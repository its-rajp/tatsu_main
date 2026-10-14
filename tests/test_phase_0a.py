"""Test suite for Phase 0-A: LangGraph Agent Core and Tool Registry."""

import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.core.state import AgentState
from src.tools.registry import AVAILABLE_TOOLS, AUDIT_LOG_PATH
from src.core.agent_graph import TatsuAgent, build_agent_graph


def test_tools_direct():
    print("=== Testing Tool Registry & Execution ===")
    
    # 1. system_info
    sys_tool = AVAILABLE_TOOLS["system_info"]
    out_sys = sys_tool.execute({"detailed": False})
    print("[PASS] system_info output:\n", out_sys)
    assert "System Health" in out_sys
    assert "CPU" in out_sys

    # 2. shell_exec safe command
    sh_tool = AVAILABLE_TOOLS["shell_exec"]
    out_sh = sh_tool.execute({"command": "echo 'TATSU Sovereign Test'"})
    print("[PASS] shell_exec output:\n", out_sh)
    assert "TATSU Sovereign Test" in out_sh

    # 3. shell_exec destructive block without confirm
    out_block = sh_tool.execute({"command": "rm -rf fake_file.txt", "confirm": False})
    print("[PASS] shell_exec destructive block:\n", out_block)
    assert "SECURITY INTERCEPT" in out_block

    # 4. file_write & file_read
    fw_tool = AVAILABLE_TOOLS["file_write"]
    test_file = "logs/test_probe.txt"
    out_write = fw_tool.execute({
        "file_path": test_file,
        "content": "Dragon awakens.",
        "confirm": True,
    })
    print("[PASS] file_write output:\n", out_write)
    assert "Successfully wrote" in out_write

    fr_tool = AVAILABLE_TOOLS["file_read"]
    out_read = fr_tool.execute({"file_path": test_file})
    print("[PASS] file_read output:\n", out_read)
    assert out_read == "Dragon awakens."

    # 5. file_read outside safe path
    out_denied = fr_tool.execute({"file_path": "/etc/shadow"})
    print("[PASS] file_read security intercept:\n", out_denied)
    assert "SECURITY INTERCEPT" in out_denied


def test_audit_log():
    print("\n=== Testing Audit Log Integrity ===")
    assert AUDIT_LOG_PATH.exists()
    lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    print(f"[PASS] Total audit log entries: {len(lines)}")
    assert len(lines) > 0
    latest = json.loads(lines[-1])
    assert "entry_hash" in latest
    assert "timestamp" in latest
    assert "event_type" in latest
    print("[PASS] Latest audit entry:", json.dumps(latest, indent=2))


def test_graph_structure():
    print("\n=== Testing LangGraph Graph Compilation ===")
    graph = build_agent_graph()
    assert graph is not None
    print("[PASS] StateGraph compiled successfully.")


def run_all():
    test_tools_direct()
    test_audit_log()
    test_graph_structure()
    print("\n✅ ALL PHASE 0-A INTEGRITY TESTS PASSED.")


if __name__ == "__main__":
    run_all()
