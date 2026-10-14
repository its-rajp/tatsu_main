"""System Health Monitor for TATSU Sovereign Agent — Phase 1-B.

Gathers hardware metrics via psutil, tracks sustained thresholds,
and triggers non-blocking proactive alerts when stress is detected.
"""

import time
import yaml
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

import psutil

from src.proactive.alert_engine import AlertEngine

logger = logging.getLogger("TATSU.SystemMonitor")
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "monitoring.yaml"


class SystemMonitor:
    """Monitors system resource pressure and alerts the agent loop proactively."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        alert_engine: Optional[AlertEngine] = None,
    ):
        self.config = self._load_config(config_path or CONFIG_PATH)
        self.enabled = self.config.get("enabled", True)
        self.check_interval = int(self.config.get("check_interval_seconds", 10))

        thresholds = self.config.get("thresholds", {})
        self.cpu_threshold = float(thresholds.get("cpu_warning", 85.0))
        self.cpu_sustain_seconds = float(thresholds.get("cpu_sustain_seconds", 10.0))
        self.ram_threshold = float(thresholds.get("ram_critical", 95.0))
        self.disk_threshold = float(thresholds.get("disk_warning", 90.0))
        self.process_hung_cpu = float(thresholds.get("process_hung_cpu", 50.0))
        self.process_hung_seconds = float(thresholds.get("process_hung_seconds", 60.0))

        self.alert_engine = alert_engine

        # State tracking for sustained condition detection
        self._cpu_high_since: Optional[float] = None
        self._hung_processes_tracker: Dict[int, float] = {}  # pid -> first_detected_time
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _load_config(self, path: Path) -> dict:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Error loading {path}: {e}")
        return {
            "enabled": True,
            "check_interval_seconds": 10,
            "thresholds": {
                "cpu_warning": 85.0,
                "cpu_sustain_seconds": 10.0,
                "ram_critical": 95.0,
                "disk_warning": 90.0,
                "process_hung_cpu": 50.0,
                "process_hung_seconds": 60.0,
            },
        }

    def get_top_cpu_processes(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Gathers highest CPU consuming processes."""
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
            try:
                info = p.info
                if info and info.get("cpu_percent") is not None:
                    procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        procs.sort(key=lambda x: x.get("cpu_percent", 0.0) or 0.0, reverse=True)
        return procs[:limit]

    def check_health(self) -> Dict[str, Any]:
        """Gathers metrics, checks thresholds, and triggers alerts if needed."""
        now = time.time()

        # 1. Metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        ram_percent = mem.percent

        try:
            disk = psutil.disk_usage("/")
            disk_percent = disk.percent
        except Exception:
            disk_percent = 0.0

        top_procs = self.get_top_cpu_processes(limit=3)

        # 2. Evaluation
        # CPU Sustained check
        cpu_high = False
        if cpu_percent >= self.cpu_threshold:
            if self._cpu_high_since is None:
                self._cpu_high_since = now
            if (now - self._cpu_high_since) >= self.cpu_sustain_seconds:
                cpu_high = True
        else:
            self._cpu_high_since = None

        ram_critical = ram_percent >= self.ram_threshold
        disk_full = disk_percent >= self.disk_threshold

        # Hung / runaway process check
        hung_pid = None
        hung_name = None
        for proc in top_procs:
            pid = proc.get("pid")
            c_pct = proc.get("cpu_percent", 0.0) or 0.0
            if pid and c_pct >= self.process_hung_cpu:
                if pid not in self._hung_processes_tracker:
                    self._hung_processes_tracker[pid] = now
                elif (now - self._hung_processes_tracker[pid]) >= self.process_hung_seconds:
                    hung_pid = pid
                    hung_name = proc.get("name", "Unknown")
                    break

        # Clean dead PIDs from hung tracker
        current_pids = {p.get("pid") for p in top_procs}
        self._hung_processes_tracker = {
            p: t for p, t in self._hung_processes_tracker.items() if p in current_pids
        }

        status = {
            "cpu_high": cpu_high,
            "ram_critical": ram_critical,
            "disk_full": disk_full,
            "process_hung": hung_pid is not None,
            "details": {
                "cpu_percent": cpu_percent,
                "ram_percent": ram_percent,
                "disk_percent": disk_percent,
                "top_processes": top_procs,
            },
        }

        # 3. Trigger proactive alerts if AlertEngine is bound
        if self.alert_engine and self.enabled:
            if cpu_high:
                self.alert_engine.trigger_alert(
                    alert_type="cpu_warning",
                    severity="WARNING",
                    message=f"High CPU load sustained at {cpu_percent}%.",
                    suggestion="Would you like me to inspect and optimize background tasks?",
                    suggested_action={"tool": "system_info", "args": {"detailed": True}},
                )

            if ram_critical:
                self.alert_engine.trigger_alert(
                    alert_type="ram_critical",
                    severity="CRITICAL",
                    message=f"Memory critical: {ram_percent}% in use.",
                    suggestion="Would you like me to identify heavy memory consumers?",
                    suggested_action={"tool": "system_info", "args": {"detailed": True}},
                )

            if disk_full:
                self.alert_engine.trigger_alert(
                    alert_type="disk_warning",
                    severity="WARNING",
                    message=f"Root disk usage exceeded {disk_percent}%.",
                    suggestion="Would you like me to check temporary files or caches?",
                    suggested_action={"tool": "shell_exec", "args": {"command": "df -h"}},
                )

            if hung_pid:
                self.alert_engine.trigger_alert(
                    alert_type="process_hung",
                    severity="WARNING",
                    message=f"Process '{hung_name}' (PID {hung_pid}) is consuming heavy CPU continuously.",
                    suggestion=f"Shall I terminate process {hung_pid}?",
                    suggested_action={"tool": "shell_exec", "args": {"command": f"kill {hung_pid}"}},
                )

        return status

    def start_background_loop(self, interval_sec: Optional[int] = None) -> None:
        """Starts monitoring thread in the background."""
        if self._running:
            return

        interval = interval_sec or self.check_interval
        self._running = True

        def _monitor_loop():
            logger.info("System health monitoring loop started.")
            while self._running:
                try:
                    self.check_health()
                except Exception as e:
                    logger.debug(f"Health check cycle error: {e}")
                time.sleep(interval)
            logger.info("System health monitoring loop stopped.")

        self._thread = threading.Thread(target=_monitor_loop, daemon=True, name="TatsuSystemMonitor")
        self._thread.start()

    def stop_background_loop(self) -> None:
        """Stops the background monitoring loop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
