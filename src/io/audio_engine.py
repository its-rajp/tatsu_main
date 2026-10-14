"""Audio Engine for TATSU Sovereign Agent — Phase 0-B.

Provides Wake Word detection, local Speech-to-Text (STT), and Text-to-Speech (TTS).
All processing is fully local. No cloud APIs. Audio buffers are discarded after use.

Dependencies (installed lazily; graceful fallback to text mode if unavailable):
  - openwakeword       — lightweight offline wake word detection
  - faster-whisper     — CTranslate2 Whisper (int8 quantized, fast CPU inference)
  - piper-tts          — local neural TTS via ONNX
  - sounddevice        — cross-platform audio capture/playback
  - numpy              — array processing
"""

import io
import os
import sys
import wave
import time
import queue
import struct
import tempfile
import threading
import subprocess
from pathlib import Path
from typing import Optional, Callable

import numpy as np

# ---------------------------------------------------------------------------
# Lazy imports — fall back gracefully if not installed
# ---------------------------------------------------------------------------

_WAKE_OK = False
_STT_OK = False
_TTS_OK = False
_SD_OK = False

try:
    import sounddevice as sd
    _SD_OK = True
except ImportError:
    sd = None

try:
    import openwakeword
    from openwakeword.model import Model as OWWModel
    _WAKE_OK = True
except ImportError:
    OWWModel = None

try:
    from faster_whisper import WhisperModel
    _STT_OK = True
except ImportError:
    WhisperModel = None

try:
    import piper
    _TTS_OK = True
except ImportError:
    piper = None


BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = BASE_DIR / "models"


def _check_capability_report() -> dict:
    """Returns which audio subsystems are available."""
    return {
        "wake_word": _WAKE_OK,
        "stt": _STT_OK,
        "tts": _TTS_OK,
        "audio_io": _SD_OK,
    }


class TatsuAudio:
    """Full-local audio pipeline: wake word → auth → STT → (agent) → TTS."""

    # Audio capture parameters
    SAMPLE_RATE = 16000
    CHANNELS = 1
    DTYPE = "int16"
    WAKE_CHUNK_MS = 80           # ms per wake-word inference chunk
    RECORD_TIMEOUT_S = 8         # max seconds to record after wake
    SILENCE_CUTOFF_S = 1.5       # seconds of silence to auto-stop recording
    SILENCE_THRESHOLD = 500      # amplitude threshold for silence detection
    AUTH_CLIP_SECONDS = 2.0      # seconds of speech to capture for voice auth

    def __init__(
        self,
        wake_word: str = "hey_jarvis",
        whisper_model_size: str = "tiny.en",
        whisper_device: str = "cpu",
        whisper_compute_type: str = "int8",
        piper_voice: Optional[str] = None,
        enable_voice_auth: bool = True,
    ):
        self.wake_word = wake_word
        self.capabilities = _check_capability_report()
        self._running = False
        self._enable_voice_auth = enable_voice_auth

        # ----------- Voice Authentication (Phase 4) -----------
        self._voice_auth = None
        if enable_voice_auth:
            try:
                from src.security.biometric_auth import get_authenticator
                self._voice_auth = get_authenticator()
                if self._voice_auth.available:
                    print("[Audio] Voice authentication engine loaded (Resemblyzer).")
                else:
                    print("[Audio] Voice auth initialized (Resemblyzer not installed — auth bypass active).")
            except Exception as e:
                print(f"[Audio] Voice auth init failed ({e}); running without biometric gate.")
                self._voice_auth = None

        # ----------- Wake Word -----------
        self._oww_model = None
        if _WAKE_OK:
            try:
                openwakeword.utils.download_models()
                self._oww_model = OWWModel(
                    wakeword_models=[wake_word],
                    inference_framework="onnx",
                )
                print(f"[Audio] Wake word model loaded: '{wake_word}'")
            except Exception as e:
                print(f"[Audio] Wake word init failed ({e}); falling back to text input.")
                self._oww_model = None

        # ----------- STT (Whisper) -----------
        self._whisper = None
        if _STT_OK:
            try:
                self._whisper = WhisperModel(
                    whisper_model_size,
                    device=whisper_device,
                    compute_type=whisper_compute_type,
                )
                print(f"[Audio] Whisper STT loaded: {whisper_model_size} ({whisper_compute_type})")
            except Exception as e:
                print(f"[Audio] Whisper init failed ({e}); STT unavailable.")
                self._whisper = None

        # ----------- TTS (Piper) -----------
        self._piper_voice_path = piper_voice
        self._piper_available = False
        if _TTS_OK:
            self._piper_available = True
            print("[Audio] Piper TTS engine available.")

    # ------------------------------------------------------------------
    # Voice Authentication Helpers (Phase 4)
    # ------------------------------------------------------------------

    def _capture_auth_clip(self) -> Optional[np.ndarray]:
        """Capture a short audio clip specifically for voice authentication.
        Uses the first AUTH_CLIP_SECONDS of speech following wake word.
        """
        if not _SD_OK:
            return None

        chunk_samples = int(self.SAMPLE_RATE * 0.1)  # 100ms chunks
        frames = []
        max_chunks = int(self.AUTH_CLIP_SECONDS / 0.1)

        audio_queue: queue.Queue = queue.Queue()

        def _callback(indata, frame_count, time_info, status):
            audio_queue.put(indata.copy())

        try:
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                blocksize=chunk_samples,
                callback=_callback,
            ):
                for _ in range(max_chunks):
                    try:
                        data = audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    frames.append(data)
        except Exception as e:
            print(f"[Audio] Auth clip capture error: {e}")
            return None

        if not frames:
            return None
        return np.concatenate(frames, axis=0).flatten()

    def verify_speaker(self, audio_clip: Optional[np.ndarray] = None) -> bool:
        """Run voice-print verification on the given or freshly captured audio.

        Returns True if:
          - Voice auth is disabled or unavailable (bypass mode)
          - Session is already valid (within timeout window)
          - Speaker matches an enrolled, authorized user
        """
        if not self._voice_auth:
            return True  # No auth engine — bypass

        if not self._voice_auth.available:
            return True  # Resemblyzer not installed — bypass for dev

        # Check if session is still valid from a previous auth
        if self._voice_auth.session.is_session_valid():
            return True

        # Check lockout
        if self._voice_auth.session.is_locked_out():
            self.speak("Access denied. System is locked due to repeated failures. Please wait.")
            return False

        # Need to verify
        if audio_clip is None:
            print("🔐 Verifying identity...")
            audio_clip = self._capture_auth_clip()

        if audio_clip is None or len(audio_clip) < 1600:
            self.speak("Access denied. Could not capture voice sample.")
            return False

        result = self._voice_auth.authenticate(audio_clip)

        if result.get("success"):
            user = result.get("user", "unknown")
            score = result.get("score", 0)
            print(f"✅ Identity verified: {user} (confidence: {score:.2f})")
            return True
        else:
            reason = result.get("reason", "unknown")
            failures = result.get("failures", 0)
            if reason == "locked_out":
                remaining = result.get("remaining_seconds", 0)
                self.speak(f"Access denied. System locked for {remaining} seconds.")
            else:
                self.speak("Access denied. Identity not recognized.")
                print(f"🚫 Auth failed: {reason} (attempts: {failures})")
            return False

    @property
    def auth_session(self):
        """Access the current authentication session (for state injection)."""
        if self._voice_auth:
            return self._voice_auth.session
        return None

    @property
    def voice_authenticator(self):
        """Access the VoiceAuthenticator instance."""
        return self._voice_auth

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def listen_for_wake_word(self, timeout_s: float = 0.0) -> bool:
        """Blocks until wake word is detected. Returns True on detection.
        If wake word model is unavailable, returns True immediately (bypass).
        Set timeout_s > 0 for a bounded wait; 0 means wait forever.
        """
        if not self._oww_model or not _SD_OK:
            return True  # bypass — caller should use text fallback

        chunk_samples = int(self.SAMPLE_RATE * self.WAKE_CHUNK_MS / 1000)
        detected = threading.Event()
        start = time.time()

        def _audio_callback(indata, frames, time_info, status):
            if detected.is_set():
                return
            pcm = np.frombuffer(indata, dtype=np.int16)
            prediction = self._oww_model.predict(pcm)
            # prediction is a dict of model_name -> score
            for name, score in prediction.items():
                if score > 0.5:
                    detected.set()
                    return

        try:
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                blocksize=chunk_samples,
                callback=_audio_callback,
            ):
                while not detected.is_set():
                    if timeout_s > 0 and (time.time() - start) > timeout_s:
                        return False
                    detected.wait(0.05)
            return True
        except Exception as e:
            print(f"[Audio] Wake word listener error: {e}")
            return True  # fallback

    def record_speech(self) -> Optional[np.ndarray]:
        """Records speech from the microphone until silence is detected or timeout."""
        if not _SD_OK:
            return None

        chunk_samples = int(self.SAMPLE_RATE * 0.1)  # 100ms chunks
        frames = []
        silence_chunks = 0
        max_silence = int(self.SILENCE_CUTOFF_S / 0.1)
        max_chunks = int(self.RECORD_TIMEOUT_S / 0.1)

        audio_queue: queue.Queue = queue.Queue()

        def _callback(indata, frame_count, time_info, status):
            audio_queue.put(indata.copy())

        try:
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                blocksize=chunk_samples,
                callback=_callback,
            ):
                for _ in range(max_chunks):
                    try:
                        data = audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    frames.append(data)
                    amplitude = np.abs(data.astype(np.float32)).mean()
                    if amplitude < self.SILENCE_THRESHOLD:
                        silence_chunks += 1
                    else:
                        silence_chunks = 0
                    if silence_chunks >= max_silence:
                        break
        except Exception as e:
            print(f"[Audio] Recording error: {e}")
            return None

        if not frames:
            return None

        return np.concatenate(frames, axis=0).flatten()

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribes recorded audio to text using Whisper locally."""
        if self._whisper is None:
            return ""

        try:
            # faster-whisper expects float32 normalised to [-1, 1]
            audio_f32 = audio.astype(np.float32) / 32768.0
            segments, info = self._whisper.transcribe(
                audio_f32,
                beam_size=1,
                language="en",
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return text
        except Exception as e:
            print(f"[Audio] Transcription error: {e}")
            return ""

    def speak(self, text: str) -> None:
        """Synthesizes speech from text using Piper TTS and plays it."""
        if not text:
            return

        # Try Piper TTS
        if self._piper_available:
            try:
                self._speak_piper(text)
                return
            except Exception as e:
                print(f"[Audio] Piper TTS failed ({e}); trying macOS fallback.")

        # Fallback: macOS `say` command
        if sys.platform == "darwin":
            try:
                subprocess.run(
                    ["say", "-r", "190", text],
                    timeout=30,
                    capture_output=True,
                )
                return
            except Exception as e:
                print(f"[Audio] macOS say failed: {e}")

        # Last resort: just print
        print(f"[TATSU speaks]: {text}")

    def _speak_piper(self, text: str) -> None:
        """Synthesize and play audio via piper-tts."""
        if not _TTS_OK:
            raise RuntimeError("Piper not installed")

        # Use piper CLI if the python bindings are complex
        # piper --model <model> --output_file - | aplay -
        voice_arg = []
        if self._piper_voice_path:
            voice_arg = ["--model", str(self._piper_voice_path)]

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            proc = subprocess.run(
                ["piper", *voice_arg, "--output_file", tmp.name],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=15,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"Piper exit {proc.returncode}: {proc.stderr.decode()}")

            if _SD_OK:
                import soundfile as sf
                data, sr = sf.read(tmp.name, dtype="float32")
                sd.play(data, sr)
                sd.wait()

    def listen_once(self) -> str:
        """Full pipeline: wake word → voice auth → record → transcribe → return text.

        Phase 4 Enhancement: After wake word detection, the first 2 seconds of
        speech are used for voice-print verification. If the speaker is not
        recognized, the command is rejected before reaching the agent core.
        Falls back to text input if audio subsystems are unavailable.
        """
        # Check if we have minimal audio capability
        if not _SD_OK or (not self._oww_model and not self._whisper):
            return self._text_fallback()

        print(f"\n🎙️  Listening for wake word ('{self.wake_word}')...")
        detected = self.listen_for_wake_word()
        if not detected:
            return ""

        # --- Phase 4: Voice Authentication Gate ---
        # Verify speaker identity before processing the command.
        # If session is already authenticated (within timeout), skip re-verification.
        if self._enable_voice_auth and self._voice_auth:
            if not self.verify_speaker():
                return ""  # Rejected — do not proceed to STT

        print("🔴 Recording... (speak now)")
        audio = self.record_speech()
        if audio is None or len(audio) == 0:
            print("⚠️  No audio captured.")
            return ""

        print("⏳ Transcribing...")
        text = self.transcribe(audio)
        if text:
            print(f"📝 Heard: \"{text}\"")
        else:
            print("⚠️  Could not transcribe audio.")
        return text

    def _text_fallback(self) -> str:
        """Text input fallback when audio hardware/libraries are unavailable."""
        missing = [k for k, v in self.capabilities.items() if not v]
        if missing:
            print(f"[Audio] Text mode active (missing: {', '.join(missing)})")
        try:
            return input("\n🐉 TATSU > ").strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    @property
    def has_voice(self) -> bool:
        """True if at least wake word OR STT is functional."""
        return bool(self._oww_model or self._whisper)

    @property
    def has_tts(self) -> bool:
        """True if TTS output is available (piper or macOS say)."""
        return self._piper_available or sys.platform == "darwin"
