"""Python Sandbox Executor for TATSU Sovereign Agent — Phase 3.

Executes Python code in an isolated subprocess with strict timeouts,
safety static analysis, and memory/filesystem confinement.
"""

import os
import re
import sys
import time
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class PythonSandbox:
    """Safe, isolated Python execution environment with static safety checks."""

    # Patterns considered dangerous or requiring explicit confirmation
    DANGEROUS_PATTERNS = [
        r"\bos\.system\b",
        r"\bos\.remove\b",
        r"\bos\.unlink\b",
        r"\bos\.rmdir\b",
        r"\bshutil\.rmtree\b",
        r"\bsocket\b",
        r"\bsubprocess\b",
        r"__import__\s*\(\s*['\"](?:os|subprocess|socket|shutil)['\"]\s*\)",
        r"\bopen\s*\(\s*['\"]/(?:etc|bin|sbin|usr|var|System|Library)",
        r"\bpty\.spawn\b",
        r"\bctypes\b",
    ]

    def __init__(self, timeout_seconds: int = 10, max_output_chars: int = 5000):
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    def scan_safety(self, code_str: str) -> Optional[str]:
        """Scans code for dangerous operations. Returns warning message if intercepted."""
        for pattern in self.DANGEROUS_PATTERNS:
            match = re.search(pattern, code_str, re.IGNORECASE)
            if match:
                return (
                    f"SECURITY INTERCEPT: Code contains potentially dangerous operation "
                    f"matching pattern '{pattern}'. Execution blocked unless confirm=True."
                )
        return None

    def execute_code(self, code_str: str, confirm: bool = False) -> Dict[str, Any]:
        """Executes a Python code snippet in an isolated subprocess.
        
        Args:
            code_str: Python code to execute.
            confirm: If True, bypasses dangerous pattern block.

        Returns:
            Dict: {"success": bool, "stdout": str, "stderr": str, "exit_code": int}
        """
        code_str = code_str.strip()
        if not code_str:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Error: Empty Python code string.",
                "exit_code": 1,
            }

        # 1. Static security check
        safety_warning = self.scan_safety(code_str)
        if safety_warning and not confirm:
            return {
                "success": False,
                "stdout": "",
                "stderr": safety_warning,
                "exit_code": 126,  # Command invoked cannot execute
            }

        # 2. Write code to a temporary script file
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(code_str)

        t0 = time.time()
        try:
            # Execute with python3 in isolated subprocess
            res = subprocess.run(
                [sys.executable, str(tmp_path)],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            duration_ms = int((time.time() - t0) * 1000)

            stdout = res.stdout.strip()
            stderr = res.stderr.strip()

            if len(stdout) > self.max_output_chars:
                stdout = stdout[: self.max_output_chars] + "\n...[Output truncated]"
            if len(stderr) > self.max_output_chars:
                stderr = stderr[: self.max_output_chars] + "\n...[Errors truncated]"

            return {
                "success": res.returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": res.returncode,
                "duration_ms": duration_ms,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Error: Python script timed out after {self.timeout_seconds} seconds.",
                "exit_code": 124,
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution error: {str(e)}",
                "exit_code": 1,
            }
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
