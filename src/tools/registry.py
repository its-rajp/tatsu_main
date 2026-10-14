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


class RiskLevel:
    """Security risk classifications for tool operations."""
    LOW = "LOW"        # Read-only ops: file_search, browser_extract, system_info, file_read
    MEDIUM = "MEDIUM"  # Non-destructive write ops: file_archive, file_organize, browser_navigate, browser_click, file_write
    HIGH = "HIGH"      # Code execution / System modification: shell_exec, run_python_script


class TatsuTool(ABC):
    """Abstract Base Class for all TATSU tools."""

    name: str
    description: str
    args_schema: Type[BaseModel]
    risk_level: str = RiskLevel.LOW

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
        "Allows process management (kill <PID>, ps, top, htop). "
        "Destructive commands (rm, rmdir, dd, mkfs, sudo, shutdown, reboot) require confirm=True."
    )
    args_schema = ShellExecInput
    risk_level = RiskLevel.HIGH

    DESTRUCTIVE_PATTERN = re.compile(
        r"\b(rm\s+-|rmdir\b|unlink\b|drop\s+database|format\b|dd\s+if|mkfs\b|del\s+/|erase\b|sudo\b|shutdown\b|reboot\b|poweroff\b|init\s+0\b)",
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
    risk_level = RiskLevel.LOW

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
    risk_level = RiskLevel.MEDIUM

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
    risk_level = RiskLevel.LOW

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
# 5. Python Sandbox Tool
# ---------------------------------------------------------------------------

class RunPythonScriptInput(BaseModel):
    code: str = Field(..., description="Python source code to execute in sandbox.")
    confirm: bool = Field(
        default=False,
        description="Required if code contains operations flagged as sensitive/destructive.",
    )


class RunPythonScriptTool(TatsuTool):
    name = "run_python_script"
    description = (
        "Execute Python code in an isolated subprocess sandbox with resource constraints. "
        "Captures stdout/stderr. Dangerous modules require confirm=True."
    )
    args_schema = RunPythonScriptInput
    risk_level = RiskLevel.HIGH

    def __init__(self):
        self._sandbox = None

    def _get_sandbox(self):
        if self._sandbox is None:
            from src.tools.python_sandbox import PythonSandbox
            self._sandbox = PythonSandbox()
        return self._sandbox

    def execute(self, args: Dict[str, Any]) -> str:
        code = args.get("code", "")
        confirm = bool(args.get("confirm", False))
        sandbox = self._get_sandbox()
        res = sandbox.execute_code(code, confirm=confirm)

        out_parts = []
        if res.get("stdout"):
            out_parts.append(f"STDOUT:\n{res['stdout']}")
        if res.get("stderr"):
            out_parts.append(f"STDERR:\n{res['stderr']}")
        if not out_parts:
            out_parts.append(f"(Script executed cleanly, exit code: {res.get('exit_code', 0)})")

        status = "SUCCESS" if res.get("success") else ("BLOCKED" if res.get("exit_code") == 126 else "ERROR")
        audit_log("TOOL_EXECUTION", {"tool": self.name, "exit_code": res.get("exit_code")}, status=status)
        return "\n\n".join(out_parts)


# ---------------------------------------------------------------------------
# 6. Browser Control Tools
# ---------------------------------------------------------------------------

_BROWSER_INSTANCE = None


def _get_browser():
    global _BROWSER_INSTANCE
    if _BROWSER_INSTANCE is None:
        from src.tools.browser_control import BrowserAgent
        _BROWSER_INSTANCE = BrowserAgent(headless=True)
    return _BROWSER_INSTANCE


class BrowserNavigateInput(BaseModel):
    url: str = Field(..., description="URL or local HTML file path to navigate to.")


class BrowserNavigateTool(TatsuTool):
    name = "browser_navigate"
    description = "Navigate local headless browser to a specified URL or HTML file."
    args_schema = BrowserNavigateInput
    risk_level = RiskLevel.MEDIUM

    def execute(self, args: Dict[str, Any]) -> str:
        url = args.get("url", "")
        browser = _get_browser()
        res = browser.navigate(url)
        if res.get("success"):
            msg = f"Navigated to '{res.get('url')}'. Title: '{res.get('title')}' (Status: {res.get('status_code')})"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "url": url}, status="SUCCESS")
        else:
            msg = f"Navigation failed: {res.get('error')}"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "url": url, "error": res.get("error")}, status="ERROR")
        return msg


class BrowserExtractInput(BaseModel):
    selector: str = Field(default="body", description="CSS selector of element to extract text from.")


class BrowserExtractTool(TatsuTool):
    name = "browser_extract"
    description = "Extract text from currently open browser page using a CSS selector."
    args_schema = BrowserExtractInput
    risk_level = RiskLevel.LOW

    def execute(self, args: Dict[str, Any]) -> str:
        selector = args.get("selector", "body")
        browser = _get_browser()
        text = browser.extract_text(selector=selector)
        audit_log("TOOL_EXECUTION", {"tool": self.name, "selector": selector, "chars": len(text)}, status="SUCCESS")
        return text


class BrowserClickInput(BaseModel):
    selector: str = Field(..., description="CSS selector of DOM element to click.")


class BrowserClickTool(TatsuTool):
    name = "browser_click"
    description = "Simulate a user click on a browser DOM element identified by selector."
    args_schema = BrowserClickInput
    risk_level = RiskLevel.MEDIUM

    def execute(self, args: Dict[str, Any]) -> str:
        selector = args.get("selector", "")
        browser = _get_browser()
        res = browser.click_element(selector)
        if res.get("success"):
            msg = f"Clicked element '{selector}'. Current URL: {res.get('current_url')}"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "selector": selector}, status="SUCCESS")
        else:
            msg = f"Click failed: {res.get('error')}"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "selector": selector, "error": res.get('error')}, status="ERROR")
        return msg


# ---------------------------------------------------------------------------
# 7. File Management Tools
# ---------------------------------------------------------------------------

_FILE_MANAGER_INSTANCE = None


def _get_file_manager():
    global _FILE_MANAGER_INSTANCE
    if _FILE_MANAGER_INSTANCE is None:
        from src.tools.file_manager import FileManager
        _FILE_MANAGER_INSTANCE = FileManager()
    return _FILE_MANAGER_INSTANCE


class FileSearchInput(BaseModel):
    pattern: str = Field(default="*", description="Glob search pattern, e.g. '*.pdf' or '*.py'.")
    directory: str = Field(default=".", description="Directory to search recursively.")


class FileSearchTool(TatsuTool):
    name = "file_search"
    description = "Search recursively for files matching a glob pattern within allowed directories."
    args_schema = FileSearchInput
    risk_level = RiskLevel.LOW

    def execute(self, args: Dict[str, Any]) -> str:
        pattern = args.get("pattern", "*")
        directory = args.get("directory", ".")
        fm = _get_file_manager()
        try:
            results = fm.search_files(pattern=pattern, directory=directory)
            audit_log("TOOL_EXECUTION", {"tool": self.name, "pattern": pattern, "matches": len(results)}, status="SUCCESS")
            return json.dumps(results, indent=2)
        except Exception as e:
            msg = f"Error during file search: {str(e)}"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "error": str(e)}, status="ERROR")
            return msg


class FileOrganizeInput(BaseModel):
    directory: str = Field(..., description="Target directory to organize into category subfolders.")
    criteria: str = Field(default="extension", description="Grouping criteria (default: 'extension').")
    confirm: bool = Field(default=False, description="Confirmation required if moving more than 5 files.")


class FileOrganizeTool(TatsuTool):
    name = "file_organize"
    description = "Organize loose files in a directory into category subfolders (documents, images, code, etc.)."
    args_schema = FileOrganizeInput
    risk_level = RiskLevel.MEDIUM

    def execute(self, args: Dict[str, Any]) -> str:
        directory = args.get("directory", "")
        criteria = args.get("criteria", "extension")
        confirm = bool(args.get("confirm", False))
        fm = _get_file_manager()
        try:
            res = fm.organize_directory(directory=directory, criteria=criteria, confirm=confirm)
            status = "BLOCKED" if "CONFIRMATION REQUIRED" in res else "SUCCESS"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "directory": directory}, status=status)
            return res
        except Exception as e:
            msg = f"Error organizing directory: {str(e)}"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "error": str(e)}, status="ERROR")
            return msg


class FileArchiveInput(BaseModel):
    file_list: List[str] = Field(..., description="List of file paths to compress into archive.")
    destination_zip: str = Field(..., description="Path to output zip archive file.")
    confirm: bool = Field(default=False, description="Confirmation required if archiving > 10 files.")


class FileArchiveTool(TatsuTool):
    name = "file_archive"
    description = "Compress a list of files into a ZIP archive."
    args_schema = FileArchiveInput
    risk_level = RiskLevel.MEDIUM

    def execute(self, args: Dict[str, Any]) -> str:
        file_list = args.get("file_list", [])
        destination_zip = args.get("destination_zip", "")
        confirm = bool(args.get("confirm", False))
        fm = _get_file_manager()
        try:
            res = fm.archive_files(file_list=file_list, destination_zip=destination_zip, confirm=confirm)
            status = "BLOCKED" if "CONFIRMATION REQUIRED" in res else "SUCCESS"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "dest": destination_zip}, status=status)
            return res
        except Exception as e:
            msg = f"Error creating archive: {str(e)}"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "error": str(e)}, status="ERROR")
            return msg


# ---------------------------------------------------------------------------
# 8. Smart Home / Hardware Bridge Tools (Phase 4)
# ---------------------------------------------------------------------------

_HARDWARE_BRIDGE = None


def _get_hardware_bridge():
    global _HARDWARE_BRIDGE
    if _HARDWARE_BRIDGE is None:
        from src.integration.hardware_bridge import get_hardware_bridge
        _HARDWARE_BRIDGE = get_hardware_bridge()
    return _HARDWARE_BRIDGE


class SmartHomeControlInput(BaseModel):
    device: str = Field(..., description="Device name or ID (e.g., 'desk_lamp', 'ceiling_fan').")
    action: str = Field(..., description="Target state: 'on', 'off', 'locked', 'unlocked', or numeric (temp/volume).")


class SmartHomeControlTool(TatsuTool):
    name = "control_smart_home"
    description = (
        "Control a smart home device (light, fan, lock, climate, audio). "
        "Set state to on/off/locked/unlocked or numeric value for temperature/volume."
    )
    args_schema = SmartHomeControlInput
    risk_level = RiskLevel.MEDIUM

    def execute(self, args: Dict[str, Any]) -> str:
        device = args.get("device", "")
        action = args.get("action", "")
        bridge = _get_hardware_bridge()
        result = bridge.set_device_state(device, action)
        if result.get("success"):
            msg = (
                f"Device '{result['device']}' changed from '{result['old_state']}' "
                f"to '{result['new_state']}' [{result['mode']}]"
            )
            audit_log("TOOL_EXECUTION", {"tool": self.name, "device": device, "action": action}, status="SUCCESS")
        else:
            msg = f"Device control failed: {result.get('error', 'unknown')}"
            audit_log("TOOL_EXECUTION", {"tool": self.name, "error": msg}, status="ERROR")
        return msg


class SmartHomeStatusInput(BaseModel):
    device: str = Field(default="", description="Device name/ID to query, or empty to list all.")


class SmartHomeStatusTool(TatsuTool):
    name = "smart_home_status"
    description = "Query the state of a smart home device, or list all devices and their states."
    args_schema = SmartHomeStatusInput
    risk_level = RiskLevel.LOW

    def execute(self, args: Dict[str, Any]) -> str:
        device = args.get("device", "").strip()
        bridge = _get_hardware_bridge()
        if device:
            result = bridge.get_device_state(device)
        else:
            result = bridge.list_devices()
        audit_log("TOOL_EXECUTION", {"tool": self.name, "device": device or "ALL"}, status="SUCCESS")
        return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Global Registry Map
# ---------------------------------------------------------------------------

AVAILABLE_TOOLS: Dict[str, TatsuTool] = {
    "shell_exec": ShellExecTool(),
    "file_read": FileReadTool(),
    "file_write": FileWriteTool(),
    "system_info": SystemInfoTool(),
    "run_python_script": RunPythonScriptTool(),
    "browser_navigate": BrowserNavigateTool(),
    "browser_extract": BrowserExtractTool(),
    "browser_click": BrowserClickTool(),
    "file_search": FileSearchTool(),
    "file_organize": FileOrganizeTool(),
    "file_archive": FileArchiveTool(),
    "control_smart_home": SmartHomeControlTool(),
    "smart_home_status": SmartHomeStatusTool(),
}

