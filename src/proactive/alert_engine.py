"""Proactive Alert Engine for TATSU Sovereign Agent — Phase 1-B.

Responsible for:
- Logging proactive alerts into the tamper-evident audit ledger.
- Notifying the user politely via console, voice (TTS), or queued message.
- Holding actionable pending commands (e.g. `kill <PID>`) for subsequent user confirmation ("Yes, do it").
- Enforcing cooldown periods to prevent alert fatigue.
"""

import time
import logging
from typing import Dict, Any, Optional, Callable, List

from src.tools.registry import audit_log

logger = logging.getLogger("TATSU.AlertEngine")


class AlertEngine:
    """Proactive alert dispatcher with pending action memory and cooldowns."""

    def __init__(
        self,
        voice_callback: Optional[Callable[[str], None]] = None,
        cooldown_seconds: int = 60,
        polite_mode: bool = True,
    ):
        self.voice_callback = voice_callback
        self.cooldown_seconds = cooldown_seconds
        self.polite_mode = polite_mode
        self._last_alert_time: Dict[str, float] = {}
        self._pending_actions: List[Dict[str, Any]] = []

    def trigger_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        suggestion: str = "",
        suggested_action: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Dispatches an alert if cooldown has elapsed.
        
        Args:
            alert_type: Identifier (e.g. 'cpu_warning', 'ram_critical', 'disk_warning').
            severity: 'INFO', 'WARNING', or 'CRITICAL'.
            message: Human-readable alert description.
            suggestion: Recommended mitigation step.
            suggested_action: Structured tool action dict, e.g.
                              {"tool": "shell_exec", "args": {"command": "kill 12345"}}

        Returns:
            True if alert was emitted; False if silenced by cooldown.
        """
        now = time.time()
        last_fired = self._last_alert_time.get(alert_type, 0.0)
        if now - last_fired < self.cooldown_seconds:
            # Cooldown active; skip duplicate alert
            return False

        self._last_alert_time[alert_type] = now

        # 1. Log to tamper-evident audit ledger
        audit_payload = {
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
            "suggestion": suggestion,
            "has_suggested_action": bool(suggested_action),
        }
        audit_log("PROACTIVE_ALERT", audit_payload, status=severity)

        # 2. Store pending action in memory
        if suggested_action:
            pending_record = {
                "timestamp": now,
                "alert_type": alert_type,
                "suggestion": suggestion,
                "action": suggested_action,
            }
            self._pending_actions.append(pending_record)
            # Keep only latest 5 pending actions
            if len(self._pending_actions) > 5:
                self._pending_actions.pop(0)

        # 3. Format user notification
        full_announcement = (
            f"[TATSU Alert] {message} {suggestion}".strip()
            if self.polite_mode
            else f"ALERT ({severity}): {message} {suggestion}".strip()
        )

        print(f"\n⚡ {full_announcement}")

        # 4. Optional voice output if voice callback is configured
        if self.voice_callback:
            try:
                self.voice_callback(full_announcement)
            except Exception as e:
                logger.warning(f"Voice alert output failed: {e}")

        return True

    def get_latest_pending_action(self) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent pending proactive action."""
        if self._pending_actions:
            return self._pending_actions[-1]
        return None

    def pop_pending_action(self) -> Optional[Dict[str, Any]]:
        """Consumes the most recent pending action (e.g. when user says 'Yes, do it')."""
        if self._pending_actions:
            return self._pending_actions.pop()
        return None

    def clear_pending_actions(self) -> None:
        """Clears all stored pending actions."""
        self._pending_actions.clear()
