import webbrowser, subprocess, time, os
from urllib.parse import urlparse, quote_plus
from .storage import log, read_apps
ALLOWED_DOMAINS = {"docs.python.org", "developers.openai.com", "platform.openai.com"}
def open_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in ALLOWED_DOMAINS: raise ValueError("Only approved HTTPS documentation domains are allowed.")
    webbrowser.open(url); log("tool", {"tool": "open_url", "url": url}); return f"Opened {url}"

def open_browser_url(url, confirmed=False):
    """Open a user-requested HTTPS URL only after explicit confirmation."""
    if not confirmed:
        return {"requires_confirmation": True, "risk": "This opens a browser page.", "url": url}
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Only complete HTTPS URLs can be opened.")
    webbrowser.open(url)
    log("tool", {"tool": "open_browser_url", "url": url, "confirmed": True})
    return {"ok": True, "result": f"Opened {url}"}

def open_whatsapp_draft(phone, text, confirmed=False):
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) < 8: raise ValueError("Provide a complete phone number with country code.")
    if not text.strip(): raise ValueError("Message text is required.")
    if not confirmed: return {"requires_confirmation": True, "risk": "This opens a WhatsApp message draft.", "phone": digits, "text": text}
    url = f"https://web.whatsapp.com/send?phone={digits}&text={quote_plus(text)}"
    webbrowser.open(url); log("tool", {"tool": "open_whatsapp_draft", "phone": digits, "confirmed": True}); return {"ok": True, "result": "WhatsApp draft opened. Press Send in WhatsApp to send it."}

ALLOWED_APPS = {"chrome": "chrome.exe", "notepad": "notepad.exe", "calculator": "calc.exe"}
def open_app(name, confirmed=False, executable=None):
    key = str(name).casefold().strip()
    is_builtin = key in ALLOWED_APPS
    entry = None if is_builtin else next((item for item in read_apps() if str(item.get("name", "")).casefold() == key), None)
    if not is_builtin and not entry: raise ValueError("That application is not in SARA's user-approved app list.")
    target = ALLOWED_APPS[key] if is_builtin else str(entry.get("executable", ""))
    if executable is not None and os.path.normcase(os.path.abspath(str(executable))) != os.path.normcase(os.path.abspath(target)):
        raise ValueError("The executable path changed after the app was approved.")
    if not is_builtin and (not os.path.isabs(target) or not target.lower().endswith(".exe") or not os.path.isfile(target)):
        raise ValueError("The approved executable is missing or invalid. Update its app entry first.")
    if not confirmed: return {"requires_confirmation": True, "risk": "This launches a Windows application.", "app": key, "executable": target}
    subprocess.Popen([target], shell=False)
    # Give Windows time to create and focus the new top-level window before a
    # subsequent confirmation-gated keyboard action targets the focused app.
    time.sleep(1.0)
    log("tool", {"tool": "open_app", "app": key, "custom": not is_builtin, "confirmed": True})
    return {"ok": True, "launch_requested": True, "window_verified": False, "result": f"Windows was asked to launch {key}. The visible window has not been verified."}

def open_email_draft(to, subject, body, confirmed=False):
    recipient = str(to).strip()
    if "@" not in recipient: raise ValueError("Provide a valid email recipient.")
    if not confirmed: return {"requires_confirmation": True, "risk": "This opens an email draft.", "to": recipient, "subject": subject}
    url = f"mailto:{recipient}?subject={quote_plus(str(subject))}&body={quote_plus(str(body))}"
    webbrowser.open(url); log("tool", {"tool": "open_email_draft", "to": recipient, "confirmed": True}); return {"ok": True, "result": "Email draft opened. Review it and press Send to send it."}
