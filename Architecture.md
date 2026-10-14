# Tatsu — System Architecture

> **Tatsu** is a human-communicatable, multimodal, agentic desktop AI assistant rebuilt entirely on a **100% free-tier / open-source / locally-run stack**. This document describes every subsystem, their interactions, and the chosen technology stack.

---

## 1. High-Level System Topology

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                          TATSU — PROCESS BOUNDARY                              ║
║                                                                                ║
║  ┌─────────────────────────────────────────────────────────────────────────┐   ║
║  │                     UI LAYER  (PyQt6 + WebEngine HUD)                   │   ║
║  │   ┌─────────────┐  ┌──────────────────────────────────────────────────┐ │   ║
║  │   │ApiKeyDialog │  │ TatsuWebWindow → dashboard/static/app.html       │ │   ║
║  │   │(first-boot) │  │  JS: updateAIState(), addMemoryLog(), toast()   │ │   ║
║  │   └──────┬──────┘  └───────────────────────┬──────────────────────────┘ │   ║
║  │          │ Qt Signals (_state_sig, _log_sig, _content_sig, _reconfig_sig)│   ║
║  └──────────┼──────────────────────────────────┼──────────────────────────┘   ║
║             │                                  │                              ║
║  ┌──────────▼──────────────────────────────────▼──────────────────────────┐   ║
║  │                    TATSU LIVE ENGINE  (main.py :: TatsuLive)            │   ║
║  │                                                                         │   ║
║  │  ┌───────────┐  ┌───────────┐  ┌─────────────┐  ┌──────────────────┐  │   ║
║  │  │ _listen   │  │ _send     │  │ _receive    │  │ _play_audio      │  │   ║
║  │  │ _audio()  │  │ _realtime │  │ _audio()    │  │ (PCM playback)   │  │   ║
║  │  │ sounddevice│  │ ()       │  │ (stream)    │  │ sounddevice      │  │   ║
║  │  └─────┬─────┘  └────┬──────┘  └──────┬──────┘  └──────────────────┘  │   ║
║  │        │PCM in        │  out_queue      │                               │   ║
║  │        └──────────────┴────────────────▼                               │   ║
║  │                                  LLM GATEWAY                           │   ║
║  │              ┌─────────────────────────────────────┐                   │   ║
║  │              │   Gemini 2.5 Flash (Free Tier)       │                   ║
║  │              │   OR  Ollama / LM Studio local        │                   ║
║  │              │   (model: qwen2.5:7b / llama3.2:3b)  │                   ║
║  │              └──────────────┬──────────────────────┘                   │   ║
║  │                             │ tool_call / function_response             │   ║
║  │  ┌──────────────────────────▼──────────────────────────────────────┐  │   ║
║  │  │                  TOOL DISPATCHER (_execute_tool)                 │  │   ║
║  │  │  open_app | web_search | browser_control | screen_process        │  │   ║
║  │  │  computer_settings | computer_control | desktop_control           │  │   ║
║  │  │  code_helper | dev_agent | file_controller | file_processor       │  │   ║
║  │  │  reminder | send_message | youtube_video | weather_report         │  │   ║
║  │  │  game_updater | flight_finder | system_status | save_memory       │  │   ║
║  │  │  shutdown_tatsu                                                   │  │   ║
║  │  └─────────────────────────────────────────────────────────────────┘  │   ║
║  └─────────────────────────────────────────────────────────────────────────┘   ║
║                                                                                ║
║  ┌────────────────────────────┐  ┌──────────────────────────────────────────┐  ║
║  │   MEMORY HUB               │  │   DASHBOARD / REMOTE CONTROL HUB         │  ║
║  │   memory/long_term.json    │  │   FastAPI + uvicorn + WebSocket           │  ║
║  │   memory/reminders.json    │  │   AES-256-CBC encrypted commands          │  ║
║  │   memory/cmr_records.json  │  │   QR Code → phone mic → Gemini Live       │  ║
║  └────────────────────────────┘  └──────────────────────────────────────────┘  ║
║                                                                                ║
║  ┌──────────────────────────────────────────────────────────────────────────┐  ║
║  │   WAKE WORD SERVICE (wake_service.py — SEPARATE PROCESS)                 │  ║
║  │   SpeechRecognition → Google Web Speech API (free) or Vosk (offline)     │  ║
║  │   Probes port 39152 → launches main.py --wake-word if not running         │  ║
║  └──────────────────────────────────────────────────────────────────────────┘  ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```

---

## 2. Detailed Data Flow Pathways

### 2.1 Voice to Response (Audio Live Pipeline)

```
Microphone (sounddevice InputStream, 16 kHz PCM int16)
    │
    ▼
out_queue (asyncio.Queue maxsize=200)
    │
    ▼  [_send_realtime coroutine]
Gemini Live Session
(models/gemini-2.5-flash-native-audio-preview)
    │
    │  stream events
    ├──▶ response.data (raw PCM bytes at 24 kHz)
    │       ▼  [audio_in_queue — 50 ms slices = 2400 bytes]
    │   _play_audio() → sounddevice RawOutputStream (24 kHz)
    │
    ├──▶ response.server_content.input_transcription.text
    │       ▼  [write_log "You: ..."]
    │   UI HUD ← Qt signal → JS addMemoryLog()
    │
    ├──▶ response.server_content.output_transcription.text
    │       ▼  [write_log "Tatsu: ..."]
    │   UI HUD ← Qt signal → JS addMemoryLog()
    │
    └──▶ response.tool_call.function_calls[]
             ▼  [_execute_tool()]
         TOOL REGISTRY dispatch
             ▼  asyncio executor (non-blocking)
         Action module (actions/*.py)
             ▼
         FunctionResponse → session.send_tool_response()
```

### 2.2 Vision Pipeline (Screen / Camera)

```
User: "What do you see on my screen?"
    │
    ▼
Gemini calls screen_process(angle="screen", text="...")
    │
    ▼
_capture_screen() → mss grabs framebuffer
    → PIL.Image.thumbnail(1280x720, BILINEAR) → JPEG @82 quality
    │
    ▼  (pending_vision set, cooldown 4s enforced)
Tatsu says: "Looking at your screen now..." [intermediate speech]
    │
    ▼  [next turn_complete event]
session.send_client_content(inline_data=JPEG_bytes + user_question)
    │
    ▼
Gemini analyzes and responds with visual description
    ▼
User hears Tatsu's description
```

### 2.3 Memory Write/Read Lifecycle

```
Gemini calls save_memory(category, key, value)
    │
    ▼  [_execute_tool — inline, no executor]
update_memory({category: {key: {"value": value, "updated": "YYYY-MM-DD"}}})
    │
    ▼  memory/long_term.json (RLock thread-safe write)
    │
    ▼  [next session _build_config()]
format_memory_for_prompt() → injected into system_instruction
```

### 2.4 Remote Dashboard Phone Relay

```
Phone Browser → ws://LAN_IP:8000/ws/phone-audio?token=...
    │  (PCM bytes from getUserMedia)
    ▼
_phone_audio_queue (asyncio.Queue maxsize=200)
    │
    ▼  [_relay_phone_audio coroutine]
out_queue.put_nowait({data, mime_type:"audio/pcm"})
    │
    ▼  (same path as PC mic → Gemini Live)
PC microphone SILENCED (_phone_active=True)
```

---

## 3. Component Architecture Patterns

### 3.1 Memory Hub

| Component | File | Responsibility |
|-----------|------|----------------|
| Long-term memory | `memory/memory_manager.py` | Load/save/update/format user facts (JSON flat-file, RLock) |
| Config manager | `memory/config_manager.py` | Read/write `config/api_keys.json` (LRU cached, RLock) |
| CRM records | `memory/cmr_manager.py` | Contacts/leads database (UUID keyed JSON list) |
| Reminder store | `memory/reminder_manager.py` | Timed task persistence (ISO datetime triggers) |
| Env utilities | `utils/env.py` | Cross-platform OS detection, config key r/w, lru_cache |

### 3.2 Skill Hub (Action Modules — 20 Tools)

| Tool Name | File | Free-Tier Implementation |
|-----------|------|--------------------------|
| `open_app` | `actions/open_app.py` | `subprocess.Popen` + 65-app cross-platform alias table |
| `web_search` | `actions/web_search.py` | DuckDuckGo (`ddgs`) + Gemini grounding (no API key for DDG) |
| `browser_control` | `actions/browser_control.py` | Playwright Chromium (free local), real browser profile attach |
| `file_controller` | `actions/file_controller.py` | `pathlib`, `send2trash` — safe root enforcement |
| `file_processor` | `actions/file_processor.py` | Pillow, python-pptx, csv, json — Gemini for AI analysis |
| `send_message` | `actions/send_message.py` | `pyautogui` + `pyperclip` — GUI automation, no external API |
| `reminder` | `actions/reminder.py` | Windows Task Scheduler / cron / `at` command |
| `computer_settings` | `actions/computer_settings.py` | pycaw (Win), osascript (Mac), pactl (Linux) |
| `computer_control` | `actions/computer_control.py` | `pyautogui` — mouse, keyboard, screenshot, find on screen |
| `desktop_control` | `actions/desktop.py` | pyautogui + Gemini sandboxed code exec |
| `screen_process` | `actions/screen_processor.py` | `mss` screen grab + `cv2` webcam + JPEG compress |
| `code_helper` | `actions/code_helper.py` | Gemini 2.5 Flash write/edit/explain/run/build |
| `dev_agent` | `actions/dev_agent.py` | Multi-file project planner + iterative error-fix loop |
| `youtube_video` | `actions/youtube_video.py` | HTML scrape (no API key) + `youtube-transcript-api` |
| `weather_report` | `actions/weather_report.py` | `webbrowser.open` Google search (no API) |
| `flight_finder` | `actions/flight_finder.py` | Playwright → Google Flights URL builder |
| `game_updater` | `actions/game_updater.py` | `steamcmd` / Steam CLI + Epic `legendary` CLI |
| `system_status` | `actions/system_monitor.py` | `psutil` + NVML ctypes — zero subprocess |
| `save_memory` | inline in `main.py` | Calls `memory_manager.update_memory()` directly |
| `shutdown_tatsu` | inline in `main.py` | `os._exit(0)` after 1s delay |

### 3.3 Harness Hub (Core Engines)

| Engine | File | Free-Tier Implementation |
|--------|------|-------------------------|
| LLM Client | `core/llm_client.py` | Ollama native API + OpenAI-compatible (LM Studio/LocalAI/Jan) |
| TTS Engine | `core/tts.py` | EdgeTTS (free cloud), Kokoro-82M (offline ~330MB), Piper (offline) |
| STT Engine | `core/stt.py` | faster-whisper (offline, VAD-buffered), Vosk (streaming, offline) |
| Tool Declarations | `core/tool_declarations.py` | 20 JSON function schemas for Gemini/Ollama function calling |
| System Prompt | `core/prompt.txt` | Tatsu persona directives, protocol, routing rules |
| Dependency Installer | `core/installer.py` | Auto-detects and pip installs missing packages at runtime |

### 3.4 Dashboard Hub

| Component | File | Technology |
|-----------|------|-----------|
| HTTP/WS Server | `dashboard/server.py` | FastAPI + uvicorn + WebSockets |
| AES Encryption | `dashboard/server.py` | PBKDF2-HMAC-SHA256 → AES-256-CBC + PKCS7 |
| Web UI | `dashboard/static/app.html` | Single-page app with WebGL HUD, responsive mobile layout |
| Login Page | `dashboard/static/login.html` | PIN-based one-time key login |
| CryptoJS | `dashboard/static/crypto-js.min.js` | Auto-downloaded once, served locally |
| Phone Audio WS | `/ws/phone-audio` | Binary PCM relay to Gemini Live session |
| File Upload | `/api/upload` | python-multipart, 500 MB limit, safe filename sanitization |

---

## 4. Zero-Cost Technology Stack Matrix

| Category | Primary (Preferred) | Secondary Fallback | Tertiary |
|----------|--------------------|--------------------|---------|
| **LLM Main Session** | Gemini 2.5 Flash Free Tier (15 RPM, 1M TPM) | Ollama `qwen2.5:7b-instruct` (local) | LM Studio `Llama-3.2-3B` |
| **LLM Tool/Code** | Gemini 2.5 Flash | Ollama `llama3.2:3b` | Ollama `mistral:7b` |
| **Live Audio** | Gemini Live native-audio model | STT → LLM → TTS pipeline | — |
| **STT** | `faster-whisper` base/small (offline) | Vosk `en-us-0.22` (streaming) | Google Web Speech API (free) |
| **TTS** | Kokoro-82M offline (~330 MB) | Microsoft EdgeTTS (free, no key) | Piper `en_US-ryan-high.onnx` |
| **Wake Word** | SpeechRecognition + Google Web Speech (free) | Vosk offline recognition | OpenWakeWord (local) |
| **Web Search** | `duckduckgo-search` DDG (no key) | Gemini Google grounding (free) | BeautifulSoup4 raw scraping |
| **Browser Automation** | Playwright Chromium (local) | Playwright Firefox | Selenium |
| **Screen Capture** | `mss` (zero deps) | `pyautogui.screenshot()` | PIL ImageGrab |
| **Camera** | OpenCV `cv2.VideoCapture` | — | — |
| **System Monitoring** | `psutil` + NVML ctypes | pynvml | — |
| **Computer Control** | `pyautogui` + `pyperclip` | `pynput` | Native shell |
| **Volume (Win)** | `pycaw` + comtypes | pyautogui keypresses | — |
| **Volume (Mac)** | `osascript` | — | — |
| **Volume (Linux)** | `pactl` / `amixer` | — | — |
| **GUI Framework** | PyQt6 + PyQt6-WebEngine | tkinter | — |
| **Web Dashboard** | FastAPI + uvicorn | Flask | — |
| **Encryption** | python `cryptography` AES-256-CBC | — | — |
| **Presentations** | `python-pptx` | LibreOffice CLI | — |
| **YouTube** | `youtube-transcript-api` (no key) | HTML scrape | — |
| **Memory Store** | JSON flat-file | SQLite | ChromaDB (vector, free local) |

---

## 5. Process and Thread Architecture

```
Main OS Process (python main.py)
├── Qt Main Thread          → UI event loop (QApplication.exec())
└── Background Thread       → asyncio.run(TatsuLive.run())  [daemon=True]
    └── asyncio Event Loop
        ├── Task: _send_realtime()          → PCM from out_queue to Gemini
        ├── Task: _listen_audio()           → mic → out_queue
        ├── Task: _receive_audio()          → Gemini stream → audio + transcripts
        ├── Task: _play_audio()             → audio_in_queue → speaker output
        ├── Task: _run_system_monitor()     → psutil 2s loop → emergency alerts
        ├── Task: _run_proactive_mode()     → 60s loop → context-aware check-ins
        ├── Task: dashboard.serve()         → uvicorn (port 8000)
        ├── Task: _process_dashboard_cmds() → command_queue → session
        └── Task: _relay_phone_audio()      → phone queue → out_queue

Separate Process (python wake_service.py — optional always-on)
└── Main Thread → sr.Recognizer loop → socket probe → Popen main.py --wake-word
```

---

## 6. Security Architecture

```
Dashboard Security Model:

1. One-time PIN (6 alphanumeric chars, expiry 10min)
   Generated by new_key() → Displayed as QR code in UI

2. QR Scan → /auto-login?key=PIN
   → Bearer token (secrets.token_urlsafe(32)) issued
   → Session key = PIN → PBKDF2-HMAC-SHA256 → 32-byte AES key

3. All subsequent commands encrypted:
   Client: AES-256-CBC(IV[16] + PKCS7(plaintext)) → base64 → {"enc": "..."}
   Server: _decrypt_cbc(aes_key, enc_b64) → plaintext

4. Device tokens (persistent re-login without new PIN)
   localStorage.setItem('device_token', ...)

5. File uploads: safe filename sanitization + safe root enforcement
   Path traversal prevention: re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)

6. Single-instance lock: socket bind(127.0.0.1:39152)

7. Subprocess isolation: CREATE_NO_WINDOW flag on Windows
   (patched via _Popen wrapper at module level in main.py)
```

---

## 7. Configuration Schema

```json
{
    "gemini_api_key": "AIza...",
    "assistant_name": "Tatsu",
    "user_name": "Alex",
    "os_system": "windows",
    "morning_brief_enabled": true,
    "ui_color": "#00d4ff",
    "llm_provider": "ollama",
    "llm_url": "http://localhost:11434",
    "llm_model": "qwen2.5:7b-instruct",
    "tts_engine": "edgetts",
    "tts_voice": "en-US-BrianNeural",
    "tts_speed": 1.0,
    "stt_engine": "whisper",
    "stt_model": "base",
    "stt_language": "auto"
}
```

---

## 8. Startup Sequence

```
SETUP.bat (first run only)
    │
    ▼
TATSU_SETUP.py
    1. Verify marker files
    2. Download from GitHub if missing (git clone → ZIP fallback)
    3. Check Python 3.10+
    4. pip install --upgrade pip
    5. pip install -r requirements.txt
    6. python -m playwright install chromium
    7. Create config/api_keys.json from .example
    8. Write .tatsu_setup_complete marker

START_TATSU.bat
    1. Check .tatsu_setup_complete marker
    2. python main.py

main.py :: main()
    1. _ensure_single_instance() → bind port 39152
    2. TatsuUI("face.png") → PyQt6 QApplication + TatsuWebWindow
    3. _needs_api_key()? → ApiKeyDialog → save to config/api_keys.json
    4. daemon Thread → asyncio.run(TatsuLive.run())
    5. ui.root.mainloop() → Qt event loop (blocks until exit)

TatsuLive.run()
    1. DashboardServer() → asyncio task → uvicorn port 8000
    2. _process_dashboard_commands() task
    3. genai.Client(api_key) + _build_config()
    4. client.aio.live.connect(model, config) → TaskGroup
    5. Tasks: _send_realtime, _listen_audio, _receive_audio, _play_audio
    6. Tasks: _run_system_monitor, _run_proactive_mode
    7. If --wake-word: send "wake up tatsu" prompt
    8. Else if morning_brief_enabled: _send_startup_briefing()
```
