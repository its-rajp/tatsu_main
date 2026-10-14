#!/usr/bin/env bash
# ==============================================================================
# TATSU AI Companion — macOS Setup Script
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "============================================================"
echo "          🐉 TATSU AI Desktop Companion — Setup (macOS)     "
echo "============================================================"
echo ""

# 1. Verify Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 could not be found. Please install Python 3.10+ (brew install python@3.11)."
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✅ Found Python $PY_VER"

# 2. Check for portaudio (recommended for microphone on macOS)
if ! brew list portaudio &>/dev/null; then
    if command -v brew &> /dev/null; then
        echo "📦 Installing PortAudio via Homebrew (required for microphone input)..."
        brew install portaudio || true
    else
        echo "ℹ️  Homebrew not found. If PyAudio fails to install, install Homebrew from https://brew.sh and run: brew install portaudio"
    fi
fi

# 3. Create or use virtual environment
if [ ! -d ".venv" ]; then
    echo "🔧 Creating Python virtual environment in .venv..."
    python3 -m venv .venv
fi

echo "🔌 Activating virtual environment..."
source .venv/bin/activate

# 4. Upgrade pip and install requirements
echo "📦 Installing Python packages from requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Install Playwright browser engine
echo "🌐 Installing Playwright Chromium browser..."
python -m playwright install chromium || echo "⚠️ Playwright browser install skipped or will finish on first run."

# 6. Ensure default config exists
mkdir -p config
if [ ! -f "config/api_keys.json" ]; then
    echo "📝 Creating initial config/api_keys.json..."
    cat << 'EOF' > config/api_keys.json
{
    "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",
    "os_system": "darwin",
    "morning_brief_enabled": true,
    "assistant_name": "TATSU",
    "user_name": "",
    "ui_color": "#ff9f43"
}
EOF
fi

# 7. Make helper scripts executable
chmod +x start_tatsu.sh 2>/dev/null || true
chmod +x start_wake_word.sh 2>/dev/null || true

echo ""
echo "============================================================"
echo "  ✅ TATSU Setup Complete!                                   "
echo "============================================================"
echo "  1. Add your Gemini API key from https://aistudio.google.com/apikey"
echo "     to config/api_keys.json (or paste it into the UI on launch)."
echo "  2. To start TATSU:            ./start_tatsu.sh"
echo "  3. To start Wake Word listen: ./start_wake_word.sh"
echo "============================================================"
