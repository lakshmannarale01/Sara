"""Confirmation-gated browser actions owned by one Playwright worker thread."""
from concurrent.futures import ThreadPoolExecutor
import threading
from urllib.parse import urlparse
from urllib.parse import quote_plus

from .config import ROOT
from .storage import log

class _BrowserWorker:
    """Serialize Playwright ownership and cancel work that has not started."""

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sara-browser")
        self._lock = threading.Lock()
        self._pending = set()
        self._started = False
        self._shutdown_requested = False
        self._owner = None

    def _execute(self, operation, args):
        self._owner = threading.get_ident()
        return operation(*args)

    def _forget(self, future):
        with self._lock:
            self._pending.discard(future)

    def run(self, operation, *args):
        with self._lock:
            if self._shutdown_requested:
                raise RuntimeError("SARA browser is shutting down; no new actions can start.")
            future = self._executor.submit(self._execute, operation, args)
            self._pending.add(future)
            self._started = True
        future.add_done_callback(self._forget)
        return future.result()

    def shutdown(self, cleanup):
        with self._lock:
            if self._shutdown_requested:
                return
            self._shutdown_requested = True
            pending = list(self._pending)
            started = self._started
        for future in pending:
            future.cancel()
        on_owner = threading.get_ident() == self._owner
        try:
            if started:
                # Cleanup is queued behind the active operation, after pending
                # actions have been cancelled. No operation is retried.
                return cleanup() if on_owner else self._executor.submit(self._execute, cleanup, ()).result()
        finally:
            # An unused executor has no thread; shutdown must keep it that way.
            self._executor.shutdown(wait=not on_owner, cancel_futures=True)


# Sync Playwright objects must stay on the thread that created them. The HTTP
# server uses a new request thread, so a lock alone cannot preserve ownership.
_worker = _BrowserWorker()
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
    if _playwright is None:
        _playwright = sync_playwright().start()
    context = _playwright.chromium.launch_persistent_context(str(profile), headless=False)
    _context = context
    context.on("close", lambda *_: _forget_context(context))
    return _context


def _forget_context(context):
    global _context
    if _context is context:
        _context = None


def _close_browser():
    global _playwright, _context
    context, playwright = _context, _playwright
    _context = _playwright = None
    errors = []
    for resource, method in ((context, "close"), (playwright, "stop")):
        if resource is not None:
            try:
                getattr(resource, method)()
            except Exception as exc:
                errors.append({"operation": method, "error": str(exc)})
    return errors


def shutdown_browser():
    """Reject new actions, cancel queued actions and close on the owner thread."""
    for error in _worker.shutdown(_close_browser) or []:
        log("browser_shutdown_error", error)


def _run_browser(operation, *args):
    """Run browser work on its owner thread; propagate errors to the caller."""
    return _worker.run(operation, *args)


def _page_for_browser(target):
    context = _context_for_browser()
    pages = [page for page in context.pages if not page.is_closed()]
    # Prefer the already loaded target when more than one tab is open.
    return next((page for page in pages if page.url == target), None) or (pages[0] if pages else context.new_page())


def _navigate(page, target, *, force=False, timeout=15000):
    if force or page.url != target:
        page.goto(target, wait_until="domcontentloaded", timeout=timeout)
    else:
        # A matching URL may still be loading. Preserve readiness without a
        # second network navigation before a click or fill.
        page.wait_for_load_state("domcontentloaded", timeout=timeout)


def _open_page(target):
    _navigate(_page_for_browser(target), target, force=True)


def _click_text(target, label):
    page = _page_for_browser(target)
    _navigate(page, target)
    page.get_by_text(label, exact=True).first.click(timeout=8000)


def _fill_text(target, field, content):
    page = _page_for_browser(target)
    _navigate(page, target)
    page.get_by_label(field, exact=True).fill(content, timeout=8000)


def _whatsapp_send(target):
    page = _page_for_browser(target)
    _navigate(page, target, force=True, timeout=20000)
    try:
        page.get_by_role("button", name="Send").click(timeout=15000)
    except Exception:
        page.locator("span[data-icon='send']").last.click(timeout=8000)


def open_page(url, confirmed=False):
    target = _check_url(url)
    if not confirmed:
        return {"requires_confirmation": True, "risk": "This opens a visible controlled browser page.", "url": target}
    _run_browser(_open_page, target)
    log("browser_action", {"action": "open_page", "url": target, "confirmed": True})
    return {"ok": True, "result": f"Opened {target} in SARA's controlled browser."}


def click_text(url, text, confirmed=False):
    target = _check_url(url)
    label = str(text or "").strip()
    if not label or len(label) > 120: raise ValueError("Visible text is required and must be under 120 characters.")
    if not confirmed:
        return {"requires_confirmation": True, "risk": "This opens a page and clicks an element matching visible text.", "url": target, "text": label}
    _run_browser(_click_text, target, label)
    log("browser_action", {"action": "click_text", "url": target, "text": label, "confirmed": True})
    return {"ok": True, "result": f"Clicked visible text '{label}'."}


def fill_text(url, label, value, confirmed=False):
    target = _check_url(url)
    field = str(label or "").strip(); content = str(value or "")
    if not field or not content: raise ValueError("Field label and value are required.")
    if len(field) > 120 or len(content) > 2000: raise ValueError("Field label or value is too long.")
    if not confirmed:
        return {"requires_confirmation": True, "risk": "This opens a page and fills a labeled form field.", "url": target, "label": field, "value": content}
    _run_browser(_fill_text, target, field, content)
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
    _run_browser(_whatsapp_send, target)
    log("browser_action", {"action": "whatsapp_send", "phone": digits, "confirmed": True})
    return {"ok": True, "result": "WhatsApp message sent through the controlled browser."}
