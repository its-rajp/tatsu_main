#!/usr/bin/env bash
# ==============================================================================
# TATSU AI Companion — macOS Launcher
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Use virtual environment python if present
if [ -d ".venv" ]; then
    PYTHON_EXE="$DIR/.venv/bin/python"
else
    PYTHON_EXE="python3"
fi

echo "============================================================"
echo "          🐉 Launching TATSU AI Desktop Companion            "
echo "============================================================"

# Auto-run setup if dependencies aren't installed yet
if ! "$PYTHON_EXE" -c "import sounddevice, google.genai, PyQt6" 2>/dev/null; then
    echo "⚠️  Missing dependencies. Running setup first..."
    chmod +x "$DIR/setup_tatsu.sh"
    "$DIR/setup_tatsu.sh"
fi

echo "🚀 Starting TATSU..."
"$PYTHON_EXE" "$DIR/main.py" "$@"
