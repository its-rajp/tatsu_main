"""Biometric Voice Authentication Engine for TATSU — Phase 4.

Provides speaker verification using Resemblyzer (GE2E-based speaker embeddings).
All processing is LOCAL ONLY. Raw audio is never stored; only mathematical
embedding vectors are persisted. Fail-closed: if auth fails, high-risk tools
are locked.

Dependencies:
  - resemblyzer     — GE2E speaker encoder (local, no cloud)
  - numpy           — array processing
  - scipy           — cosine distance calculation
"""

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "auth.yaml"
DEFAULT_EMBEDDINGS_PATH = BASE_DIR / "data" / "user_embeddings.json"

# Lazy import of Resemblyzer — graceful fallback
_RESEMBLYZER_OK = False
_encoder = None

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
    _RESEMBLYZER_OK = True
except ImportError:
    VoiceEncoder = None
    preprocess_wav = None


def _get_encoder():
    """Lazily load the GE2E voice encoder (thread-safe singleton)."""
    global _encoder
    if _encoder is None and _RESEMBLYZER_OK:
        _encoder = VoiceEncoder("cpu")
    return _encoder


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors without scipy dependency."""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def load_auth_config() -> Dict[str, Any]:
    """Loads authentication configuration from auth.yaml."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {
        "authorized_users": ["raj"],
        "similarity_threshold": 0.75,
        "max_failures_before_lockout": 3,
        "lockout_duration_seconds": 60,
        "embeddings_path": "data/user_embeddings.json",
        "session_timeout_minutes": 30,
    }


class AuthSession:
    """Tracks authentication state for the current session."""

    def __init__(self, timeout_minutes: int = 30):
        self.is_authenticated: bool = False
        self.authenticated_user: Optional[str] = None
        self.auth_timestamp: Optional[float] = None
        self.failure_count: int = 0
        self.lockout_until: Optional[float] = None
        self.timeout_seconds: float = timeout_minutes * 60.0
        self._lock = threading.RLock()

    def mark_authenticated(self, user_name: str) -> None:
        """Mark session as authenticated for the given user."""
        with self._lock:
            self.is_authenticated = True
            self.authenticated_user = user_name
            self.auth_timestamp = time.time()
            self.failure_count = 0
            self.lockout_until = None

    def mark_failed(self, max_failures: int, lockout_seconds: int) -> bool:
        """Record a failed auth attempt. Returns True if now locked out."""
        with self._lock:
            self.failure_count += 1
            self.is_authenticated = False
            self.authenticated_user = None
            self.auth_timestamp = None
            if self.failure_count >= max_failures:
                self.lockout_until = time.time() + lockout_seconds
                return True
            return False

    def is_locked_out(self) -> bool:
        """Check if the session is currently in lockout period."""
        with self._lock:
            if self.lockout_until is None:
                return False
            if time.time() >= self.lockout_until:
                # Lockout expired — reset
                self.lockout_until = None
                self.failure_count = 0
                return False
            return True

    def is_session_valid(self) -> bool:
        """Check if current authentication session is still valid (not expired)."""
        with self._lock:
            if not self.is_authenticated or self.auth_timestamp is None:
                return False
            elapsed = time.time() - self.auth_timestamp
            if elapsed > self.timeout_seconds:
                # Session expired
                self.is_authenticated = False
                self.authenticated_user = None
                self.auth_timestamp = None
                return False
            return True

    def revoke(self) -> None:
        """Explicitly revoke the current session."""
        with self._lock:
            self.is_authenticated = False
            self.authenticated_user = None
            self.auth_timestamp = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session state for injection into agent state."""
        with self._lock:
            return {
                "is_authenticated": self.is_authenticated,
                "authenticated_user": self.authenticated_user,
                "failure_count": self.failure_count,
                "is_locked_out": self.is_locked_out(),
                "session_valid": self.is_session_valid(),
            }


class VoiceAuthenticator:
    """Speaker verification engine using Resemblyzer GE2E embeddings.

    - enroll_user(): Captures voice samples, extracts mean embedding, stores locally.
    - verify_user(): Compares incoming audio against stored embeddings.
    - reject_unknown(): Logs failed authentication attempts.

    Privacy: Raw audio is processed in RAM and immediately discarded.
    Only mathematical embedding vectors (256-dim float arrays) are persisted.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_auth_config()
        self.threshold = self.config.get("similarity_threshold", 0.75)
        self.max_failures = self.config.get("max_failures_before_lockout", 3)
        self.lockout_duration = self.config.get("lockout_duration_seconds", 60)
        session_timeout = self.config.get("session_timeout_minutes", 30)

        embeddings_rel = self.config.get("embeddings_path", "data/user_embeddings.json")
        self.embeddings_path = BASE_DIR / embeddings_rel

        self.session = AuthSession(timeout_minutes=session_timeout)
        self._lock = threading.RLock()
        self._embeddings_cache: Dict[str, np.ndarray] = {}
        self._load_embeddings()

    def _load_embeddings(self) -> None:
        """Load stored user embeddings from disk."""
        with self._lock:
            if self.embeddings_path.exists():
                try:
                    with open(self.embeddings_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for name, vec in data.items():
                        self._embeddings_cache[name] = np.array(vec, dtype=np.float32)
                except Exception as e:
                    print(f"[Auth] Failed to load embeddings: {e}")

    def _save_embeddings(self) -> None:
        """Persist current embeddings to disk."""
        with self._lock:
            self.embeddings_path.parent.mkdir(parents=True, exist_ok=True)
            serialized = {
                name: vec.tolist() for name, vec in self._embeddings_cache.items()
            }
            with open(self.embeddings_path, "w", encoding="utf-8") as f:
                json.dump(serialized, f, indent=2)

    @property
    def available(self) -> bool:
        """True if Resemblyzer is available for voice-print processing."""
        return _RESEMBLYZER_OK

    @property
    def enrolled_users(self) -> List[str]:
        """List of users with stored voice embeddings."""
        with self._lock:
            return list(self._embeddings_cache.keys())

    def enroll_user(self, name: str, audio_samples: List[np.ndarray]) -> Dict[str, Any]:
        """Enroll a user by extracting mean embedding from multiple voice samples.

        Args:
            name: User identifier (e.g., "raj").
            audio_samples: List of raw audio arrays (int16 or float32, 16kHz mono).
                          Minimum 3 samples recommended for reliable enrollment.

        Returns:
            Dict with status, embedding_dim, and num_samples.
        """
        if not _RESEMBLYZER_OK:
            return {
                "success": False,
                "error": "Resemblyzer not installed. Run: pip install resemblyzer",
            }

        if len(audio_samples) < 1:
            return {"success": False, "error": "At least 1 audio sample required."}

        encoder = _get_encoder()
        if encoder is None:
            return {"success": False, "error": "Voice encoder failed to initialize."}

        embeddings = []
        for i, sample in enumerate(audio_samples):
            try:
                # Normalize to float32 [-1, 1] if int16
                if sample.dtype == np.int16:
                    audio_f32 = sample.astype(np.float32) / 32768.0
                elif sample.dtype == np.float32:
                    audio_f32 = sample
                else:
                    audio_f32 = sample.astype(np.float32) / 32768.0

                # Preprocess (trim silence, normalize volume)
                processed = preprocess_wav(audio_f32, source_sr=16000)
                if len(processed) < 1600:  # Less than 0.1s — skip
                    continue
                embed = encoder.embed_utterance(processed)
                embeddings.append(embed)
            except Exception as e:
                print(f"[Auth] Sample {i} processing failed: {e}")
                continue

        if not embeddings:
            return {"success": False, "error": "No valid embeddings extracted from samples."}

        # Compute mean embedding (centroid of the speaker's voice space)
        mean_embedding = np.mean(embeddings, axis=0).astype(np.float32)

        with self._lock:
            self._embeddings_cache[name.lower()] = mean_embedding
        self._save_embeddings()

        # Raw audio is never stored — only the embedding vector
        return {
            "success": True,
            "user": name.lower(),
            "embedding_dim": len(mean_embedding),
            "num_samples_used": len(embeddings),
        }

    def verify_user(self, audio_sample: np.ndarray) -> Tuple[bool, float, Optional[str]]:
        """Verify a speaker against all enrolled users.

        Args:
            audio_sample: Raw audio array (int16 or float32, 16kHz mono).

        Returns:
            Tuple of (is_verified, best_score, matched_user_name_or_None).
        """
        if not _RESEMBLYZER_OK:
            # Fail-open in dev mode if resemblyzer not installed
            # Production should fail-closed
            return (False, 0.0, None)

        encoder = _get_encoder()
        if encoder is None:
            return (False, 0.0, None)

        if not self._embeddings_cache:
            return (False, 0.0, None)

        try:
            # Normalize audio
            if audio_sample.dtype == np.int16:
                audio_f32 = audio_sample.astype(np.float32) / 32768.0
            elif audio_sample.dtype == np.float32:
                audio_f32 = audio_sample
            else:
                audio_f32 = audio_sample.astype(np.float32) / 32768.0

            processed = preprocess_wav(audio_f32, source_sr=16000)
            if len(processed) < 1600:
                return (False, 0.0, None)

            incoming_embed = encoder.embed_utterance(processed)
        except Exception as e:
            print(f"[Auth] Voice verification extraction error: {e}")
            return (False, 0.0, None)

        # Compare against all enrolled users
        best_score = -1.0
        best_user = None

        with self._lock:
            for user_name, stored_embed in self._embeddings_cache.items():
                score = _cosine_similarity(incoming_embed, stored_embed)
                if score > best_score:
                    best_score = score
                    best_user = user_name

        is_verified = best_score >= self.threshold
        return (is_verified, best_score, best_user if is_verified else None)

    def authenticate(self, audio_sample: np.ndarray) -> Dict[str, Any]:
        """Full authentication flow: verify + update session + audit logging.

        Args:
            audio_sample: Raw audio from the microphone.

        Returns:
            Dict with result, score, user, and session state.
        """
        from src.tools.registry import audit_log

        # Check lockout first
        if self.session.is_locked_out():
            remaining = 0
            if self.session.lockout_until:
                remaining = int(self.session.lockout_until - time.time())
            audit_log("AUTH_ATTEMPT", {
                "result": "LOCKED_OUT",
                "remaining_seconds": remaining,
            }, status="BLOCKED")
            return {
                "success": False,
                "reason": "locked_out",
                "remaining_seconds": remaining,
            }

        is_verified, score, matched_user = self.verify_user(audio_sample)

        if is_verified and matched_user:
            # Check if user is in authorized list
            authorized = [u.lower() for u in self.config.get("authorized_users", [])]
            if matched_user.lower() in authorized:
                self.session.mark_authenticated(matched_user)
                audit_log("AUTH_SUCCESS", {
                    "user": matched_user,
                    "score": round(score, 4),
                }, status="SUCCESS")
                return {
                    "success": True,
                    "user": matched_user,
                    "score": round(score, 4),
                }
            else:
                # Known voice but not authorized
                self.reject_unknown(score, matched_user)
                return {
                    "success": False,
                    "reason": "not_authorized",
                    "matched_user": matched_user,
                    "score": round(score, 4),
                }
        else:
            # Unknown voice
            locked = self.session.mark_failed(self.max_failures, self.lockout_duration)
            self.reject_unknown(score)
            return {
                "success": False,
                "reason": "locked_out" if locked else "voice_mismatch",
                "score": round(score, 4),
                "failures": self.session.failure_count,
            }

    def reject_unknown(self, score: float = 0.0, partial_match: Optional[str] = None) -> None:
        """Log a failed authentication attempt to the audit ledger."""
        from src.tools.registry import audit_log

        audit_log("AUTH_REJECTED", {
            "score": round(score, 4),
            "partial_match": partial_match,
            "failure_count": self.session.failure_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, status="BLOCKED")

    def get_auth_status_prompt(self) -> str:
        """Generate auth status string for injection into agent system prompt."""
        if self.session.is_session_valid():
            return (
                f"[AUTH STATUS]: User '{self.session.authenticated_user}' is VERIFIED. "
                f"Full tool access granted."
            )
        elif self.session.is_locked_out():
            return (
                "[AUTH STATUS]: User is LOCKED OUT due to repeated failed authentication. "
                "ALL tools are disabled. Wait for lockout to expire."
            )
        else:
            return (
                "[AUTH STATUS]: User is UNVERIFIED. "
                "Politely decline any request involving data modification, system changes, "
                "or external communication. Offer read-only information instead. "
                "HIGH and MEDIUM risk tools are BLOCKED."
            )


# ---------------------------------------------------------------------------
# Module-level singleton for cross-module access
# ---------------------------------------------------------------------------

_AUTH_INSTANCE: Optional[VoiceAuthenticator] = None
_AUTH_LOCK = threading.Lock()


def get_authenticator() -> VoiceAuthenticator:
    """Get or create the global VoiceAuthenticator singleton."""
    global _AUTH_INSTANCE
    if _AUTH_INSTANCE is None:
        with _AUTH_LOCK:
            if _AUTH_INSTANCE is None:
                _AUTH_INSTANCE = VoiceAuthenticator()
    return _AUTH_INSTANCE
