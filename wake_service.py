"""
Wake Word Service for TATSU AI Companion
========================================
A lightweight background listener that waits for the phrase "wake up tatsu" or "hey tatsu"
and automatically launches TATSU (main.py) if it is not already running.

Usage:
    python wake_service.py
    
Add to Windows Startup for always-on wake word detection:
    1. Press Win+R, type "shell:startup"
    2. Create a shortcut to: pythonw.exe "C:\\path\\to\\wake_service.py"
"""

import os
import sys
import time
import subprocess
import threading
from pathlib import Path

import psutil

# ── Configuration ─────────────────────────────────────────────────────────────
WAKE_PHRASES = [
    "wake up tatsu",
    "tatsu wake up",
    "hey tatsu",
    "tatsu",
    "wake up",
    "wakey wakey",
    "wake up ultron",
    "hey ultron",
]

# How many seconds of audio to capture per recognition attempt
LISTEN_TIMEOUT  = 3
PHRASE_TIMEOUT   = 5
CHECK_INTERVAL   = 1.0     # seconds between listen cycles
COOLDOWN_AFTER_LAUNCH = 15  # seconds to wait after launching before listening again

BASE_DIR = Path(__file__).resolve().parent
MAIN_SCRIPT = BASE_DIR / "main.py"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_tatsu_running() -> bool:
    """Check if main.py is already running via socket probe to port 39153."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 39153), timeout=0.1):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

_is_ultron_running = _is_tatsu_running


def _launch_tatsu() -> bool:
    """Launch TATSU main.py in a new detached process."""
    python = sys.executable
    # On Windows, use pythonw.exe to avoid console window
    pythonw = Path(python).parent / "pythonw.exe"
    if pythonw.exists():
        exe = str(pythonw)
    else:
        exe = python

    try:
        if sys.platform == "win32":
            subprocess.Popen(
                [exe, str(MAIN_SCRIPT), "--wake-word"],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
                cwd=str(BASE_DIR),
            )
        else:
            subprocess.Popen(
                [exe, str(MAIN_SCRIPT), "--wake-word"],
                start_new_session=True,
                cwd=str(BASE_DIR),
            )
        return True
    except Exception as e:
        print(f"[WakeService] ❌ Launch error: {e}")
        return False

_launch_ultron = _launch_tatsu


def _log(msg: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [WakeService] {msg}")


# ── Main Service Loop ─────────────────────────────────────────────────────────

def main():
    """
    Continuously listens for the wake phrase using SpeechRecognition
    with the Google Web Speech API (free, no key required).
    Falls back to offline Vosk if available.
    """
    try:
        import speech_recognition as sr
    except ImportError:
        print("=" * 60)
        print("  SpeechRecognition is required for the wake service.")
        print("  Install it with:  pip install SpeechRecognition PyAudio")
        print("=" * 60)
        sys.exit(1)

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300       # sensitivity (lower = more sensitive)
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.8

    # Try to find a microphone
    try:
        mic = sr.Microphone()
    except Exception as e:
        print(f"[WakeService] ❌ No microphone found: {e}")
        print("[WakeService] Make sure PyAudio is installed: pip install PyAudio")
        sys.exit(1)

    _log("🎙️  Wake word service started")
    _log(f"📂 TATSU script: {MAIN_SCRIPT}")
    _log(f"🔑 Wake phrases: {', '.join(WAKE_PHRASES)}")
    _log("👂 Listening...")

    # Initial calibration for ambient noise
    with mic as source:
        _log("🔧 Calibrating for ambient noise (2 seconds)...")
        recognizer.adjust_for_ambient_noise(source, duration=2)
        _log("✅ Calibration complete. Listening for wake word...")

    while True:
        try:
            with mic as source:
                try:
                    audio = recognizer.listen(
                        source,
                        timeout=LISTEN_TIMEOUT,
                        phrase_time_limit=PHRASE_TIMEOUT,
                    )
                except sr.WaitTimeoutError:
                    # No speech detected in this window — loop again
                    continue

            # Optional VAD pre-filter
            try:
                import audioop
                rms = audioop.rms(audio.frame_data, audio.sample_width)
                if rms < recognizer.energy_threshold:
                    continue
            except Exception:
                pass

            # Try to recognize speech
            text = ""
            try:
                # Google Web Speech API (free, no API key)
                text = recognizer.recognize_google(audio, language="en-US")
            except sr.UnknownValueError:
                # Could not understand audio
                continue
            except sr.RequestError:
                # API error — try offline Vosk if available
                try:
                    text = recognizer.recognize_vosk(audio)
                except Exception:
                    _log("⚠️  Speech API unavailable and no offline fallback")
                    time.sleep(5)
                    continue

            if not text:
                continue

            text_lower = text.lower().strip()
            _log(f"🗣️  Heard: \"{text_lower}\"")

            # Check if any wake phrase is in the recognized text
            wake_detected = any(phrase in text_lower for phrase in WAKE_PHRASES)

            if wake_detected:
                _log("🚀 Wake word detected!")

                if _is_tatsu_running():
                    _log("✅ TATSU is already running — no action needed.")
                else:
                    _log("🔄 TATSU is not running — launching now...")
                    success = _launch_tatsu()
                    if success:
                        _log("✅ TATSU launched successfully!")
                        _log(f"⏳ Cooling down for {COOLDOWN_AFTER_LAUNCH}s...")
                        time.sleep(COOLDOWN_AFTER_LAUNCH)
                    else:
                        _log("❌ Failed to launch TATSU.")

        except KeyboardInterrupt:
            _log("🛑 Wake service stopped by user.")
            break
        except Exception as e:
            _log(f"⚠️  Error: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()
