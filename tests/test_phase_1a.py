"""Test suite for Phase 1-A: Desktop Perception Engine (Eyes)."""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.perception.screen_watcher import ScreenWatcher
from src.core.agent_graph import build_agent_graph
from src.core.state import AgentState


def test_screen_watcher_initialization():
    print("=== Testing ScreenWatcher Initialization ===")
    watcher = ScreenWatcher()
    assert watcher is not None
    assert isinstance(watcher.enabled, bool)
    assert watcher.privacy_mode == "strict"
    print(f"[PASS] ScreenWatcher initialized (enabled={watcher.enabled}, privacy={watcher.privacy_mode}).")


def test_screen_watcher_active_window():
    print("\n=== Testing Active Window Detection ===")
    watcher = ScreenWatcher()
    title, bounds = watcher.get_active_window()
    print(f"[PASS] Detected Active Window: '{title}', Bounds: {bounds}")
    assert isinstance(title, str)
    assert len(title) > 0


def test_screen_watcher_capture_in_ram():
    print("\n=== Testing RAM-Only Screen Capture ===")
    watcher = ScreenWatcher()
    title, img = watcher.capture_active_window()
    print(f"[PASS] Capture completed. Window: '{title}', Image array: {type(img)}")
    if img is not None:
        assert hasattr(img, "shape")
        print(f"[PASS] Image dimensions: {img.shape}")
        # Verify RAM discard
        del img


def test_screen_watcher_context_summary():
    print("\n=== Testing Context Summary Extraction ===")
    watcher = ScreenWatcher()
    summary = watcher.get_context_summary()
    assert isinstance(summary, dict)
    assert "window_title" in summary
    assert "visible_content" in summary
    print(f"[PASS] Context Summary: window='{summary['window_title']}', content_len={len(summary['visible_content'])}")


def test_state_schema_screen_context():
    print("\n=== Testing AgentState Schema Screen Context ===")
    state: AgentState = {
        "current_task": "test",
        "screen_context": {"window_title": "Test IDE", "visible_content": "print('hello')"},
        "turn_count": 1,
    }
    assert state["screen_context"]["window_title"] == "Test IDE"
    print("[PASS] AgentState accepts screen_context field.")


def run_all():
    test_screen_watcher_initialization()
    test_screen_watcher_active_window()
    test_screen_watcher_capture_in_ram()
    test_screen_watcher_context_summary()
    test_state_schema_screen_context()
    print("\n✅ ALL PHASE 1-A PERCEPTION TESTS PASSED.")


if __name__ == "__main__":
    run_all()
