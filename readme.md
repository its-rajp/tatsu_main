# TATSU AI Desktop Companion

> **TATSU** is a next-generation AI Desktop Companion powered by Google Gemini. It features hands-free voice recognition, real-time voice synthesis, warm amber visual HUD, automated desktop control, browser automation, system monitoring, and a remote web dashboard.

---

## Features

- **Google Gemini Live Audio Engine** -- Ultra-fast LLM with native bi-directional audio and text models
- **Hands-Free Voice** -- Real-time speech recognition, neural TTS, and wake word ("Wake up Tatsu" or "Hey Tatsu")
- **Computer Control** -- Volume, brightness, media, app launcher, window management, keyboard shortcuts
- **Web Automation** -- Built-in Playwright engine for automated browsing, search, and page extraction
- **Hardware Monitor** -- Real-time CPU, RAM, GPU, battery, and network telemetry
- **Remote Dashboard** -- Web-based control panel accessible from any browser or phone
- **File Processing** -- Read, write, analyze files and generate presentations
- **Code Assistant** -- Write, debug, and explain code across languages

---

## Quick Start (Any Windows 10/11 PC)

### Prerequisites

- **Python 3.10+** installed with "Add python.exe to PATH" checked
  - Download from [python.org](https://python.org) if needed
- **Internet connection** for first-time setup (downloads dependencies)

### Option 1: Automatic Setup (Recommended)

```
1. Download or clone this repository
2. Double-click TATSU_SETUP.bat
3. Done! TATSU installs all dependencies and launches automatically.
```

### Option 2: Manual Setup

```bash
cd Tatsumain-main
python TATSU_SETUP.py
```

### Option 3: Step-by-Step Manual

```bash
cd Tatsumain-main
pip install -r requirements.txt
python -m playwright install chromium
python main.py
```

---

## First Launch

On the very first launch, TATSU will ask for your **Gemini API Key**.

1. Get a free key at [Google AI Studio](https://aistudio.google.com/apikey)
2. Paste it when prompted, or edit `config/api_keys.json` manually
3. Optional: if pyaudio error occurs, ensure `pyaudio` is installed in your python environment

---

## Wake Word (Hands-Free Activation)

To keep TATSU listening in the background:

- Double-click **`Start_TATSU_Wake_Word.bat`**
- Say **"Wake up Tatsu"** or **"Hey Tatsu"** to activate

---

## Repository Structure

```
TATSU/
|-- TATSU_SETUP.py              # Portable first-time setup script
|-- TATSU_SETUP.bat             # 1-click setup launcher (runs TATSU_SETUP.py)
|-- START_TATSU.bat             # Main launcher (auto-runs setup on first use)
|-- Start_TATSU_Wake_Word.bat   # Wake word background listener
|-- main.py                     # Main companion entry point
|-- ui.py                       # PyQt6 WebEngine visual HUD (Amber theme)
|-- wake_service.py             # Always-on voice wake word service
|-- requirements.txt            # Python package dependencies
|-- config/
|   |-- api_keys.json.example   # Template for API key configuration
|   |-- __init__.py             # Config loader module
|   +-- jarvis.ico              # Application icon
|-- core/                       # LLM client, TTS, STT engines
|-- actions/                    # Tool modules (browser, system, desktop, etc.)
|-- dashboard/                  # Remote web dashboard server & assets
+-- memory/                     # Local companion memory & preferences
```

---

## How Sharing Works

This project is **fully portable** -- no hardcoded paths.

**To share TATSU with someone:**

1. Push this repo to GitHub (or send as ZIP)
2. Recipient clones/extracts to ANY folder on their PC
3. They double-click `TATSU_SETUP.bat` (or run `python TATSU_SETUP.py`)
4. Everything installs automatically
5. TATSU launches and works immediately

**The setup script automatically:**
- Verifies all project files are present
- Downloads missing files from GitHub if needed
- Installs all Python packages (PyQt6, sounddevice, google-genai, etc.)
- Installs Playwright Chromium browser engine
- Creates default configuration files
- Provides manual download links if auto-download fails

---

## Requirements

All dependencies are listed in `requirements.txt` and installed automatically by the setup script:

- PyQt6 + PyQt6-WebEngine
- sounddevice, PyAudio, SpeechRecognition
- google-genai, google-generativeai
- playwright, requests, beautifulsoup4
- numpy, opencv-python, pillow
- psutil, pyautogui, pyperclip
- fastapi, uvicorn, cryptography
- And more (see requirements.txt)

---

## License

Contributions, issues, and feature requests are welcome!
