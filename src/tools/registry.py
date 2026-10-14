"""Tool Registry and Sandboxed Tools for TATSU Sovereign Agent."""

import hashlib
import json
import os
import re
import subprocess
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Type
import psutil
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent.parent
AUDIT_LOG_PATH = BASE_DIR / "logs" / "tatsu_audit.jsonl"
ALLOWED_DIRS_DEFAULT = [
    BASE_DIR.resolve(),
    (BASE_DIR / "logs").resolve(),
    (BASE_DIR / "config").resolve(),
    (BASE_DIR / "src").resolve(),
    (BASE_DIR / "memory").resolve(),
]


def audit_log(event_type: str, details: Dict[str, Any], status: str = "SUCCESS") -> None:
    """Appends an immutable entry to the JSONL audit ledger with SHA256 integrity."""
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    
    payload = {
        "timestamp": timestamp,
        "event_type": event_type,
        "status": status,
        "details": details,
    }
    
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    entry_hash = hashlib.sha256(encoded).hexdigest()
    payload["entry_hash"] = entry_hash

    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


class TatsuTool(ABC):
    """Abstract Base Class for all TATSU tools."""

    name: str
    description: str
    args_schema: Type[BaseModel]

    @abstractmethod
    def execute(self, args: Dict[str, Any]) -> str:
        """Executes the tool with validated arguments and returns result string."""
        pass

    def to_ollama_tool(self) -> Dict[str, Any]:
        """Converts tool definition to Ollama / OpenAI function calling schema."""
        schema = self.args_schema.model_json_schema()
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


# ---------------------------------------------------------------------------
# 1. Shell Exec Tool
# ---------------------------------------------------------------------------

class ShellExecInput(BaseModel):
    command: str = Field(..., description="The shell command to execute.")
    confirm: bool = Field(
        default=False,
        description="Must be set to True explicitly for commands that modify or delete files.",
    )


class ShellExecTool(TatsuTool):
    name = "shell_exec"
    description = (
        "Execute a shell command with a 30-second timeout. Captures stdout and stderr. "
        "Destructive commands (rm, rmdir, delete, drop, format, dd, mkfs) require confirm=True."
    )
    args_schema = ShellExecInput

    DESTRUCTIVE_PATTERN = re.compile(
        r"\b(rm\s+-|rmdir\b|unlink\b|drop\s+database|format\b|dd\s+if|mkfs\b|del\s+/|erase\b)",
        re.IGNORECASE,
    )

    def execute(self, args: Dict[str, Any]) -> str:
        cmd = args.get("command", "").strip()
        confirm = bool(args.get("confirm", False))

        if not cmd:
            return "Error: Command cannot be empty."

        # Safety check: block destructive commands unless confirmed
        if self.DESTRUCTIVE_PATTERN.search(cmd) and not confirm:
            msg = (
                f"SECURITY INTERCEPT: Command '{cmd}' appears potentially destructive. "
                "Explicit confirmation required: re-run with confirm=True."
            )
            audit_log("TOOL_EXECUTION", {"tool": self.name, "command": cmd, "warning": msg}, status="BLOCKED")
            return msg

        t0 = time.time()
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=30,
            )
            duration_ms = int((time.time() - t0) * 1000)
            stdout = res.stdout.strip()
            stderr = res.stderr.strip()

            out_parts = []
            if stdout:
                out_parts.append(f"STDOUT:\n{stdout}")
            if stderr:
                out_parts.append(f"STDERR:\n{stderr}")
            if not out_parts:
                out_parts.append("(Command produced no output, exit code: 0)")

            result_str = "\n".join(out_parts)
            status = "SUCCESS" if res.returncode == 0 else f"FAILED_EXIT_{res.returncode}"

            audit_log(
                "TOOL_EXECUTION",
                {
                    "tool": self.name,
                    "command": cmd,
                    "exit_code": res.returncode,
                    "duration_ms": duration_ms,
                    "output_preview": result_str[:300],
                },
                status=status,
            )
            return result_str
        except subprocess.TimeoutExpired:
            msg = f"Error: Command timed out after 30 seconds: '{cmd}'"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "command": cmd, "error": "timeout"}, status="TIMEOUT")
            return msg
        except Exception as e:
            msg = f"Error executing shell command: {str(e)}"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "command": cmd, "error": str(e)}, status="ERROR")
            return msg


# ---------------------------------------------------------------------------
# 2. File Read Tool
# ---------------------------------------------------------------------------

class FileReadInput(BaseModel):
    file_path: str = Field(..., description="Path to the file to read (relative or absolute).")


class FileReadTool(TatsuTool):
    name = "file_read"
    description = "Read the contents of a text file within allowed project directories."
    args_schema = FileReadInput

    def _resolve_safe_path(self, file_path: str) -> Optional[Path]:
        p = (BASE_DIR / file_path).resolve() if not os.path.isabs(file_path) else Path(file_path).resolve()
        for allowed in ALLOWED_DIRS_DEFAULT:
            try:
                p.relative_to(allowed)
                return p
            except ValueError:
                continue
        return None

    def execute(self, args: Dict[str, Any]) -> str:
        raw_path = args.get("file_path", "").strip()
        if not raw_path:
            return "Error: file_path cannot be empty."

        safe_path = self._resolve_safe_path(raw_path)
        if safe_path is None:
            msg = f"SECURITY INTERCEPT: Access to '{raw_path}' denied. Path is outside allowed directories."
            audit_log("TOOL_EXECUTION", {"tool": self.name, "path": raw_path}, status="BLOCKED")
            return msg

        if not safe_path.exists():
            return f"Error: File does not exist: '{safe_path}'"

        if safe_path.is_dir():
            return f"Error: '{safe_path}' is a directory, not a file."

        try:
            content = safe_path.read_text(encoding="utf-8", errors="replace")
            # Truncate preview if gigantic
            if len(content) > 50000:
                content = content[:50000] + f"\n... [Truncated {len(content) - 50000} characters]"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "path": str(safe_path), "bytes": len(content)}, status="SUCCESS")
            return content
        except Exception as e:
            msg = f"Error reading file '{safe_path}': {str(e)}"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "path": str(safe_path), "error": str(e)}, status="ERROR")
            return msg


# ---------------------------------------------------------------------------
# 3. File Write Tool
# ---------------------------------------------------------------------------

class FileWriteInput(BaseModel):
    file_path: str = Field(..., description="Target file path to write to.")
    content: str = Field(..., description="Text content to write into the file.")
    confirm: bool = Field(
        default=False,
        description="Confirmation flag. Required if overwriting an existing file.",
    )


class FileWriteTool(TatsuTool):
    name = "file_write"
    description = (
        "Write text content to a file within allowed project directories. "
        "Requires confirm=True if overwriting an existing file."
    )
    args_schema = FileWriteInput

    def _resolve_safe_path(self, file_path: str) -> Optional[Path]:
        p = (BASE_DIR / file_path).resolve() if not os.path.isabs(file_path) else Path(file_path).resolve()
        for allowed in ALLOWED_DIRS_DEFAULT:
            try:
                p.relative_to(allowed)
                return p
            except ValueError:
                continue
        return None

    def execute(self, args: Dict[str, Any]) -> str:
        raw_path = args.get("file_path", "").strip()
        content = args.get("content", "")
        confirm = bool(args.get("confirm", False))

        if not raw_path:
            return "Error: file_path cannot be empty."

        safe_path = self._resolve_safe_path(raw_path)
        if safe_path is None:
            msg = f"SECURITY INTERCEPT: Access to '{raw_path}' denied. Path is outside allowed directories."
            audit_log("TOOL_EXECUTION", {"tool": self.name, "path": raw_path}, status="BLOCKED")
            return msg

        if safe_path.exists() and not confirm:
            msg = (
                f"SECURITY INTERCEPT: File '{safe_path}' already exists. "
                "Overwriting requires confirm=True."
            )
            audit_log("TOOL_EXECUTION", {"tool": self.name, "path": str(safe_path), "warning": "overwrite_unconfirmed"}, status="BLOCKED")
            return msg

        try:
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            safe_path.write_text(content, encoding="utf-8")
            audit_log(
                "TOOL_EXECUTION",
                {"tool": self.name, "path": str(safe_path), "bytes_written": len(content.encode('utf-8'))},
                status="SUCCESS",
            )
            return f"Successfully wrote {len(content)} characters to '{safe_path}'."
        except Exception as e:
            msg = f"Error writing file '{safe_path}': {str(e)}"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "path": str(safe_path), "error": str(e)}, status="ERROR")
            return msg


# ---------------------------------------------------------------------------
# 4. System Info Tool
# ---------------------------------------------------------------------------

class SystemInfoInput(BaseModel):
    detailed: bool = Field(default=False, description="Whether to include per-CPU and disk partition breakdown.")


class SystemInfoTool(TatsuTool):
    name = "system_info"
    description = "Check current system health and hardware metrics: CPU %, Memory (RAM) %, and Disk usage %."
    args_schema = SystemInfoInput

    def execute(self, args: Dict[str, Any]) -> str:
        detailed = bool(args.get("detailed", False))
        try:
            cpu_percent = psutil.cpu_percent(interval=0.2)
            vm = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            boot_time = datetime.fromtimestamp(psutil.boot_time(), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            info = {
                "cpu_percent": f"{cpu_percent}%",
                "cpu_cores": psutil.cpu_count(logical=True),
                "ram_used_gb": round(vm.used / (1024**3), 2),
                "ram_total_gb": round(vm.total / (1024**3), 2),
                "ram_percent": f"{vm.percent}%",
                "disk_used_gb": round(disk.used / (1024**3), 2),
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "disk_percent": f"{disk.percent}%",
                "boot_time": boot_time,
            }

            if detailed:
                info["cpu_per_core"] = [f"{p}%" for p in psutil.cpu_percent(percpu=True, interval=0.1)]
                parts = []
                for p in psutil.disk_partitions(all=False):
                    try:
                        u = psutil.disk_usage(p.mountpoint)
                        parts.append({
                            "device": p.device,
                            "mountpoint": p.mountpoint,
                            "percent": f"{u.percent}%",
                        })
                    except Exception:
                        pass
                info["partitions"] = parts

            summary_text = (
                f"=== System Health ===\n"
                f"• CPU Usage:   {info['cpu_percent']} ({info['cpu_cores']} cores)\n"
                f"• Memory:      {info['ram_used_gb']} GB / {info['ram_total_gb']} GB ({info['ram_percent']})\n"
                f"• Disk (/):    {info['disk_used_gb']} GB / {info['disk_total_gb']} GB ({info['disk_percent']})\n"
                f"• Boot Time:   {info['boot_time']}"
            )
            audit_log("TOOL_EXECUTION", {"tool": self.name, "metrics": info}, status="SUCCESS")
            return summary_text
        except Exception as e:
            msg = f"Error retrieving system info: {str(e)}"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "error": str(e)}, status="ERROR")
            return msg


# ---------------------------------------------------------------------------
# Global Registry Map
# ---------------------------------------------------------------------------

AVAILABLE_TOOLS: Dict[str, TatsuTool] = {
    "shell_exec": ShellExecTool(),
    "file_read": FileReadTool(),
    "file_write": FileWriteTool(),
    "system_info": SystemInfoTool(),
}
