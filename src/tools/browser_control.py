"""Browser Automation Control for TATSU Sovereign Agent — Phase 3.

Provides local, private, headless browser navigation, element interaction,
and text extraction using Playwright. No cloud tracking or sync.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from playwright.sync_api import sync_playwright, Playwright, Browser, Page
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    _PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger("TATSU.Browser")
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class BrowserAgent:
    """Manages an ephemeral local headless browser session."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright: Optional[Any] = None
        self._browser: Optional[Any] = None
        self._page: Optional[Any] = None

    def _ensure_page(self) -> Any:
        """Initializes Playwright browser and page on demand."""
        if not _PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright package is not installed.")

        if self._playwright is None:
            self._playwright = sync_playwright().start()

        if self._browser is None:
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )

        if self._page is None:
            self._page = self._browser.new_page()

        return self._page

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigates to the specified URL or local file path."""
        try:
            page = self._ensure_page()
            # If path is local file, prepend file://
            if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("file://"):
                local_path = Path(url).resolve()
                if local_path.exists():
                    url = local_path.as_uri()

            response = page.goto(url, timeout=15000)
            status = response.status if response else 200
            title = page.title()
            return {
                "success": True,
                "url": page.url,
                "title": title,
                "status_code": status,
            }
        except Exception as e:
            logger.warning(f"Browser navigation failed: {e}")
            return {
                "success": False,
                "url": url,
                "error": str(e),
            }

    def extract_text(self, selector: str = "body", max_chars: int = 3000) -> str:
        """Extracts visible text content from the specified DOM element."""
        try:
            page = self._ensure_page()
            element = page.wait_for_selector(selector, timeout=5000)
            if element:
                text = element.inner_text().strip()
                if len(text) > max_chars:
                    return text[:max_chars] + "\n...[Content truncated]"
                return text
            return f"Element '{selector}' not found."
        except Exception as e:
            return f"Extraction error: {str(e)}"

    def click_element(self, selector: str) -> Dict[str, Any]:
        """Simulates a user click on the specified CSS or XPath selector."""
        try:
            page = self._ensure_page()
            page.click(selector, timeout=5000)
            return {
                "success": True,
                "selector": selector,
                "current_url": page.url,
            }
        except Exception as e:
            return {
                "success": False,
                "selector": selector,
                "error": str(e),
            }

    def fill_form(self, selector: str, value: str) -> Dict[str, Any]:
        """Fills input text into the specified DOM form field."""
        try:
            page = self._ensure_page()
            page.fill(selector, value, timeout=5000)
            return {
                "success": True,
                "selector": selector,
            }
        except Exception as e:
            return {
                "success": False,
                "selector": selector,
                "error": str(e),
            }

    def take_screenshot(self, output_path: Optional[str] = None) -> str:
        """Captures viewport screenshot and saves to file."""
        try:
            page = self._ensure_page()
            path = output_path or str(BASE_DIR / "logs" / "browser_capture.png")
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=path)
            return f"Screenshot saved to {path}"
        except Exception as e:
            return f"Screenshot error: {str(e)}"

    def close(self) -> None:
        """Closes browser page, context, and Playwright process cleanly."""
        try:
            if self._page:
                self._page.close()
                self._page = None
            if self._browser:
                self._browser.close()
                self._browser = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
        except Exception as e:
            logger.debug(f"Browser cleanup error: {e}")
