# Tatsu — Codebase Structure & Directory Blueprint

> This document provides an exhaustive file-by-file and directory-by-directory reference of the entire **Tatsu** repository.

---

## 1. Directory Tree Overview

```
tatsu/
├── config/
│   ├── api_keys.json               # Active user configurations and credentials
│   └── api_keys.json.example       # Template configuration for initial onboarding
├── memory/
│   ├── long_term.json              # Long-term persisted user facts and preferences
│   ├── reminders.json              # Active and recurring scheduled reminders
│   ├── cmr_records.json            # CRM database for contacts and personal network
│   ├── memory_manager.py           # CRUD and thread-safe persistence for long-term memory
│   ├── reminder_manager.py         # Scheduled task storage, parser, and trigger checks
│   ├── cmr_manager.py              # CRM management functions
│   └── config_manager.py           # Thread-safe cached configuration reader/writer
├── core/
│   ├── llm_client.py               # Local LLM gateway (Ollama native & OpenAI-compatible)
│   ├── tts.py                      # Multi-engine TTS (EdgeTTS, Kokoro-82M, Piper)
│   ├── stt.py                      # Multi-engine STT (faster-whisper, Vosk)
│   ├── tool_declarations.py        # Complete JSON schemas for all 20 action tools
│   ├── prompt.txt                  # Tatsu warm human persona master prompt
│   └── installer.py                # Runtime dynamic dependency checker and installer
├── actions/
│   ├── open_app.py                 # Cross-platform desktop application launcher
│   ├── web_search.py               # DuckDuckGo zero-cost search scraper & summarizer
│   ├── browser_control.py          # Playwright Chromium browser automation engine
│   ├── computer_control.py         # PyAutoGUI mouse, keyboard, and screen interaction
│   ├── computer_settings.py        # System volume, brightness, and audio device control
│   ├── desktop.py                  # Code-generated desktop automation interpreter
│   ├── screen_processor.py         # MSS screen grabber and OpenCV webcam processor
│   ├── file_controller.py          # Safe-path bounded file CRUD operations
│   ├── file_processor.py           # Multimodal document analyzer (images, code, PPTX, CSV)
│   ├── code_helper.py              # Code analysis, drafting, execution, and debugging
│   ├── dev_agent.py                # Multi-step automated software engineering agent
│   ├── reminder.py                 # OS-level reminder execution wrappers
│   ├── send_message.py             # Desktop app message dispatch via GUI automation
│   ├── youtube_video.py            # Free transcript extraction and video summarization
│   ├── weather_report.py           # Zero-cost weather inquiry launcher
│   ├── flight_finder.py            # Google Flights query generator
│   ├── game_updater.py             # Steam / Epic Games launcher and update trigger
│   └── system_monitor.py           # Hardware metrics collector (CPU, RAM, GPU, thermals)
├── dashboard/
│   ├── server.py                   # FastAPI + WebSockets server & encrypted command gateway
│   └── static/
│       ├── app.html                # Responsive web app HUD interface
│       ├── login.html              # PIN and QR-code authentication portal
│       └── crypto-js.min.js        # Local crypto library for AES-256-CBC client encryption
├── utils/
│   ├── env.py                      # Cross-platform environment and OS identification helpers
│   └── logger.py                   # Standardized logging configuration
├── main.py                         # System orchestrator, PyQt6 UI lifecycle, Gemini Live loop
├── ui.py                           # PyQt6 desktop HUD, WebEngine integration, signal bus
├── wake_service.py                 # Standalone lightweight background wake-word listener
├── requirements.txt                # Unified dependency manifest
├── TATSU_SETUP.py                  # Cross-platform automated bootstrap & setup script
├── SETUP.bat                       # Windows one-click initialization script
└── START_TATSU.bat                 # Windows one-click launcher script
```

---

## 2. Component Directory Breakdown

### 2.1 `config/`
- **`api_keys.json`**: Primary runtime state containing model keys, active provider selections, UI themes, and preferences. Never committed to version control.
- **`api_keys.json.example`**: Clean template illustrating default field names, data types, and fallback local values (`http://localhost:11434`).

### 2.2 `memory/`
- **`long_term.json`**: Keyed storage segmented into `identity`, `preferences`, `projects`, `relationships`, `wishes`, and `notes`.
- **`memory_manager.py`**:
  - `load_memory() -> dict`: Reads JSON file safely.
  - `update_memory(updates: dict)`: Deep-merges dictionary payloads with RLock protection.
  - `format_memory_for_prompt() -> str`: Formats historical facts into conversational markdown injected into Tatsu's system instruction.
- **`reminder_manager.py`**: Handles cron-like recurrence (`daily`, `weekdays`, `once`) and ISO timestamp triggers.
- **`cmr_manager.py`**: Exposes query, search, and CRUD APIs for contacts.
- **`config_manager.py`**: LRU-cached configuration accessor that invalidates upon disk write.

### 2.3 `core/`
- **`llm_client.py`**: Implements `OllamaClient` and `OpenAICompatibleClient`. Provides unified asynchronous completion and streaming interfaces.
- **`tts.py`**:
  - EdgeTTS: Asynchronous streaming cloud voice synthesis without subscription keys.
  - Kokoro-82M: Local, 82-million parameter ONNX voice synthesis model running offline.
  - Fallback logic ensuring seamless switch if internet drops.
- **`stt.py`**:
  - `faster-whisper`: Low-latency local transcription with Voice Activity Detection (VAD) slicing.
  - `Vosk`: Ultra-lightweight streaming offline transcription.
- **`tool_declarations.py`**: Centralized registry exporting function calling schemas compatible with both Gemini 2.5 Flash and local LLM tool dispatchers.
- **`prompt.txt`**: Tatsu master prompt defining tone, personality, boundaries, speech conventions, and agentic workflows.
- **`installer.py`**: Auto-detects missing third-party packages at runtime and executes non-blocking `pip install` subprocesses.

### 2.4 `actions/`
- **`open_app.py`**: Contains an alias dictionary of 65+ desktop applications mapped to binary names across Windows, macOS, and Linux.
- **`web_search.py`**: Executes DuckDuckGo queries via `duckduckgo-search` library, parsing and formatting top text snippets.
- **`browser_control.py`**: Wraps Playwright headless/headed Chromium instances for web navigation, button clicking, form filling, and DOM evaluation.
- **`computer_control.py`**: Interfaces with `pyautogui` for mouse motion, clicks, keystrokes, and template image matching.
- **`computer_settings.py`**: Platform-sensitive volume and brightness controller (using `pycaw` on Windows, `osascript` on macOS, `amixer`/`pactl` on Linux).
- **`desktop.py`**: Executes short-form desktop automation routines safely.
- **`screen_processor.py`**: Handles screen frame capture (`mss`) and camera snapshots (`cv2`), converting images to compressed JPEG byte streams.
- **`file_controller.py`**: Manages directory listings, file reads, writes, moves, and `send2trash` deletions within configured boundaries.
- **`file_processor.py`**: Parses PDFs, Word docs, CSV tables, and images into structured prompts for multimodal analysis.
- **`code_helper.py`**: Provides development utilities including syntax analysis, localized file editing, and test execution.
- **`dev_agent.py`**: Orchestrates multi-file generation, dependency installation, and iterative execution-fix loops.
- **`system_monitor.py`**: Samples hardware health metrics (CPU %, Memory %, Disk %, GPU temp/VRAM via NVML) without spawning blocking subshells.

### 2.5 `dashboard/`
- **`server.py`**: FastAPI application exposing:
  - `/ws/live-feed`: WebSocket streaming transcript updates and system metrics.
  - `/ws/phone-audio`: Binary WebSocket accepting PCM voice data from mobile devices.
  - `/api/upload`: Authenticated multipart file upload handler.
  - `/api/command`: AES-256-CBC encrypted command receiver.
- **`static/app.html`**: Web frontend equipped with mobile-responsive controls, real-time log inspector, and audio streamer.
- **`static/login.html`**: Authentication UI with integrated QR-code scanner and PIN field.

### 2.6 Entry Points & Utilities
- **`main.py`**: Core entry point. Boots PyQt6 UI, establishes `TatsuLive` session, initializes asyncio TaskGroups, binds single-instance port `39152`, and manages tool routing.
- **`ui.py`**: Implements desktop floating HUD, WebEngine view, API key initialization modal, and cross-thread Qt signal relays.
- **`wake_service.py`**: Independent background listener that detects wake phrases ("Hey Tatsu", "Wake up Tatsu") and triggers `main.py`.
