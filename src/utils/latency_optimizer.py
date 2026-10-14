"""Latency Optimizer & Async Pipeline for TATSU — Phase 5.

Provides:
1. End-to-end pipeline profiler: measures wake→STT→reason→tool→TTS latency.
2. Intent cache: bypasses LLM for frequent static queries (time, status, greetings).
3. Streaming TTS: starts speaking the first sentence while LLM continues generating.
4. Response chunker: splits LLM output into speakable sentence fragments.

All optimizations are local-only. No cloud dependencies.
"""

import re
import time
import threading
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Pipeline Profiler
# ---------------------------------------------------------------------------

class PipelineProfiler:
    """Measures and reports latency across each stage of the TATSU pipeline.

    Usage:
        profiler = PipelineProfiler()
        profiler.start("wake_word")
        ... detect wake word ...
        profiler.stop("wake_word")
        profiler.start("stt")
        ... transcribe ...
        profiler.stop("stt")
        report = profiler.report()
    """

    def __init__(self):
        self._timers: Dict[str, float] = {}
        self._results: Dict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    def start(self, stage: str) -> None:
        """Begin timing a pipeline stage."""
        with self._lock:
            self._timers[stage] = time.perf_counter()

    def stop(self, stage: str) -> float:
        """End timing a pipeline stage. Returns elapsed milliseconds."""
        with self._lock:
            start_time = self._timers.pop(stage, None)
            if start_time is None:
                return 0.0
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._results[stage] = elapsed_ms
            return elapsed_ms

    @contextmanager
    def profile_stage(self, stage: str):
        """Context manager to measure latency of a stage."""
        self.start(stage)
        try:
            yield
        finally:
            self.stop(stage)

    def get_summary(self) -> Dict[str, float]:
        """Return dict of stage names to latency in milliseconds."""
        with self._lock:
            return dict(self._results)

    def total_latency(self) -> float:
        """Return total elapsed latency in milliseconds across all completed stages."""
        with self._lock:
            return sum(self._results.values())

    def reset(self) -> None:
        """Clear all timing data."""
        with self._lock:
            self._timers.clear()
            self._results.clear()

    def report(self) -> Dict[str, Any]:
        """Generate a latency report across all measured stages."""
        with self._lock:
            total_ms = sum(self._results.values())
            stages = []
            for stage, ms in self._results.items():
                pct = (ms / total_ms * 100) if total_ms > 0 else 0
                stages.append({
                    "stage": stage,
                    "latency_ms": round(ms, 2),
                    "percent": round(pct, 1),
                })

            return {
                "total_ms": round(total_ms, 2),
                "stages": stages,
                "bottleneck": max(stages, key=lambda s: s["latency_ms"])["stage"] if stages else None,
                "timestamp": datetime.utcnow().isoformat(),
            }

    def summary_str(self) -> str:
        """Human-readable latency summary."""
        r = self.report()
        lines = ["╔══ TATSU Pipeline Latency Report ══╗"]
        for s in r["stages"]:
            bar = "█" * int(s["percent"] / 5)
            lines.append(f"  {s['stage']:.<20s} {s['latency_ms']:>8.1f}ms ({s['percent']:>5.1f}%) {bar}")
        lines.append(f"  {'TOTAL':.<20s} {r['total_ms']:>8.1f}ms")
        if r["bottleneck"]:
            lines.append(f"  ⚠ Bottleneck: {r['bottleneck']}")
        lines.append("╚═══════════════════════════════════╝")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Intent Cache — Bypass LLM for Common Static Queries
# ---------------------------------------------------------------------------

# Pattern → handler mapping. Each handler returns a string response.
_INTENT_PATTERNS: List[Tuple[re.Pattern, Callable[[], str]]] = []


def _time_response() -> str:
    now = datetime.now()
    return f"It's {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d, %Y')}."


def _date_response() -> str:
    now = datetime.now()
    return f"Today is {now.strftime('%A, %B %d, %Y')}."


def _greeting_response() -> str:
    hour = datetime.now().hour
    if hour < 12:
        period = "Good morning"
    elif hour < 17:
        period = "Good afternoon"
    else:
        period = "Good evening"
    return f"{period}, sir. TATSU is ready and operational."


def _status_response() -> str:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        return f"System nominal. CPU: {cpu}%, Memory: {mem}%."
    except Exception:
        return "System status: operational."


def _identity_response() -> str:
    return (
        "I am TATSU — your sovereign digital companion. "
        "Locally hosted, biometrically secured, and fully autonomous."
    )


def _hindi_time_response() -> str:
    now = datetime.now()
    return f"अभी समय {now.strftime('%I:%M %p')} है।"


def _hindi_greeting_response() -> str:
    return "नमस्ते, मैं तातसु हूँ। आपकी सेवा के लिए पूर्णतः तैयार और संप्रभु।"


def _hindi_identity_response() -> str:
    return "मैं तातसु हूँ — आपका स्थानीय, सुरक्षित और स्वायत्त डिजिटल साथी।"


# Register default intent patterns (Bilingual English & Hindi/Hinglish)
_INTENT_PATTERNS = [
    (re.compile(r"^(what('?s| is) (the )?time|what time is it|time)\??$", re.I), _time_response),
    (re.compile(r"^(what('?s| is) (the )?date|what date is it|date)\??$", re.I), _date_response),
    (re.compile(r"^(hey|hi|hello|good (morning|afternoon|evening))\b", re.I), _greeting_response),
    (re.compile(r"^(system )?status\??$", re.I), _status_response),
    (re.compile(r"^who are you\??$", re.I), _identity_response),
    (re.compile(r"^what('?s| is) your name\??$", re.I), _identity_response),
    # Hindi & Hinglish Fast-Path Intents
    (re.compile(r"^(kya samay hua hai|samay kya hai|time kya hai|kya time hai)\??$", re.I), _hindi_time_response),
    (re.compile(r"^(namaste|namaskar|pranam|hello tatsu|namaste tatsu)\b", re.I), _hindi_greeting_response),
    (re.compile(r"^(tum kaun ho|aap kaun hain|tatsu kaun hai)\??$", re.I), _hindi_identity_response),
]


class IntentCache:
    """Fast-path cache that matches known static intents and returns
    pre-computed responses without invoking the LLM.

    Reduces latency by ~200-500ms for trivial queries.
    """

    def __init__(self, extra_patterns: Optional[List[Tuple[re.Pattern, Callable]]] = None):
        self._patterns = list(_INTENT_PATTERNS)
        if extra_patterns:
            self._patterns.extend(extra_patterns)
        self._hit_count = 0
        self._miss_count = 0
        self._lock = threading.Lock()

    def match(self, query: str) -> Optional[str]:
        """Try to match query against cached intents.

        Returns response string if matched, None if LLM reasoning is needed.
        """
        cleaned = query.strip().rstrip("!.")
        for pattern, handler in self._patterns:
            if pattern.search(cleaned):
                with self._lock:
                    self._hit_count += 1
                try:
                    return handler()
                except Exception:
                    return None

        with self._lock:
            self._miss_count += 1
        return None

    def get(self, query: str) -> Tuple[bool, Optional[str]]:
        """Check cache for query. Returns (hit: bool, response: Optional[str])."""
        res = self.match(query)
        return (res is not None, res)

    def set(self, query_pattern: str, response: str) -> None:
        """Add a static response pattern to the cache."""
        pattern = re.compile(rf"^{re.escape(query_pattern)}\??$", re.I)
        with self._lock:
            self._patterns.insert(0, (pattern, lambda: response))

    @property
    def stats(self) -> Dict[str, int]:
        with self._lock:
            total = self._hit_count + self._miss_count
            return {
                "hits": self._hit_count,
                "misses": self._miss_count,
                "total": total,
                "hit_rate_pct": round(self._hit_count / total * 100, 1) if total > 0 else 0,
            }


# ---------------------------------------------------------------------------
# Response Chunker — Sentence-Level Streaming for TTS
# ---------------------------------------------------------------------------

# Sentence boundary pattern — splits on . ! ? followed by space or end
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+|(?<=[.!?])$')


def chunk_response(text: str) -> List[str]:
    """Split a response into sentence-level chunks for streaming TTS.

    This enables speaking the first sentence while the LLM is still
    generating subsequent sentences, reducing perceived latency by ~40%.

    Args:
        text: Full response text from the LLM.

    Returns:
        List of sentence strings, each suitable for independent TTS synthesis.
    """
    if not text:
        return []

    # Split on sentence boundaries
    sentences = _SENTENCE_RE.split(text.strip())
    # Filter empty and whitespace-only chunks
    chunks = [s.strip() for s in sentences if s.strip()]

    # If no sentence boundaries found, return the whole text as one chunk
    if not chunks:
        return [text.strip()]

    return chunks


class StreamingTTSController:
    """Manages streaming TTS output — speaks sentences as they arrive
    rather than waiting for the full response.

    Usage:
        controller = StreamingTTSController(tts_func=audio_engine.speak)
        controller.feed("First sentence.")
        controller.feed("Second sentence.")
        controller.finish()
    """

    def __init__(self, tts_func: Optional[Callable[[str], None]] = None, audio_engine: Optional[Any] = None):
        if tts_func is None and audio_engine is not None:
            tts_func = getattr(audio_engine, "speak", None)
        if tts_func is None:
            raise ValueError("Either tts_func or audio_engine must be provided")
        self._tts_func = tts_func
        self._queue: List[str] = []
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._started = False

    def feed(self, text: str) -> None:
        """Feed a text chunk for immediate TTS synthesis."""
        sentences = chunk_response(text)
        with self._lock:
            self._queue.extend(sentences)

        if not self._started:
            self._started = True
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def _worker(self) -> None:
        """Background worker that speaks queued sentences."""
        while not self._stop_event.is_set():
            sentence = None
            with self._lock:
                if self._queue:
                    sentence = self._queue.pop(0)

            if sentence:
                try:
                    self._tts_func(sentence)
                except Exception as e:
                    print(f"[StreamTTS] Error: {e}")
            else:
                time.sleep(0.05)  # Brief wait for more content

    def finish(self) -> None:
        """Wait for all queued sentences to be spoken, then stop."""
        # Drain remaining queue
        while True:
            with self._lock:
                if not self._queue:
                    break
            time.sleep(0.05)

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._started = False
        self._stop_event.clear()

    def flush(self) -> None:
        """Alias for finish()."""
        self.finish()

    def cancel(self) -> None:
        """Immediately stop TTS output."""
        with self._lock:
            self._queue.clear()
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._started = False
        self._stop_event.clear()


# ---------------------------------------------------------------------------
# Proactive Greeting Generator
# ---------------------------------------------------------------------------

def generate_startup_greeting(
    user_name: Optional[str] = None,
    is_authenticated: bool = True,
    language: str = "en",
    **kwargs,
) -> str:
    """Generate a context-aware startup greeting based on time of day,
    system health, and target language (English or Hindi/Hinglish).

    Args:
        user_name: Authenticated user name (if available).
        is_authenticated: Whether the user session is authenticated.
        language: Language code ('en', 'hi', or 'hinglish').

    Returns:
        Natural greeting string for TTS output on startup.
    """
    hour = datetime.now().hour

    if language in ["hi", "hinglish"]:
        if hour < 12:
            period = "सुप्रभात"
            emoji = "☀️"
        elif hour < 17:
            period = "शुभ दोपहर"
            emoji = "🌤️"
        else:
            period = "शुभ संध्या"
            emoji = "🌆"
        name_part = f", {user_name.title()}" if user_name else ""
        return f"{emoji} {period}{name_part}। तातसु आपकी सेवा में तत्पर है।"

    if hour < 6:
        period = "You're up early"
        emoji = "🌙"
    elif hour < 12:
        period = "Good morning"
        emoji = "☀️"
    elif hour < 17:
        period = "Good afternoon"
        emoji = "🌤️"
    elif hour < 21:
        period = "Good evening"
        emoji = "🌆"
    else:
        period = "Working late"
        emoji = "🌙"

    name_part = f", {user_name.title()}" if user_name else ""

    # Check system health for proactive info
    health_note = ""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        if cpu > 80:
            health_note = f" CPU load is high at {cpu}%. Want me to investigate?"
        elif mem > 85:
            health_note = f" Memory usage is at {mem}%. Should I check for heavy processes?"
        else:
            health_note = " All systems nominal."
    except Exception:
        health_note = ""

    return f"{emoji} {period}{name_part}.{health_note} TATSU is ready."
