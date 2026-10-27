"""Confirmation-gated semantic browser actions using a dedicated Playwright profile."""
import threading
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import quote_plus

from .config import ROOT
from .storage import log

_lock = threading.RLock()
_playwright = None
_context = None


def _check_url(url):
    parsed = urlparse(str(url).strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Only complete HTTPS URLs can be controlled.")
    return parsed.geturl()


def _context_for_browser():
    global _playwright, _context
    if _context is not None:
        return _context
    from playwright.sync_api import sync_playwright
    profile = ROOT / "sara_data" / "browser_profile"
    profile.mkdir(parents=True, exist_ok=True)
    _playwright = sync_playwright().start()
    _context = _playwright.chromium.launch_persistent_context(str(profile), headless=False)
    return _context


def open_page(url, confirmed=False):
    target = _check_url(url)
    if not confirmed:
        return {"requires_confirmation": True, "risk": "This opens a visible controlled browser page.", "url": target}
    with _lock:
        page = _context_for_browser().pages[0] if _context_for_browser().pages else _context_for_browser().new_page()
        page.goto(target, wait_until="domcontentloaded", timeout=15000)
    log("browser_action", {"action": "open_page", "url": target, "confirmed": True})
    return {"ok": True, "result": f"Opened {target} in SARA's controlled browser."}


def click_text(url, text, confirmed=False):
    target = _check_url(url)
    label = str(text or "").strip()
    if not label or len(label) > 120: raise ValueError("Visible text is required and must be under 120 characters.")
    if not confirmed:
        return {"requires_confirmation": True, "risk": "This opens a page and clicks an element matching visible text.", "url": target, "text": label}
    with _lock:
        page = _context_for_browser().pages[0] if _context_for_browser().pages else _context_for_browser().new_page()
        page.goto(target, wait_until="domcontentloaded", timeout=15000)
        page.get_by_text(label, exact=True).first.click(timeout=8000)
    log("browser_action", {"action": "click_text", "url": target, "text": label, "confirmed": True})
    return {"ok": True, "result": f"Clicked visible text '{label}'."}


def fill_text(url, label, value, confirmed=False):
    target = _check_url(url)
    field = str(label or "").strip(); content = str(value or "")
    if not field or not content: raise ValueError("Field label and value are required.")
    if len(field) > 120 or len(content) > 2000: raise ValueError("Field label or value is too long.")
    if not confirmed:
        return {"requires_confirmation": True, "risk": "This opens a page and fills a labeled form field.", "url": target, "label": field, "value": content}
    with _lock:
        page = _context_for_browser().pages[0] if _context_for_browser().pages else _context_for_browser().new_page()
        page.goto(target, wait_until="domcontentloaded", timeout=15000)
        page.get_by_label(field, exact=True).fill(content, timeout=8000)
    log("browser_action", {"action": "fill_text", "url": target, "label": field, "confirmed": True})
    return {"ok": True, "result": f"Filled the '{field}' field."}


def whatsapp_send(phone, text, confirmed=False):
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    message = str(text or "").strip()
    if len(digits) < 8: raise ValueError("Provide a complete phone number with country code.")
    if not message or len(message) > 2000: raise ValueError("Message is required and must be under 2000 characters.")
    if not confirmed:
        return {"requires_confirmation": True, "risk": "This sends an external WhatsApp message after opening WhatsApp Web.", "phone": digits, "text": message}
    target = f"https://web.whatsapp.com/send?phone={digits}&text={quote_plus(message)}"
    with _lock:
        page = _context_for_browser().pages[0] if _context_for_browser().pages else _context_for_browser().new_page()
        page.goto(target, wait_until="domcontentloaded", timeout=20000)
        try:
            page.get_by_role("button", name="Send").click(timeout=15000)
        except Exception:
            page.locator("span[data-icon='send']").last.click(timeout=8000)
    log("browser_action", {"action": "whatsapp_send", "phone": digits, "confirmed": True})
    return {"ok": True, "result": "WhatsApp message sent through the controlled browser."}
