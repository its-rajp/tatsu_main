"""Hardware Bridge for TATSU — Phase 4.

Provides GPIO/Smart Home control. Detects real hardware (Raspberry Pi with
RPi.GPIO/gpiozero) and falls back to a simulated virtual device state machine
on Mac/laptop for demo purposes.

All device operations respect the authentication gate — only verified users
can toggle device states.
"""

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEVICE_STATE_PATH = BASE_DIR / "data" / "device_state.json"

# Detect real GPIO hardware
_GPIO_OK = False
_GPIO_LIB = None

try:
    import RPi.GPIO as GPIO
    _GPIO_OK = True
    _GPIO_LIB = "RPi.GPIO"
except ImportError:
    pass

if not _GPIO_OK:
    try:
        from gpiozero import LED, OutputDevice
        _GPIO_OK = True
        _GPIO_LIB = "gpiozero"
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Default Virtual Devices (for simulation on Mac/laptop)
# ---------------------------------------------------------------------------

DEFAULT_DEVICES = {
    "desk_lamp": {
        "name": "Desk Lamp",
        "type": "light",
        "state": "off",
        "gpio_pin": 17,
        "location": "desk",
    },
    "ceiling_fan": {
        "name": "Ceiling Fan",
        "type": "fan",
        "state": "off",
        "gpio_pin": 27,
        "location": "room",
    },
    "monitor_backlight": {
        "name": "Monitor Backlight",
        "type": "light",
        "state": "on",
        "gpio_pin": 22,
        "location": "desk",
    },
    "door_lock": {
        "name": "Front Door Lock",
        "type": "lock",
        "state": "locked",
        "gpio_pin": 23,
        "location": "entrance",
    },
    "ac_unit": {
        "name": "Air Conditioner",
        "type": "climate",
        "state": "off",
        "gpio_pin": 24,
        "temperature": 24,
        "location": "room",
    },
    "speaker_system": {
        "name": "Speaker System",
        "type": "audio",
        "state": "off",
        "volume": 50,
        "gpio_pin": 25,
        "location": "desk",
    },
}


class HardwareBridge:
    """Unified hardware control — real GPIO on Pi, virtual state machine elsewhere.

    Methods:
        set_device_state(device_name, state) — Toggle a device on/off/lock/unlock.
        get_device_state(device_name) — Query current device state.
        list_devices() — List all known devices and their states.
    """

    def __init__(self):
        self.is_real_hardware = _GPIO_OK
        self.gpio_lib = _GPIO_LIB
        self._lock = threading.RLock()
        self._devices: Dict[str, Dict[str, Any]] = {}
        self._gpio_pins: Dict[int, Any] = {}  # Active GPIO pin objects

        # Load persisted state or use defaults
        self._load_state()

        if self.is_real_hardware:
            self._init_gpio()
            print(f"[Hardware] Real GPIO detected ({self.gpio_lib}). Pins mapped.")
        else:
            print("[Hardware] No GPIO hardware detected. Running in SIMULATION mode.")

    def _load_state(self) -> None:
        """Load device state from disk, or initialize with defaults."""
        with self._lock:
            if DEVICE_STATE_PATH.exists():
                try:
                    with open(DEVICE_STATE_PATH, "r", encoding="utf-8") as f:
                        self._devices = json.load(f)
                    return
                except Exception:
                    pass
            # Initialize with defaults
            self._devices = json.loads(json.dumps(DEFAULT_DEVICES))
            self._save_state()

    def _save_state(self) -> None:
        """Persist device state to disk."""
        with self._lock:
            DEVICE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(DEVICE_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(self._devices, f, indent=2)

    def _init_gpio(self) -> None:
        """Initialize real GPIO pins (Raspberry Pi only)."""
        if not _GPIO_OK:
            return

        if _GPIO_LIB == "RPi.GPIO":
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for dev_id, dev in self._devices.items():
                pin = dev.get("gpio_pin")
                if pin is not None:
                    GPIO.setup(pin, GPIO.OUT)
                    # Set initial state
                    is_on = dev.get("state") in ("on", "unlocked")
                    GPIO.output(pin, GPIO.HIGH if is_on else GPIO.LOW)

        elif _GPIO_LIB == "gpiozero":
            from gpiozero import OutputDevice
            for dev_id, dev in self._devices.items():
                pin = dev.get("gpio_pin")
                if pin is not None:
                    device_obj = OutputDevice(pin)
                    self._gpio_pins[pin] = device_obj
                    is_on = dev.get("state") in ("on", "unlocked")
                    if is_on:
                        device_obj.on()
                    else:
                        device_obj.off()

    def list_devices(self) -> List[Dict[str, Any]]:
        """List all registered devices and their current states."""
        with self._lock:
            result = []
            for dev_id, dev in self._devices.items():
                entry = {"id": dev_id}
                entry.update(dev)
                entry["hardware_mode"] = "REAL" if self.is_real_hardware else "SIMULATED"
                result.append(entry)
            return result

    def get_device_state(self, device_name: str) -> Dict[str, Any]:
        """Query the current state of a specific device.

        Args:
            device_name: Device identifier (e.g., "desk_lamp") or display name.

        Returns:
            Device state dict, or error dict if not found.
        """
        with self._lock:
            # Search by ID first, then by display name
            dev = self._devices.get(device_name.lower().replace(" ", "_"))
            if dev is None:
                for dev_id, d in self._devices.items():
                    if d.get("name", "").lower() == device_name.lower():
                        dev = d
                        break

            if dev is None:
                return {"error": f"Device '{device_name}' not found.", "available": list(self._devices.keys())}

            result = dict(dev)
            result["hardware_mode"] = "REAL" if self.is_real_hardware else "SIMULATED"
            return result

    def set_device_state(self, device_name: str, state: str) -> Dict[str, Any]:
        """Set the state of a device (on/off, lock/unlock, or custom).

        Args:
            device_name: Device identifier or display name.
            state: Target state ("on", "off", "locked", "unlocked", or numeric for temperature/volume).

        Returns:
            Result dict with success status and new state.
        """
        from src.tools.registry import audit_log

        with self._lock:
            # Resolve device
            dev_id = device_name.lower().replace(" ", "_")
            dev = self._devices.get(dev_id)
            if dev is None:
                for did, d in self._devices.items():
                    if d.get("name", "").lower() == device_name.lower():
                        dev_id = did
                        dev = d
                        break

            if dev is None:
                return {
                    "success": False,
                    "error": f"Device '{device_name}' not found.",
                    "available": list(self._devices.keys()),
                }

            old_state = dev.get("state")
            normalized_state = state.lower().strip()

            # Handle numeric properties (temperature, volume)
            if dev.get("type") == "climate" and normalized_state.isdigit():
                dev["temperature"] = int(normalized_state)
                dev["state"] = "on"
                normalized_state = f"on (temp={normalized_state}°C)"
            elif dev.get("type") == "audio" and normalized_state.isdigit():
                dev["volume"] = min(100, max(0, int(normalized_state)))
                dev["state"] = "on"
                normalized_state = f"on (vol={dev['volume']}%)"
            else:
                dev["state"] = normalized_state

            # Drive real GPIO if available
            if self.is_real_hardware:
                self._drive_gpio(dev, normalized_state)

            self._save_state()

            audit_log("HARDWARE_CONTROL", {
                "device": dev_id,
                "old_state": old_state,
                "new_state": normalized_state,
                "mode": "REAL" if self.is_real_hardware else "SIMULATED",
            }, status="SUCCESS")

            return {
                "success": True,
                "device": dev.get("name"),
                "old_state": old_state,
                "new_state": normalized_state,
                "mode": "REAL" if self.is_real_hardware else "SIMULATED",
            }

    def _drive_gpio(self, dev: Dict[str, Any], state: str) -> None:
        """Actually drive the GPIO pin for real hardware."""
        pin = dev.get("gpio_pin")
        if pin is None:
            return

        is_on = state in ("on", "unlocked") or state.startswith("on ")

        if _GPIO_LIB == "RPi.GPIO":
            import RPi.GPIO as GPIO
            GPIO.output(pin, GPIO.HIGH if is_on else GPIO.LOW)
        elif _GPIO_LIB == "gpiozero":
            device_obj = self._gpio_pins.get(pin)
            if device_obj:
                if is_on:
                    device_obj.on()
                else:
                    device_obj.off()

    def add_device(self, device_id: str, device_config: Dict[str, Any]) -> Dict[str, Any]:
        """Register a new device dynamically.

        Args:
            device_id: Unique string identifier.
            device_config: Dict with at least 'name', 'type', 'state'.

        Returns:
            Success/error dict.
        """
        with self._lock:
            if device_id in self._devices:
                return {"success": False, "error": f"Device '{device_id}' already exists."}

            required = {"name", "type", "state"}
            if not required.issubset(device_config.keys()):
                return {"success": False, "error": f"Config must include: {required}"}

            self._devices[device_id] = device_config
            self._save_state()
            return {"success": True, "device": device_id}

    def cleanup(self) -> None:
        """Release GPIO resources on shutdown."""
        if self.is_real_hardware and _GPIO_LIB == "RPi.GPIO":
            try:
                import RPi.GPIO as GPIO
                GPIO.cleanup()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_BRIDGE_INSTANCE: Optional[HardwareBridge] = None
_BRIDGE_LOCK = threading.Lock()


def get_hardware_bridge() -> HardwareBridge:
    """Get or create the global HardwareBridge singleton."""
    global _BRIDGE_INSTANCE
    if _BRIDGE_INSTANCE is None:
        with _BRIDGE_LOCK:
            if _BRIDGE_INSTANCE is None:
                _BRIDGE_INSTANCE = HardwareBridge()
    return _BRIDGE_INSTANCE
