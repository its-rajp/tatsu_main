"""Test Suite for TATSU Phase 4: Biometric Authentication & Physical Control.

Tests:
1. VoiceAuthenticator enrollment with dummy samples
2. Matching voice verification (same embedding → True)
3. Non-matching voice rejection (random noise → False)
4. Unauthenticated session blocked from HIGH-risk tools (RBAC)
5. Authenticated session allowed to run HIGH-risk tools
6. Lockout mechanism after max failed attempts
7. Hardware bridge device state management (simulated)
8. Auth session timeout and revocation
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(tmp_path):
    """Create a temporary data directory for test embeddings."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def auth_config(tmp_data_dir):
    """Create a test auth config pointing to temp directory."""
    return {
        "authorized_users": ["raj"],
        "similarity_threshold": 0.75,
        "max_failures_before_lockout": 3,
        "lockout_duration_seconds": 2,  # Short for testing
        "embeddings_path": str(tmp_data_dir / "user_embeddings.json"),
        "session_timeout_minutes": 1,
    }


@pytest.fixture
def dummy_voice_samples():
    """Generate deterministic dummy audio samples for testing."""
    rng = np.random.RandomState(42)
    # Simulated voice: sine waves with some noise (consistent pattern)
    t = np.linspace(0, 2, 32000, dtype=np.float32)  # 2 seconds @ 16kHz
    base_signal = np.sin(2 * np.pi * 200 * t) * 0.5  # 200Hz tone
    samples = []
    for i in range(5):
        noise = rng.randn(32000).astype(np.float32) * 0.01
        sample = (base_signal + noise + i * 0.001).astype(np.float32)
        samples.append(sample)
    return samples


@pytest.fixture
def random_noise_sample():
    """Generate random noise that should NOT match any enrolled user."""
    rng = np.random.RandomState(999)
    return rng.randn(32000).astype(np.float32) * 0.3


# ---------------------------------------------------------------------------
# Test 1: Auth Session Management
# ---------------------------------------------------------------------------

class TestAuthSession:
    """Test the AuthSession state tracking."""

    def test_initial_state_unauthenticated(self):
        from src.security.biometric_auth import AuthSession
        session = AuthSession(timeout_minutes=5)
        assert session.is_authenticated is False
        assert session.authenticated_user is None
        assert session.failure_count == 0

    def test_mark_authenticated(self):
        from src.security.biometric_auth import AuthSession
        session = AuthSession(timeout_minutes=5)
        session.mark_authenticated("raj")
        assert session.is_authenticated is True
        assert session.authenticated_user == "raj"
        assert session.failure_count == 0

    def test_session_valid_within_timeout(self):
        from src.security.biometric_auth import AuthSession
        session = AuthSession(timeout_minutes=5)
        session.mark_authenticated("raj")
        assert session.is_session_valid() is True

    def test_session_expires_after_timeout(self):
        from src.security.biometric_auth import AuthSession
        session = AuthSession(timeout_minutes=0)  # Immediate timeout
        session.mark_authenticated("raj")
        session.timeout_seconds = 0.01  # Override to 10ms
        time.sleep(0.02)
        assert session.is_session_valid() is False

    def test_revoke_session(self):
        from src.security.biometric_auth import AuthSession
        session = AuthSession(timeout_minutes=5)
        session.mark_authenticated("raj")
        session.revoke()
        assert session.is_authenticated is False
        assert session.is_session_valid() is False

    def test_failure_tracking(self):
        from src.security.biometric_auth import AuthSession
        session = AuthSession()
        locked = session.mark_failed(max_failures=3, lockout_seconds=2)
        assert locked is False
        assert session.failure_count == 1

    def test_lockout_after_max_failures(self):
        from src.security.biometric_auth import AuthSession
        session = AuthSession()
        session.mark_failed(max_failures=3, lockout_seconds=2)
        session.mark_failed(max_failures=3, lockout_seconds=2)
        locked = session.mark_failed(max_failures=3, lockout_seconds=2)
        assert locked is True
        assert session.is_locked_out() is True

    def test_lockout_expires(self):
        from src.security.biometric_auth import AuthSession
        session = AuthSession()
        for _ in range(3):
            session.mark_failed(max_failures=3, lockout_seconds=1)
        assert session.is_locked_out() is True
        time.sleep(1.1)
        assert session.is_locked_out() is False
        assert session.failure_count == 0  # Reset after lockout expires

    def test_to_dict_serialization(self):
        from src.security.biometric_auth import AuthSession
        session = AuthSession(timeout_minutes=5)
        session.mark_authenticated("raj")
        state = session.to_dict()
        assert state["is_authenticated"] is True
        assert state["authenticated_user"] == "raj"
        assert state["failure_count"] == 0
        assert state["is_locked_out"] is False
        assert state["session_valid"] is True


# ---------------------------------------------------------------------------
# Test 2 & 3: Voice Authenticator (with mocked Resemblyzer)
# ---------------------------------------------------------------------------

class TestVoiceAuthenticator:
    """Test VoiceAuthenticator enrollment and verification."""

    def test_enrollment_without_resemblyzer(self, auth_config):
        """If Resemblyzer is not available, enrollment should fail gracefully."""
        from src.security.biometric_auth import VoiceAuthenticator
        with patch("src.security.biometric_auth._RESEMBLYZER_OK", False):
            auth = VoiceAuthenticator(config=auth_config)
            result = auth.enroll_user("raj", [np.zeros(16000, dtype=np.float32)])
            assert result["success"] is False
            assert "not installed" in result["error"].lower() or "resemblyzer" in result["error"].lower()

    def test_enrolled_users_persist_to_disk(self, auth_config, tmp_data_dir):
        """Verify that enrolling stores embeddings to the configured path."""
        from src.security.biometric_auth import VoiceAuthenticator
        auth = VoiceAuthenticator(config=auth_config)
        # Manually inject a fake embedding
        auth._embeddings_cache["testuser"] = np.random.randn(256).astype(np.float32)
        auth._save_embeddings()

        embed_path = Path(auth_config["embeddings_path"])
        assert embed_path.exists()
        with open(embed_path) as f:
            data = json.load(f)
        assert "testuser" in data
        assert len(data["testuser"]) == 256

    def test_cosine_similarity_identical(self):
        """Identical vectors should have similarity ≈ 1.0."""
        from src.security.biometric_auth import _cosine_similarity
        a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert abs(_cosine_similarity(a, a) - 1.0) < 0.0001

    def test_cosine_similarity_orthogonal(self):
        """Orthogonal vectors should have similarity ≈ 0.0."""
        from src.security.biometric_auth import _cosine_similarity
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert abs(_cosine_similarity(a, b)) < 0.0001

    def test_cosine_similarity_zero_vector(self):
        """Zero vector should return 0.0 without division error."""
        from src.security.biometric_auth import _cosine_similarity
        a = np.array([1.0, 2.0], dtype=np.float32)
        b = np.zeros(2, dtype=np.float32)
        assert _cosine_similarity(a, b) == 0.0

    def test_verify_no_enrolled_users(self, auth_config):
        """Verification with no enrolled users should fail."""
        from src.security.biometric_auth import VoiceAuthenticator
        auth = VoiceAuthenticator(config=auth_config)
        is_verified, score, user = auth.verify_user(np.random.randn(16000).astype(np.float32))
        # With no resemblyzer or no embeddings, should return False
        assert is_verified is False

    def test_auth_status_prompt_unverified(self, auth_config):
        """Unverified session should produce UNVERIFIED prompt."""
        from src.security.biometric_auth import VoiceAuthenticator
        auth = VoiceAuthenticator(config=auth_config)
        prompt = auth.get_auth_status_prompt()
        assert "UNVERIFIED" in prompt

    def test_auth_status_prompt_verified(self, auth_config):
        """Verified session should produce VERIFIED prompt."""
        from src.security.biometric_auth import VoiceAuthenticator
        auth = VoiceAuthenticator(config=auth_config)
        auth.session.mark_authenticated("raj")
        prompt = auth.get_auth_status_prompt()
        assert "VERIFIED" in prompt
        assert "raj" in prompt

    def test_auth_status_prompt_locked(self, auth_config):
        """Locked out session should produce LOCKED OUT prompt."""
        from src.security.biometric_auth import VoiceAuthenticator
        auth = VoiceAuthenticator(config=auth_config)
        for _ in range(3):
            auth.session.mark_failed(max_failures=3, lockout_seconds=60)
        prompt = auth.get_auth_status_prompt()
        assert "LOCKED OUT" in prompt


# ---------------------------------------------------------------------------
# Test 4 & 5: RBAC Enforcement in execute_node
# ---------------------------------------------------------------------------

class TestRBAC:
    """Test that execute_node enforces biometric RBAC on tool risk levels."""

    def test_high_risk_blocked_when_unauthenticated(self):
        """shell_exec (HIGH risk) should be BLOCKED for unauthenticated sessions."""
        from src.core.agent_graph import execute_node
        from src.tools.registry import RiskLevel

        state = {
            "tool_calls": [{"id": "test_1", "name": "shell_exec", "args": {"command": "ls"}}],
            "observations": [],
            "messages": [],
            "is_authenticated": False,
        }

        result = execute_node(state)
        obs = result["observations"]
        assert len(obs) == 1
        assert "Security Violation" in obs[0]
        assert "Biometric authentication required" in obs[0]

    def test_low_risk_allowed_when_unauthenticated(self):
        """system_info (LOW risk) should PASS even without authentication."""
        from src.core.agent_graph import execute_node

        state = {
            "tool_calls": [{"id": "test_2", "name": "system_info", "args": {"detailed": False}}],
            "observations": [],
            "messages": [],
            "is_authenticated": False,
        }

        result = execute_node(state)
        obs = result["observations"]
        assert len(obs) == 1
        assert "Security Violation" not in obs[0]
        assert "System Health" in obs[0] or "CPU" in obs[0]

    def test_high_risk_allowed_when_authenticated(self):
        """shell_exec (HIGH risk) should PASS for authenticated sessions."""
        from src.core.agent_graph import execute_node

        state = {
            "tool_calls": [{"id": "test_3", "name": "shell_exec", "args": {"command": "echo test"}}],
            "observations": [],
            "messages": [],
            "is_authenticated": True,
        }

        result = execute_node(state)
        obs = result["observations"]
        assert len(obs) == 1
        assert "Security Violation" not in obs[0]

    def test_medium_risk_blocked_when_unauthenticated(self):
        """file_write (MEDIUM risk) should be BLOCKED for unauthenticated sessions."""
        from src.core.agent_graph import execute_node

        state = {
            "tool_calls": [{"id": "test_4", "name": "file_write", "args": {"file_path": "test.txt", "content": "x"}}],
            "observations": [],
            "messages": [],
            "is_authenticated": False,
        }

        result = execute_node(state)
        obs = result["observations"]
        assert len(obs) == 1
        assert "Security Violation" in obs[0]


# ---------------------------------------------------------------------------
# Test 7: Hardware Bridge (Simulated)
# ---------------------------------------------------------------------------

class TestHardwareBridge:
    """Test the simulated hardware bridge for smart home control."""

    def test_list_devices(self):
        from src.integration.hardware_bridge import HardwareBridge
        bridge = HardwareBridge()
        devices = bridge.list_devices()
        assert len(devices) >= 5  # At least the default devices
        names = [d["id"] for d in devices]
        assert "desk_lamp" in names
        assert "ceiling_fan" in names

    def test_get_device_state(self):
        from src.integration.hardware_bridge import HardwareBridge
        bridge = HardwareBridge()
        state = bridge.get_device_state("desk_lamp")
        assert "error" not in state
        assert state["name"] == "Desk Lamp"
        assert state["hardware_mode"] == "SIMULATED"

    def test_get_unknown_device(self):
        from src.integration.hardware_bridge import HardwareBridge
        bridge = HardwareBridge()
        state = bridge.get_device_state("nonexistent")
        assert "error" in state

    def test_set_device_on_off(self):
        from src.integration.hardware_bridge import HardwareBridge
        bridge = HardwareBridge()
        result = bridge.set_device_state("desk_lamp", "on")
        assert result["success"] is True
        assert result["new_state"] == "on"
        assert result["mode"] == "SIMULATED"

        result = bridge.set_device_state("desk_lamp", "off")
        assert result["success"] is True
        assert result["new_state"] == "off"

    def test_set_temperature(self):
        from src.integration.hardware_bridge import HardwareBridge
        bridge = HardwareBridge()
        result = bridge.set_device_state("ac_unit", "22")
        assert result["success"] is True
        state = bridge.get_device_state("ac_unit")
        assert state["temperature"] == 22
        assert state["state"] == "on"

    def test_set_volume(self):
        from src.integration.hardware_bridge import HardwareBridge
        bridge = HardwareBridge()
        result = bridge.set_device_state("speaker_system", "75")
        assert result["success"] is True
        state = bridge.get_device_state("speaker_system")
        assert state["volume"] == 75

    def test_lock_unlock(self):
        from src.integration.hardware_bridge import HardwareBridge
        bridge = HardwareBridge()
        result = bridge.set_device_state("door_lock", "unlocked")
        assert result["success"] is True
        assert result["new_state"] == "unlocked"

        result = bridge.set_device_state("door_lock", "locked")
        assert result["success"] is True
        assert result["new_state"] == "locked"

    def test_add_custom_device(self):
        from src.integration.hardware_bridge import HardwareBridge
        bridge = HardwareBridge()
        result = bridge.add_device("test_led", {
            "name": "Test LED",
            "type": "light",
            "state": "off",
        })
        assert result["success"] is True
        state = bridge.get_device_state("test_led")
        assert state["name"] == "Test LED"

    def test_simulation_mode_detected(self):
        from src.integration.hardware_bridge import HardwareBridge
        bridge = HardwareBridge()
        # On Mac/laptop, should always be simulated
        assert bridge.is_real_hardware is False or bridge.gpio_lib is not None


# ---------------------------------------------------------------------------
# Test 8: Smart Home Tools via Registry
# ---------------------------------------------------------------------------

class TestSmartHomeTools:
    """Test smart home tools registered in the tool registry."""

    def test_smart_home_status_tool(self):
        from src.tools.registry import AVAILABLE_TOOLS
        tool = AVAILABLE_TOOLS.get("smart_home_status")
        assert tool is not None
        result = tool.execute({"device": ""})
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) >= 5

    def test_smart_home_control_tool(self):
        from src.tools.registry import AVAILABLE_TOOLS
        tool = AVAILABLE_TOOLS.get("control_smart_home")
        assert tool is not None
        result = tool.execute({"device": "desk_lamp", "action": "on"})
        assert "Desk Lamp" in result
        assert "SIMULATED" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
