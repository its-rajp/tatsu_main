# Tatsu — Project Requirements Document (PRD)

> This document captures all functional, non-functional, and technical requirements for the **Tatsu** human-communicatable AI assistant. All requirements must be satisfied using a **100% free-tier / open-source / locally-run** technology stack.

---

## 1. Product Vision

**Tatsu** is a warm, human-communicatable, multimodal AI desktop assistant. Unlike cold, robotic assistant systems, Tatsu is designed to feel like a knowledgeable, empathetic friend who happens to be infinitely capable. It listens, remembers, acts, and grows alongside the user.

### Design Pillars

| Pillar | Description |
|--------|------------|
| **Human-first Communication** | Natural speech, warm tone, brief and clear responses |
| **Persistent Memory** | Remembers the user's life across sessions |
| **Agentic Capability** | Executes real computer actions, not just chat |
| **Privacy by Default** | Can run 100% offline; no data leaves the device |
| **Zero Cost** | Free forever on a consumer machine; no subscriptions |

---

## 2. Persona Requirements

### PR-1: Name and Identity
- The assistant is named **Tatsu**
- Tatsu has a consistent personality: warm, curious, slightly witty, never robotic
- Tatsu refers to the user by their configured preferred name
- Tatsu never refers to itself as an "AI language model" or breaks character

### PR-2: Speech Style
- In voice mode: responses are **1-3 sentences** unless user asks for detail
- In text/dashboard mode: responses may be longer and formatted with lists/code
- Tatsu uses contractions, natural phrasing ("Sure, let me check that")
- Tatsu expresses genuine curiosity ("Oh, that's interesting — tell me more")

### PR-3: Emotional Intelligence
- Tatsu detects distress signals in speech and responds with empathy first
- Tatsu acknowledges uncertainty honestly ("I'm not sure about that, but let me look it up")
- Tatsu never sounds dismissive or condescending

### PR-4: Proactivity
- After 60 seconds of silence, Tatsu may offer a contextual check-in
- On startup, Tatsu delivers a morning briefing (weather, reminders, in-progress projects)
- Tatsu proactively saves important facts the user mentions ("I've noted your meeting is tomorrow")

---

## 3. Functional Requirements

### FR-1: Voice Conversation
| ID | Requirement |
|----|------------|
| FR-1.1 | System captures microphone audio at 16 kHz PCM int16 |
| FR-1.2 | Audio streams in real-time to Gemini Live session |
| FR-1.3 | Gemini Live responses stream back as PCM audio at 24 kHz |
| FR-1.4 | User can interrupt Tatsu mid-sentence (barge-in / VAD) |
| FR-1.5 | Both user and Tatsu transcripts appear in the HUD |
| FR-1.6 | System recovers automatically from dropped Gemini Live connections |

### FR-2: Memory System
| ID | Requirement |
|----|------------|
| FR-2.1 | Tatsu persists user facts in 6 categories (identity, preferences, projects, relationships, wishes, notes) |
| FR-2.2 | Memory is injected into system_instruction at every session start |
| FR-2.3 | `save_memory` tool allows Gemini to persist new facts in real-time |
| FR-2.4 | All memory survives process restarts (JSON file-backed) |
| FR-2.5 | Reminders can be set with natural language and triggered at the correct time |
| FR-2.6 | CRM/contact records can be created, updated, searched, and deleted |

### FR-3: Multimodal Input
| ID | Requirement |
|----|------------|
| FR-3.1 | `screen_process` captures the full desktop framebuffer via `mss` |
| FR-3.2 | `screen_process` can also capture from a webcam via OpenCV |
| FR-3.3 | Captured frames are JPEG-compressed (≤1280×720, quality 82) before API submission |
| FR-3.4 | Vision requests have a 4-second cooldown to prevent rate-limit abuse |
| FR-3.5 | Files (images, PDFs, CSVs, code, PPTX) can be uploaded for Gemini analysis |

### FR-4: Desktop Automation (20 Tools)
| ID | Requirement |
|----|------------|
| FR-4.1 | `open_app` — open any of 65+ apps by natural language name on Win/Mac/Linux |
| FR-4.2 | `computer_control` — click, type, scroll, hotkey, screenshot, find on screen |
| FR-4.3 | `computer_settings` — volume, brightness, WiFi, Bluetooth, display settings |
| FR-4.4 | `desktop_control` — Gemini-generated `pyautogui` script executed in sandbox |
| FR-4.5 | `web_search` — DuckDuckGo search → summarized results |
| FR-4.6 | `browser_control` — Playwright: navigate, click, type, scrape, scroll |
| FR-4.7 | `file_controller` — list, read, write, move, delete files; safe root enforced |
| FR-4.8 | `file_processor` — AI-analyze images, CSVs, code, PPTX, text files |
| FR-4.9 | `code_helper` — write, edit, explain, run, build code in any language |
| FR-4.10 | `dev_agent` — build multi-file projects from a description; iterative error-fix loop |
| FR-4.11 | `send_message` — type and send messages via pyautogui to any open app |
| FR-4.12 | `youtube_video` — fetch video transcripts and summaries without API key |
| FR-4.13 | `weather_report` — open weather search in browser |
| FR-4.14 | `flight_finder` — build Google Flights URL and open in browser |
| FR-4.15 | `game_updater` — update Steam / Epic games via CLI |
| FR-4.16 | `system_status` — CPU, RAM, disk, GPU usage + emergency alerts |
| FR-4.17 | `reminder` — schedule cross-platform OS reminders |
| FR-4.18 | `save_memory` — persist user facts immediately |
| FR-4.19 | `screen_process` — screen/camera vision |
| FR-4.20 | `shutdown_tatsu` — clean process exit |

### FR-5: Dashboard & Remote Control
| ID | Requirement |
|----|------------|
| FR-5.1 | FastAPI server starts on port 8000 alongside Tatsu |
| FR-5.2 | Dashboard accessible from phone browser on same LAN |
| FR-5.3 | Login via QR-scanned one-time PIN (6 chars, 10-minute expiry) |
| FR-5.4 | All dashboard commands encrypted with AES-256-CBC |
| FR-5.5 | Device tokens allow persistent login without re-scanning QR |
| FR-5.6 | Phone microphone can be relayed to Tatsu's Gemini Live session |
| FR-5.7 | Files up to 500 MB can be uploaded from phone to Tatsu's machine |
| FR-5.8 | Dashboard displays real-time memory log and Tatsu state |

### FR-6: Setup & Onboarding
| ID | Requirement |
|----|------------|
| FR-6.1 | `SETUP.bat` / `SETUP.sh` installs all dependencies automatically |
| FR-6.2 | `core/installer.py` checks and installs missing Python packages at runtime |
| FR-6.3 | First-boot `ApiKeyDialog` guides user to get and paste a free Gemini API key |
| FR-6.4 | All dependencies installable via `pip install -r requirements.txt` |
| FR-6.5 | `python -m playwright install chromium` installs browser automatically |
| FR-6.6 | Wake word service (`wake_service.py`) runs as a separate process |

---

## 4. Non-Functional Requirements

### NFR-1: Performance
| ID | Requirement |
|----|------------|
| NFR-1.1 | Gemini Live voice response latency: < 2 seconds |
| NFR-1.2 | Local STT (Whisper base): < 500ms for 5-second utterance |
| NFR-1.3 | Local TTS (EdgeTTS): < 800ms to first audio byte |
| NFR-1.4 | `screen_process` capture to API submission: < 1 second |
| NFR-1.5 | `web_search` DuckDuckGo: < 3 seconds for top 5 results |
| NFR-1.6 | System monitor loop: 2-second interval, < 1% CPU overhead |

### NFR-2: Reliability
| ID | Requirement |
|----|------------|
| NFR-2.1 | Gemini Live session reconnects automatically on disconnect |
| NFR-2.2 | All file operations use `try/except` with user-friendly error messages |
| NFR-2.3 | Memory writes use RLock to prevent corruption under concurrent access |
| NFR-2.4 | Single-instance guard prevents multiple conflicting Tatsu processes |
| NFR-2.5 | All tool calls return meaningful error strings (never raise to session) |

### NFR-3: Security
| ID | Requirement |
|----|------------|
| NFR-3.1 | Dashboard commands encrypted with AES-256-CBC + PKCS7 padding |
| NFR-3.2 | Session keys derived via PBKDF2-HMAC-SHA256 (100k iterations) |
| NFR-3.3 | File upload paths sanitized; no path traversal possible |
| NFR-3.4 | API keys stored in local `config/api_keys.json` only; never logged |
| NFR-3.5 | `desktop_control` AI-generated scripts reviewed by Gemini for safety |
| NFR-3.6 | File operations restricted to user's configured safe root directory |

### NFR-4: Privacy
| ID | Requirement |
|----|------------|
| NFR-4.1 | In local-only mode (Ollama + Whisper + Kokoro), zero network calls |
| NFR-4.2 | No telemetry, analytics, or usage data collection |
| NFR-4.3 | Memory files stored locally only (`memory/` directory) |
| NFR-4.4 | Dashboard server binds only to LAN IP; not exposed to public internet by default |

### NFR-5: Compatibility
| ID | Requirement |
|----|------------|
| NFR-5.1 | Python 3.10, 3.11, 3.12 compatible |
| NFR-5.2 | Works on Windows 10/11, macOS 12+, Ubuntu 20.04+ |
| NFR-5.3 | Handles missing optional dependencies gracefully (e.g., pycaw on Mac) |
| NFR-5.4 | All async code uses `asyncio` (no `trio`, no `gevent`) |

---

## 5. Dependency Manifest

### Core (Required)

```
google-genai>=1.16.0          # Gemini API + Live audio session
PyQt6>=6.7.0                  # GUI framework
PyQt6-WebEngine>=6.7.0        # WebEngine for HTML HUD
sounddevice>=0.4.6            # Mic input + speaker output (PCM)
numpy>=1.24                   # PCM buffer processing
fastapi>=0.115.0              # Dashboard HTTP + WebSocket server
uvicorn>=0.30.0               # ASGI server for FastAPI
websockets>=12.0              # WebSocket support
cryptography>=42.0            # AES-256-CBC encryption
pillow>=10.0                  # Image processing (screen capture)
mss>=9.0                      # High-performance screen capture
psutil>=5.9                   # System monitoring
pyautogui>=0.9.54             # Desktop automation
pyperclip>=1.8                # Clipboard r/w
duckduckgo-search>=6.0        # Web search (no API key)
playwright>=1.45              # Browser automation
send2trash>=1.8               # Safe file deletion
requests>=2.31                # HTTP client
```

### Optional (Enhanced Features)

```
edge-tts>=6.1.9               # Microsoft EdgeTTS (free cloud TTS)
kokoro>=0.9                   # Kokoro-82M local TTS (offline)
piper-tts>=1.2                # Piper local TTS (offline)
faster-whisper>=1.0           # Offline STT
openai-whisper>=2023           # Alternative STT
vosk>=0.3.45                  # Streaming offline STT
speechrecognition>=3.10       # Wake word + fallback STT
opencv-python>=4.9            # Webcam capture
python-pptx>=0.6.23           # PowerPoint read/write
pycaw>=20240210               # Windows audio control (Win only)
comtypes>=1.4.4               # COM interface for pycaw (Win only)
youtube-transcript-api>=0.6   # YouTube transcript fetch
pywin32>=306                  # Windows system integration (Win only)
pywinauto>=0.6.8              # Windows GUI automation (Win only)
python-multipart>=0.0.9       # FastAPI file upload support
qrcode>=7.4                   # QR code generation for dashboard login
```

---

## 6. Anti-Requirements (Explicitly Excluded)

| Category | Excluded Item | Reason |
|----------|--------------|--------|
| Cloud Storage | AWS S3, Google Cloud Storage | Paid / privacy |
| Vector DBs | Pinecone, Weaviate (cloud) | Paid |
| Paid LLM APIs | OpenAI GPT-4, Anthropic Claude | Paid |
| Paid TTS | ElevenLabs (paid tier), Amazon Polly | Paid |
| Paid STT | OpenAI Whisper API, Google Speech-to-Text | Paid |
| Analytics | Mixpanel, Amplitude, Segment | Privacy violation |
| Telemetry | Sentry (paid), Datadog | Privacy + paid |
| Auth Providers | Auth0, Firebase Auth | Dependency on external service |
| Package Managers | Conda, Poetry | Complexity; pip is sufficient |
| Containerization | Docker (runtime requirement) | Not required for desktop app |

---

## 7. Configuration Requirements

All user-configurable settings stored in `config/api_keys.json`:

| Key | Type | Default | Required |
|-----|------|---------|---------|
| `gemini_api_key` | string | — | YES (for Gemini mode) |
| `assistant_name` | string | `"Tatsu"` | NO |
| `user_name` | string | `"User"` | NO |
| `os_system` | string | auto-detected | NO |
| `morning_brief_enabled` | bool | `true` | NO |
| `ui_color` | string | `"#00d4ff"` | NO |
| `llm_provider` | string | `"gemini"` | NO |
| `llm_url` | string | `"http://localhost:11434"` | Only for Ollama |
| `llm_model` | string | `"qwen2.5:7b-instruct"` | Only for Ollama |
| `tts_engine` | string | `"edgetts"` | NO |
| `tts_voice` | string | `"en-US-BrianNeural"` | NO |
| `tts_speed` | float | `1.0` | NO |
| `stt_engine` | string | `"whisper"` | NO |
| `stt_model` | string | `"base"` | NO |
| `stt_language` | string | `"auto"` | NO |
