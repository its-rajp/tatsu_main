"""Desktop Perception Engine for TATSU Sovereign Agent — Phase 1-A.

Provides fast, local, privacy-first screen observation:
- Active window identification (macOS AppKit/Quartz, Windows win32gui, Linux xdotool)
- RAM-only region or screen capture via mss
- Local OCR via PaddleOCR (with graceful fallback if uninstalled)
- In-memory processing: zero image disk writes.
"""

import os
import re
import sys
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import numpy as np

try:
    import mss
    _MSS_AVAILABLE = True
except ImportError:
    mss = None
    _MSS_AVAILABLE = False

# Lazy PaddleOCR check
_PADDLE_AVAILABLE = False
_PaddleOCR = None

try:
    from paddleocr import PaddleOCR
    _PaddleOCR = PaddleOCR
    _PADDLE_AVAILABLE = True
except (ImportError, Exception):
    _PaddleOCR = None
    _PADDLE_AVAILABLE = False

logger = logging.getLogger("TATSU.Perception")
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "perception.yaml"


class ScreenWatcher:
    """Watches the user desktop context safely and locally in RAM."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config = self._load_config(config_path or CONFIG_PATH)
        self.enabled = self.config.get("enabled", True)
        self.ocr_language = self.config.get("ocr_language", "en")
        self.max_chars = int(self.config.get("max_chars", 2000))
        self.privacy_mode = self.config.get("privacy_mode", "strict")

        self._ocr_engine = None
        self._sct = None

        if self.enabled and _MSS_AVAILABLE:
            try:
                # Use MSS instance
                mss_cls = getattr(mss, "MSS", mss.mss)
                self._sct = mss_cls()
            except Exception as e:
                logger.warning(f"Could not initialize mss: {e}")

        # Initialize OCR engine lazily if available
        if self.enabled and _PADDLE_AVAILABLE:
            try:
                self._ocr_engine = _PaddleOCR(
                    use_angle_cls=False,
                    lang=self.ocr_language,
                    show_log=False,
                )
            except Exception as e:
                logger.warning(f"PaddleOCR init deferred or failed: {e}")
                self._ocr_engine = None

    def _load_config(self, path: Path) -> dict:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Error loading {path}: {e}")
        return {
            "enabled": True,
            "ocr_language": "en",
            "max_chars": 2000,
            "privacy_mode": "strict",
        }

    def get_active_window(self) -> Tuple[str, Optional[Dict[str, int]]]:
        """Detect the title and screen coordinates of the active window."""
        window_title = "Desktop"
        bounds = None

        platform = sys.platform

        if platform == "darwin":
            # macOS: AppKit frontmost application
            try:
                from AppKit import NSWorkspace
                ws = NSWorkspace.sharedWorkspace()
                front_app = ws.frontmostApplication()
                if front_app:
                    app_name = front_app.localizedName() or "Unknown App"
                    window_title = f"{app_name}"

                # Try to get active window title via Quartz if available
                try:
                    import Quartz
                    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
                    window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
                    for win in window_list:
                        owner = win.get(Quartz.kCGWindowOwnerName, "")
                        w_title = win.get(Quartz.kCGWindowName, "")
                        w_bounds = win.get(Quartz.kCGWindowBounds, {})
                        
                        # Match front application owner or focused window
                        if front_app and owner == front_app.localizedName():
                            if w_title:
                                window_title = f"{owner} - {w_title}"
                            if w_bounds and w_bounds.get("Width", 0) > 100:
                                bounds = {
                                    "top": int(w_bounds.get("Y", 0)),
                                    "left": int(w_bounds.get("X", 0)),
                                    "width": int(w_bounds.get("Width", 800)),
                                    "height": int(w_bounds.get("Height", 600)),
                                }
                            break
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"macOS window detection fallback: {e}")

        elif platform.startswith("win"):
            # Windows: win32gui / pygetwindow
            try:
                import win32gui
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd)
                if title:
                    window_title = title
                rect = win32gui.GetWindowRect(hwnd)
                if rect:
                    bounds = {
                        "left": rect[0],
                        "top": rect[1],
                        "width": max(100, rect[2] - rect[0]),
                        "height": max(100, rect[3] - rect[1]),
                    }
            except Exception as e:
                logger.debug(f"Windows window detection error: {e}")

        elif platform.startswith("linux"):
            # Linux: xdotool fallback
            try:
                import subprocess
                out = subprocess.check_output(["xdotool", "getactivewindow", "getwindowname"], text=True)
                if out.strip():
                    window_title = out.strip()
            except Exception:
                pass

        return window_title, bounds

    def capture_active_window(self) -> Tuple[str, Optional[np.ndarray]]:
        """Captures only the active window (or primary screen) directly into RAM.
        
        Returns:
            (window_title, numpy_image_array) or (window_title, None) on failure.
        """
        if not self.enabled or not self._sct:
            return "Display Disabled", None

        window_title, bounds = self.get_active_window()

        try:
            # If bounds are valid, grab bounded region, else primary monitor
            if bounds and bounds.get("width", 0) > 50 and bounds.get("height", 0) > 50:
                region = {
                    "top": bounds["top"],
                    "left": bounds["left"],
                    "width": bounds["width"],
                    "height": bounds["height"],
                }
            else:
                monitors = self._sct.monitors
                region = monitors[1] if len(monitors) > 1 else monitors[0]

            shot = self._sct.grab(region)
            # Convert mss ScreenShot to numpy RGB array in RAM
            img = np.array(shot)
            # Drop alpha channel if present (BGRA -> RGB)
            if img.shape[2] == 4:
                img = img[:, :, :3]
            return window_title, img

        except Exception as e:
            logger.warning(f"Screen capture failed: {e}")
            return window_title, None

    def extract_text(self, image_array: Optional[np.ndarray]) -> str:
        """Runs local OCR on in-memory image array and returns clean text."""
        if image_array is None:
            return ""

        if self._ocr_engine is None:
            # Fallback if PaddleOCR is not installed or failed to load
            return "[OCR Engine not installed - capture in memory OK]"

        try:
            result = self._ocr_engine.ocr(image_array, cls=False)
            if not result or not result[0]:
                return ""

            lines = []
            for line in result[0]:
                if len(line) >= 2 and len(line[1]) >= 1:
                    text = line[1][0]
                    confidence = line[1][1] if len(line[1]) > 1 else 1.0
                    if confidence > 0.4:
                        lines.append(text.strip())

            extracted = " ".join(lines)
            # Clean up excessive whitespace
            extracted = re.sub(r"\s+", " ", extracted).strip()
            # Truncate to maximum characters allowed
            if len(extracted) > self.max_chars:
                extracted = extracted[: self.max_chars] + "..."
            return extracted

        except Exception as e:
            logger.warning(f"OCR extraction failed: {e}")
            return ""

    def get_context_summary(self) -> Dict[str, Any]:
        """Captures window, runs OCR in RAM, and returns a structured summary dict.
        
        Images are immediately discarded from RAM once this method returns.
        """
        if not self.enabled:
            return {
                "window_title": "Disabled",
                "visible_content": "",
            }

        window_title, img = self.capture_active_window()
        visible_content = ""
        try:
            if img is not None:
                visible_content = self.extract_text(img)
        finally:
            # Ensure RAM image reference is freed immediately
            del img

        return {
            "window_title": window_title,
            "visible_content": visible_content,
        }
