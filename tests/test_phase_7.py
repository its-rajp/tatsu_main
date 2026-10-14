"""Tests for Phase 7: The Polyglot Core (Hindi-English Dual-Language Routing & British Jarvis TTS)."""

import pytest
from src.io.language_detector import (
    detect_language,
    get_language_details,
    format_multilingual_prompt_guidance,
    has_devanagari,
    count_hinglish_markers,
)
from src.io.audio_engine import TatsuAudio, PolyglotVoiceEngine
from src.core.agent_graph import perceive_node
from src.core.state import AgentState
from src.utils.latency_optimizer import IntentCache, generate_startup_greeting


# ---------------------------------------------------------------------------
# Test 1: Language Detection
# ---------------------------------------------------------------------------

def test_language_detection_hindi_devanagari():
    """Verify pure Devanagari Hindi is classified as 'hi'."""
    samples = [
        "नमस्ते तातसु, आप कैसे हैं?",
        "मेरा लैपटॉप बहुत धीमा चल रहा है, क्या करूँ?",
        "सिस्टम की स्थिति बताओ।",
        "डिस्क स्पेस चेक करो।",
    ]
    for text in samples:
        assert detect_language(text) == "hi", f"Failed to detect Hindi for: {text}"
        assert has_devanagari(text) is True


def test_language_detection_hinglish():
    """Verify conversational Hinglish (Romanized Hindi) is classified as 'hinglish'."""
    samples = [
        "Tatsu, mera laptop thoda slow chal raha hai, kya karun?",
        "Mera system check karo aur batao kya issue hai.",
        "Python script run kardo please.",
        "Chrome ko band karo aur RAM free karo.",
        "Bhai CPU load check karoge?",
        "Namaste Tatsu, aaj ka status kya hai?",
    ]
    for text in samples:
        assert detect_language(text) == "hinglish", f"Failed to detect Hinglish for: {text}"


def test_language_detection_english():
    """Verify standard English commands are classified as 'en'."""
    samples = [
        "Check my disk space and memory usage immediately.",
        "List all running processes consuming more than 5% CPU.",
        "What time is it in Tokyo right now?",
        "Organize my downloads folder and remove temporary archives.",
    ]
    for text in samples:
        assert detect_language(text) == "en", f"Failed to detect English for: {text}"


def test_language_details_telemetry():
    """Verify linguistic telemetry breakdown."""
    info = get_language_details("Tatsu mera laptop slow chal raha hai")
    assert info["language"] == "hinglish"
    assert info["script"] == "latin_transliterated"
    assert info["confidence"] > 0.60
    assert info["hinglish_marker_count"] >= 3

    info_hi = get_language_details("नमस्ते तातसु")
    assert info_hi["language"] == "hi"
    assert info_hi["script"] == "devanagari"
    assert info_hi["devanagari_char_count"] > 0


# ---------------------------------------------------------------------------
# Test 2: British Jarvis Voice Engine Tuning & Cadence Modulation
# ---------------------------------------------------------------------------

def test_british_jarvis_voice_profile():
    """Verify Piper parameters match Varahamihira's sovereign British delivery."""
    engine = TatsuAudio()
    cfg = engine.voice_config
    assert cfg["profile"] == "jarvis_british"
    assert cfg["length_scale"] == 1.05   # Slower, measured cadence
    assert cfg["noise_scale"] == 0.667   # Low breathiness, high clarity
    assert cfg["noise_w_scale"] == 0.8   # Controlled monotone prosody


def test_dynamic_cadence_modulation():
    """Verify speech rate modulates with emotional/system state."""
    engine = TatsuAudio()
    # Nominal state
    assert engine.tune_cadence("nominal") == 1.05
    assert engine.voice_config["length_scale"] == 1.05

    # Stressed state -> slower pace to calm user
    assert engine.tune_cadence("stressed") == 1.15
    assert engine.voice_config["length_scale"] == 1.15

    # Excited/urgent state -> crisper pace
    assert engine.tune_cadence("excited") == 0.95
    assert engine.voice_config["length_scale"] == 0.95


def test_polyglot_voice_engine_fallback():
    """Verify PolyglotVoiceEngine executes without errors in headless/simulation environments."""
    polyglot = PolyglotVoiceEngine()
    # English call
    polyglot.speak_english("Diagnostic sequence initiated. All subsystems nominal, sir.")
    # Hindi call
    polyglot.speak_hindi("नमस्ते राज, सिस्टम तैयार है।")
    # Auto-detect routing
    polyglot.speak("Mera laptop kaisa chal raha hai?")


# ---------------------------------------------------------------------------
# Test 3: Agent Graph Multilingual Routing
# ---------------------------------------------------------------------------

def test_agent_graph_language_routing_english():
    """Verify English task routes to standard sovereign English model."""
    state = AgentState(
        current_task="Check the free disk space on the root partition.",
        messages=[],
        observations=[],
    )
    result = perceive_node(state)
    assert result["detected_lang"] == "en"
    assert "llama3.2" in result["target_model"]
    sys_prompt = result["messages"][0].content
    assert "BRITISH SOVEREIGN" in sys_prompt


def test_agent_graph_language_routing_hindi():
    """Verify Hindi task routes to multilingual model and Hindi prompt guidance."""
    state = AgentState(
        current_task="नमस्ते तातसु, डिस्क में कितना स्पेस बचा है?",
        messages=[],
        observations=[],
    )
    result = perceive_node(state)
    assert result["detected_lang"] == "hi"
    assert "aya-expanse" in result["target_model"]
    sys_prompt = result["messages"][0].content
    assert "HINDI ACTIVE" in sys_prompt


def test_agent_graph_language_routing_hinglish():
    """Verify Hinglish task routes to multilingual model and Hinglish guidance."""
    state = AgentState(
        current_task="Tatsu, mera CPU usage check karke batao please.",
        messages=[],
        observations=[],
    )
    result = perceive_node(state)
    assert result["detected_lang"] == "hinglish"
    assert "aya-expanse" in result["target_model"]
    sys_prompt = result["messages"][0].content
    assert "HINGLISH ACTIVE" in sys_prompt


# ---------------------------------------------------------------------------
# Test 4: Bilingual Fast-Path Intents & Greetings
# ---------------------------------------------------------------------------

def test_intent_cache_hindi():
    """Verify IntentCache handles fast-path queries in Hindi/Hinglish."""
    cache = IntentCache()
    hit_time, resp_time = cache.get("samay kya hai")
    assert hit_time is True
    assert "समय" in resp_time

    hit_greet, resp_greet = cache.get("namaste tatsu")
    assert hit_greet is True
    assert "नमस्ते" in resp_greet

    hit_who, resp_who = cache.get("tum kaun ho")
    assert hit_who is True
    assert "तातसु" in resp_who


def test_bilingual_startup_greeting():
    """Verify startup greeting can generate Hindi/Hinglish output."""
    greeting_hi = generate_startup_greeting("Raj", is_authenticated=True, language="hi")
    assert "राज" in greeting_hi or "Raj" in greeting_hi
    assert "तातसु" in greeting_hi
