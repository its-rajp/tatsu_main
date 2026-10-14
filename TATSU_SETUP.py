"""
TATSU SETUP SCRIPT

This is a portable first-time setup script for the TATSU AI Companion.
It verifies project integrity, checks Python version, installs dependencies,
configures API keys, and prepares the environment for running the assistant.
"""
import os
import sys
import subprocess
import shutil
import json
from datetime import datetime
from pathlib import Path

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = Path(__file__).resolve().parent

MARKER_FILES = [
    "main.py",
    "ui.py",
    "requirements.txt",
    "core/tts.py",
    "actions/browser_control.py",
    "dashboard/server.py",
]

def print_separator():
    print("=" * 60)

def check_marker_files():
    for marker in MARKER_FILES:
        if not (SCRIPT_DIR / marker).exists():
            return False
    
    config_json = SCRIPT_DIR / "config" / "api_keys.json"
    config_example = SCRIPT_DIR / "config" / "api_keys.json.example"
    
    if not (config_json.exists() or config_example.exists()):
        return False
        
    return True

def check_python_version():
    print("[INFO] Checking Python version...")
    if sys.version_info < (3, 10):
        print(f"[ERROR] Python 3.10 or higher is required. Found Python {sys.version_info.major}.{sys.version_info.minor}")
        sys.exit(1)
    print(f"[OK] Python {sys.version_info.major}.{sys.version_info.minor} verified.")

def upgrade_pip():
    print("[INFO] Upgrading pip...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], 
                       capture_output=True, check=True)
        print("[OK] Pip upgraded quietly.")
    except Exception as e:
        print(f"[WARN] Failed to upgrade pip: {e}")

def install_requirements():
    print("[INFO] Installing requirements.txt...")
    req_file = SCRIPT_DIR / "requirements.txt"
    if not req_file.exists():
        print(f"[ERROR] {req_file.name} not found!")
        sys.exit(1)
        
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req_file)], 
                       check=True)
        print("[OK] Requirements installed.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to install requirements: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error installing requirements: {e}")
        sys.exit(1)

def install_playwright_chromium():
    print("[INFO] Installing Playwright Chromium...")
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], 
                       check=True)
        print("[OK] Playwright Chromium installed.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to install Playwright Chromium: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error installing Playwright Chromium: {e}")
        sys.exit(1)

def setup_api_keys():
    print("[INFO] Setting up config/api_keys.json...")
    config_dir = SCRIPT_DIR / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    api_keys_file = config_dir / "api_keys.json"
    api_keys_example = config_dir / "api_keys.json.example"
    
    if api_keys_file.exists():
        print("[OK] api_keys.json already exists.")
        return
        
    if api_keys_example.exists():
        try:
            shutil.copy(str(api_keys_example), str(api_keys_file))
            print("[OK] Copied api_keys.json.example to api_keys.json.")
        except Exception as e:
            print(f"[ERROR] Failed to copy example config: {e}")
            sys.exit(1)
    else:
        default_config = {
            "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",
            "os_system": "windows" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux",
            "morning_brief_enabled": True,
            "assistant_name": "TATSU",
            "user_name": "",
            "ui_color": "#ff9f43"
        }
        try:
            with open(api_keys_file, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            print("[OK] Created default api_keys.json.")
        except Exception as e:
            print(f"[ERROR] Failed to create api_keys.json: {e}")
            sys.exit(1)

def write_setup_marker():
    marker_file = SCRIPT_DIR / ".tatsu_setup_complete"
    try:
        with open(marker_file, "w", encoding="utf-8") as f:
            f.write(f"Setup completed on: {datetime.now().isoformat()}")
        print("[OK] Wrote setup completion marker.")
    except Exception as e:
        print(f"[WARN] Failed to write setup marker: {e}")

def main():
    try:
        # STEP 1: Integrity Check
        if check_marker_files():
            print("[OK] TATSU base project verified.")
        else:
            print("[WARN] Some marker files were missing. Proceeding with verification...")
                
        # STEP 2: Check Python Version
        check_python_version()
        
        # STEP 3: Upgrade pip
        upgrade_pip()
        
        # STEP 4: Install requirements.txt
        install_requirements()
        
        # STEP 5: Install Playwright Chromium
        install_playwright_chromium()
        
        # STEP 6: Setup config/api_keys.json
        setup_api_keys()
        
        # STEP 7: Write Setup Complete Marker
        write_setup_marker()
        
        # STEP 8: Print Success
        print_separator()
        print(" TATSU SETUP COMPLETE!")
        print_separator()
        print("")
        print(" To launch TATSU:")
        print("   python main.py")
        print("   OR double-click START_TATSU.bat")
        print("")
        print(" IMPORTANT: Add your Gemini API key in config/api_keys.json")
        print(" Get a free key: https://aistudio.google.com/apikey")
        print_separator()
        
        choice = input("Do you want to launch TATSU now? (Press Enter to launch, N to exit): ")
        if choice.strip().lower() != 'n':
            print("[INFO] Launching TATSU...")
            subprocess.run([sys.executable, "main.py"], cwd=str(SCRIPT_DIR))
            
    except KeyboardInterrupt:
        print("\n[WARN] Setup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
