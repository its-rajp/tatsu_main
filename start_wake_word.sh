#!/usr/bin/env bash
# ==============================================================================
# TATSU AI Companion — Background Wake Word Listener (macOS)
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ -d ".venv" ]; then
    PYTHON_EXE="$DIR/.venv/bin/python"
else
    PYTHON_EXE="python3"
fi

echo "============================================================"
echo "      👂 TATSU Background Wake Word Service (macOS)        "
echo "============================================================"
echo "Listening for: 'Hey Tatsu' or 'Wake up Tatsu'"
echo "Press Ctrl+C to stop listening."
echo ""

"$PYTHON_EXE" "$DIR/wake_service.py" "$@"
