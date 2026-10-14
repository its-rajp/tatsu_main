"""Tests for Phase 5: System Optimization, Latency Profiling, and Red-Team Certification."""

import json
import os
import pytest
from pathlib import Path

from src.utils.latency_optimizer import (
    PipelineProfiler,
    IntentCache,
    chunk_response,
    generate_startup_greeting,
    StreamingTTSController,
)
from tests.red_team_suite import run_red_team_benchmark, ATTACK_VECTORS


def test_profiler_stage_timing():
    """Verify PipelineProfiler measures and records execution latency."""
    profiler = PipelineProfiler()
    with profiler.profile_stage("test_stage"):
        # simple work
        _ = sum(i * i for i in range(1000))
    summary = profiler.get_summary()
    assert "test_stage" in summary
    assert summary["test_stage"] > 0
    assert profiler.total_latency() >= summary["test_stage"]


def test_intent_cache_hit_and_miss():
    """Verify IntentCache stores and matches fast-path queries."""
    cache = IntentCache()
    # Cache hit
    hit, resp = cache.get("what time is it")
    assert hit is True
    assert "It's" in resp or "time" in resp.lower()

    # Cache miss
    hit_miss, resp_miss = cache.get("run a complex script to analyze data")
    assert hit_miss is False
    assert resp_miss is None

    # Custom entry
    cache.set("who are you", "I am TATSU.")
    hit_custom, resp_custom = cache.get("who are you")
    assert hit_custom is True
    assert resp_custom == "I am TATSU."


def test_streaming_tts_chunk_response():
    """Verify response chunking creates sentence-level tokens."""
    long_text = "Hello Raj. System diagnostics are fully nominal! How may I assist you today? All nodes ready."
    chunks = chunk_response(long_text)
    assert len(chunks) == 4
    assert chunks[0] == "Hello Raj."
    assert "diagnostics" in chunks[1]


def test_streaming_tts_controller():
    """Verify StreamingTTSController calls audio playback per chunk."""
    played = []

    class MockAudioEngine:
        def speak(self, text: str) -> None:
            played.append(text)

    controller = StreamingTTSController(audio_engine=MockAudioEngine())
    controller.feed("First sentence. Second sentence! Third?")
    controller.flush()
    assert len(played) == 3
    assert played[0] == "First sentence."
    assert played[1] == "Second sentence!"
    assert played[2] == "Third?"


def test_startup_greeting():
    """Verify generate_startup_greeting respects persona and tone."""
    greeting = generate_startup_greeting("Raj", is_authenticated=True)
    assert "Raj" in greeting
    assert len(greeting.split("\n")) <= 4


def test_red_team_defense_integrity():
    """Verify red team benchmark achieves >= 95% defense integrity score."""
    result = run_red_team_benchmark(verbose=False)
    assert result["score"] >= 95.0
    assert result["failed"] == 0
    assert result["total_vectors"] == len(ATTACK_VECTORS)
