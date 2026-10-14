"""Test suite for Phase 0-B: Audio Engine & Unified Entry Point."""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.io.audio_engine import TatsuAudio, _check_capability_report


def test_audio_engine_capabilities():
    print("=== Testing Audio Engine Capabilities & Fallbacks ===")
    caps = _check_capability_report()
    assert isinstance(caps, dict)
    assert "wake_word" in caps
    assert "stt" in caps
    assert "tts" in caps
    assert "audio_io" in caps
    print("[PASS] Capability report generated:", caps)


def test_audio_engine_initialization():
    print("\n=== Testing TatsuAudio Instance Initialization ===")
    engine = TatsuAudio(
        wake_word="hey_jarvis",
        whisper_model_size="tiny.en",
        whisper_device="cpu",
    )
    assert engine.wake_word == "hey_jarvis"
    assert engine._running is False
    print("[PASS] TatsuAudio initialized successfully.")


def test_audio_engine_fallback_tts():
    print("\n=== Testing TatsuAudio TTS / Fallback ===")
    engine = TatsuAudio()
    # Speak a short test phrase; should not raise exception (falls back to say or print)
    engine.speak("TATSU Phase zero audio test verified.")
    print("[PASS] Audio engine speak completed without error.")


def run_all():
    test_audio_engine_capabilities()
    test_audio_engine_initialization()
    test_audio_engine_fallback_tts()
    print("\n✅ ALL PHASE 0-B AUDIO TESTS PASSED.")


if __name__ == "__main__":
    run_all()
