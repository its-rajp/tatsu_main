@echo off
title TATSU -- Wake Word Service
color 0B

echo ==============================================
echo   TATSU -- Starting Wake Word Listener...
echo ==============================================

cd /d "%~dp0"

REM ── Check if setup has been completed ──────────────────────────────
if not exist ".tatsu_setup_complete" (
    echo First-time launch detected. Running setup first...
    echo.
    python TATSU_SETUP.py
    if %ERRORLEVEL% NEQ 0 (
        echo Setup failed. Check the messages above.
        pause
        exit /b %ERRORLEVEL%
    )
)

echo.
echo Launching Wake Word Listener ("wake up tatsu" / "hey tatsu")...
python wake_service.py

echo.
pause
