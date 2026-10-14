"""Test suite for Phase 1-B: System Health Monitoring & Proactivity (Nerves)."""

import time
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.proactive.alert_engine import AlertEngine
from src.perception.system_monitor import SystemMonitor
from src.tools.registry import AVAILABLE_TOOLS


def test_alert_engine_basic_and_cooldown():
    print("=== Testing AlertEngine & Cooldown Logic ===")
    fired = []
    engine = AlertEngine(
        voice_callback=lambda msg: fired.append(msg),
        cooldown_seconds=2,
        polite_mode=True,
    )

    # First trigger should succeed
    res1 = engine.trigger_alert(
        alert_type="test_cpu",
        severity="WARNING",
        message="CPU is high.",
        suggestion="Kill runaway task?",
        suggested_action={"tool": "shell_exec", "args": {"command": "echo 'ok'"}},
    )
    assert res1 is True
    assert len(fired) == 1
    assert engine.get_latest_pending_action() is not None
    print("[PASS] Alert triggered successfully and action stored.")

    # Second trigger immediately should be silenced by cooldown
    res2 = engine.trigger_alert(
        alert_type="test_cpu",
        severity="WARNING",
        message="CPU is still high.",
    )
    assert res2 is False
    print("[PASS] Alert successfully suppressed by cooldown.")

    # Pending action pop
    pending = engine.pop_pending_action()
    assert pending["action"]["tool"] == "shell_exec"
    assert engine.get_latest_pending_action() is None
    print("[PASS] Pending action consumed cleanly.")


def test_system_monitor_check_health():
    print("\n=== Testing SystemMonitor Health Check ===")
    engine = AlertEngine(cooldown_seconds=5)
    monitor = SystemMonitor(alert_engine=engine)
    status = monitor.check_health()
    assert isinstance(status, dict)
    assert "cpu_high" in status
    assert "ram_critical" in status
    assert "disk_full" in status
    assert "details" in status
    details = status["details"]
    assert "cpu_percent" in details
    assert "ram_percent" in details
    assert "disk_percent" in details
    print(f"[PASS] Health check results: CPU={details['cpu_percent']}%, RAM={details['ram_percent']}%, Disk={details['disk_percent']}%")


def test_system_monitor_background_loop():
    print("\n=== Testing SystemMonitor Background Loop ===")
    engine = AlertEngine(cooldown_seconds=5)
    monitor = SystemMonitor(alert_engine=engine)
    monitor.start_background_loop(interval_sec=1)
    assert monitor._running is True
    assert monitor._thread.is_alive()
    time.sleep(1.5)
    monitor.stop_background_loop()
    assert monitor._running is False
    print("[PASS] Background thread started and stopped cleanly.")


def test_shell_tool_process_kill_safety():
    print("\n=== Testing Process Kill & Dangerous Command Safety ===")
    shell_tool = AVAILABLE_TOOLS["shell_exec"]

    # Allowed safe command
    safe_res = shell_tool.execute({"command": "echo 'Process PID 42 status: OK'"})
    print("[PASS] Safe command executed:\n", safe_res)
    assert "STDOUT" in safe_res and "PID 42" in safe_res

    # Blocked without confirm
    blocked = shell_tool.execute({"command": "sudo kill -9 9999", "confirm": False})
    print("[PASS] Sudo command blocked without confirm:\n", blocked)
    assert "SECURITY INTERCEPT" in blocked


def run_all():
    test_alert_engine_basic_and_cooldown()
    test_system_monitor_check_health()
    test_system_monitor_background_loop()
    test_shell_tool_process_kill_safety()
    print("\n✅ ALL PHASE 1-B MONITORING & PROACTIVITY TESTS PASSED.")


if __name__ == "__main__":
    run_all()
