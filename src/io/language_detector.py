"""Language Detector for TATSU Sovereign Agent — Phase 7 (The Polyglot Core).

Provides lightweight, offline language detection and classification for:
- English ('en')
- Hindi (Devanagari script, 'hi')
- Hinglish (Romanized / transliterated Hindi, 'hinglish')

Zero cloud dependencies. Highly deterministic with heuristic marker scoring
and optional fallback to langdetect if available in the environment.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Common Hinglish lexical markers (phonetic transliterations of high-frequency Hindi words)
# Excludes English homographs (e.g. 'the', 'to', 'do', 'hi', 'in', 'is', 'me')
HINGLISH_MARKERS: Set[str] = {
    # Pronouns & demonstratives
    "mera", "meri", "mere", "apna", "apni", "apne", "tera", "teri", "tere",
    "hum", "humara", "humari", "humare", "tum", "tumhara", "tumhari", "aap", "aapka", "aapki",
    "yeh", "woh", "iss", "uss", "unhe", "kise", "kisko",
    # Question words
    "kya", "kyun", "kyu", "kaise", "kaisa", "kaisi", "kaun", "kahan", "kidhar", "kab", "kitna", "kitni",
    # Verbs & auxiliaries
    "hai", "hain", "hoon", "hun", "tha", "thi",
    "kar", "karo", "kare", "karega", "karegi", "kardo", "karne", "karna", "kiya", "kiye",
    "dekh", "dekho", "dekhe", "dekhein", "bol", "bolo", "batao", "bata", "bataiye",
    "chal", "chala", "chalo", "chalu", "chalega", "chalegi", "chalte",
    "raha", "rahi", "rahe", "hona", "hoga", "hogi", "hote", "hoti", "hota",
    "dijiye", "lijiye", "aao", "jao", "jaate", "aate", "dedo",
    "rok", "roko", "band", "khol", "kholo", "hata", "hatao", "lagao", "bhejo",
    # Modifiers, particles & conjunctions
    "bhi", "toh", "aur", "lekin", "magar", "kyunki", "isliye",
    "thoda", "thodi", "thode", "zara", "bahut", "bohot", "zyada", "jyada", "kam",
    "accha", "achha", "achi", "achhi", "theek", "thik", "sahi", "galat",
    "haan", "nahi", "nahin", "mat",
    # Salutations & colloquial terms
    "namaste", "namaskar", "pranam", "shukriya", "dhanyavaad", "dhanyawad", "alvida",
    "bhai", "yaar", "dost", "sahab", "sirji", "bataiye", "suno", "sunie",
}

# Regex for Devanagari Unicode block (\u0900 - \u097F)
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
# Regex for Latin alphabetic words
WORD_RE = re.compile(r"\b[a-zA-Z']+\b")


def has_devanagari(text: str) -> bool:
    """Check if text contains any Devanagari characters."""
    return bool(DEVANAGARI_RE.search(text))


def devanagari_ratio(text: str) -> float:
    """Calculate the ratio of Devanagari characters among alphabetic characters."""
    chars = [c for c in text if c.isalpha() or ('\u0900' <= c <= '\u097F')]
    if not chars:
        return 0.0
    dev_count = sum(1 for c in chars if '\u0900' <= c <= '\u097F')
    return dev_count / len(chars)


def count_hinglish_markers(text: str) -> Tuple[int, int, List[str]]:
    """Count occurrences of Hinglish markers in Latin text.

    Returns:
        (marker_count, total_word_count, matched_markers)
    """
    words = [w.lower() for w in WORD_RE.findall(text)]
    if not words:
        return (0, 0, [])
    matched = [w for w in words if w in HINGLISH_MARKERS]
    return (len(matched), len(words), matched)


def detect_language(text: str) -> str:
    """Detect language of the input text.

    Returns:
        - 'hi': Hindi written in Devanagari script.
        - 'hinglish': Hindi transliterated into Latin script or mixed English-Hindi.
        - 'en': Standard English.

    Heuristic priority:
    1. If Devanagari characters are prominent (>15% of alpha chars), classify as 'hi'.
    2. If Latin text contains recognizable Hinglish lexical markers, classify as 'hinglish'.
    3. Optional secondary check via langdetect if installed.
    4. Default to 'en' (English).
    """
    if not text or not text.strip():
        return "en"

    cleaned = text.strip()

    # Rule 1: Devanagari presence
    if has_devanagari(cleaned):
        ratio = devanagari_ratio(cleaned)
        # Any significant Devanagari presence indicates Hindi
        if ratio >= 0.15 or len(DEVANAGARI_RE.findall(cleaned)) >= 2:
            return "hi"

    # Rule 2: Hinglish marker detection in Latin text
    marker_count, word_count, _ = count_hinglish_markers(cleaned)
    if word_count > 0:
        # If text is short (<= 4 words) and has at least 1 strong Hinglish word
        if word_count <= 4 and marker_count >= 1:
            return "hinglish"
        # If 15% or more words are Hinglish markers
        if marker_count >= 2 or (marker_count / word_count >= 0.15):
            return "hinglish"

    # Rule 3: Optional langdetect verification
    try:
        from langdetect import detect
        detected = detect(cleaned)
        if detected == "hi":
            # Sometimes romanized Hindi is detected as 'hi'
            return "hinglish" if not has_devanagari(cleaned) else "hi"
    except Exception:
        pass

    return "en"


def get_language_details(text: str) -> Dict[str, Any]:
    """Provide comprehensive linguistic breakdown for debugging and telemetry.

    Returns dict containing detected language, script type, marker counts, and confidence.
    """
    lang = detect_language(text)
    dev_chars = len(DEVANAGARI_RE.findall(text))
    marker_count, word_count, matched = count_hinglish_markers(text)

    if lang == "hi":
        confidence = min(0.99, 0.70 + (dev_chars / max(1, len(text))) * 0.3)
        script = "devanagari"
    elif lang == "hinglish":
        ratio = marker_count / max(1, word_count)
        confidence = min(0.95, 0.60 + ratio * 0.4)
        script = "latin_transliterated"
    else:
        confidence = 0.90 if word_count > 0 else 0.50
        script = "latin"

    return {
        "language": lang,
        "script": script,
        "confidence": round(confidence, 2),
        "devanagari_char_count": dev_chars,
        "hinglish_marker_count": marker_count,
        "total_words": word_count,
        "matched_markers": matched,
    }


def format_multilingual_prompt_guidance(detected_lang: str, persona: Optional[Dict[str, Any]] = None) -> str:
    """Generate dynamic system prompt instructions tailored to the user's language."""
    if detected_lang == "hi":
        return (
            "\n\n[LINGUISTIC PROTOCOL: HINDI ACTIVE]\n"
            "The user addressed you in Hindi (Devanagari). "
            "Reply strictly in pure, natural Hindi in Devanagari script (e.g., 'नमस्ते राज, मैं देख रहा हूँ कि...'). "
            "Maintain the calm, sovereign, polite persona of TATSU. Avoid English unless quoting code or technical names."
        )
    elif detected_lang == "hinglish":
        return (
            "\n\n[LINGUISTIC PROTOCOL: HINGLISH ACTIVE]\n"
            "The user addressed you in Hinglish (conversational Hindi in Latin script). "
            "Reply in natural, fluid Hinglish matching the user's cadence (e.g., 'Haan Raj, main check kar raha hoon...'). "
            "Keep technical commands precise and the tone warm, concise, and sovereign."
        )
    else:
        return (
            "\n\n[LINGUISTIC PROTOCOL: ENGLISH (BRITISH SOVEREIGN)]\n"
            "The user addressed you in English. "
            "Reply in crisp, British-accented, authoritative English (e.g., 'Certainly, sir. System nominal.'). "
            "Keep simple answers to 1-2 concise sentences."
        )
