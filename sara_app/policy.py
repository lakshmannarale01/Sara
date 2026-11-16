"""Local action policy and emergency-stop state for SARA."""
from threading import RLock
from urllib.parse import parse_qs, urlparse, unquote

from . import config

_lock = RLock()
_stopped = False

# High-impact actions stay confirmation gated regardless of UI preferences.
ACTION_RISK = {
    "create_reminder": "medium", "delete_reminder": "high",
    "create_task": "low", "complete_task": "low", "delete_task": "high",
    "create_event": "medium", "delete_event": "high",
    "save_memory": "medium", "approve_memory": "medium", "update_memory": "high", "delete_memory": "high",
    "save_pronunciation": "low", "delete_pronunciation": "medium",
    "add_custom_app": "medium", "delete_custom_app": "medium",
    "save_capability_request": "low", "delete_capability_request": "medium",
    "write_file": "high", "delete_file": "critical",
    "open_app": "medium", "notepad_write": "high", "open_browser_url": "medium",
    "browser_open": "medium", "youtube_play": "medium", "browser_click_text": "high", "browser_fill": "high",
    "media_control": "low", "save_routine": "medium", "delete_routine": "medium", "run_routine": "medium",
    "type_text": "high", "hotkey": "high", "click_point": "high",
    "email_draft": "high", "whatsapp_draft": "high", "whatsapp_send": "critical",
}

def set_stopped(value):
    global _stopped
    with _lock:
        _stopped = bool(value)
        return _stopped

def is_stopped():
    with _lock:
        return _stopped

def access_mode():
    """Restore the explicit local preference; unknown/corrupt records fail closed."""
    from .storage import _read_json_list
    with _lock:
        records = _read_json_list(config.DATA_DIR / "access_policy.json")
        return "trusted" if len(records) == 1 and records[0].get("mode") == "trusted" else "review"


def set_access_mode(mode):
    """Persist one reviewed preference using the existing atomic/recovery writer."""
    if not isinstance(mode, str) or mode not in {"review", "trusted"}:
        raise ValueError("Access mode must be review or trusted.")
    from .storage import _write_json_atomic
    with _lock:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(config.DATA_DIR / "access_policy.json", [{"mode": mode}])
        return mode


def routine_action(action, payload=None):
    """Allow only bounded, repeatable browsing/media and built-in app launches.

    Trusted mode never approves an unknown action, arbitrary focused-window
    input, sending, memory changes, file writes or a custom executable.
    """
    if not isinstance(payload, dict):
        return False
    if action == "media_control":
        from .system_controls import normalize_media_payload
        try:
            normalize_media_payload({key: value for key, value in payload.items() if key not in {"session_id", "proposal_id", "confirmed", "type", "label"}})
            return True
        except (ValueError, TypeError):
            return False
    if action == "run_routine":
        from .routines import validate_run_payload
        try:
            validate_run_payload({key: value for key, value in payload.items() if key not in {"session_id", "proposal_id", "confirmed", "type", "label"}})
            return True
        except (ValueError, TypeError):
            return False
    if action == "youtube_play":
        query = payload.get("query")
        return isinstance(query, str) and 0 < len(query.strip()) <= 200 and not any(ord(c) < 32 for c in query)
    if action == "open_app":
        from .tools import ALLOWED_APPS
        app = payload.get("app")
        if not isinstance(app, str) or app.casefold().strip() not in ALLOWED_APPS:
            return False
        executable = payload.get("executable")
        return executable is None or executable == ALLOWED_APPS[app.casefold().strip()]
    if action not in {"open_browser_url", "browser_open"}:
        return False
    url = payload.get("url")
    if not isinstance(url, str) or len(url) > 2000 or any(ord(c) < 32 for c in url):
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in {None, 443} or parsed.fragment:
            return False
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    query = parse_qs(parsed.query, keep_blank_values=True)
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        return ((parsed.path in {"", "/"} and not query)
                or (parsed.path == "/results" and set(query) <= {"search_query"} and bool(query.get("search_query", [""])[0]))
                or (parsed.path == "/watch" and set(query) <= {"v"} and bool(query.get("v", [""])[0])))
    if host in {"google.com", "www.google.com", "bing.com", "www.bing.com"}:
        return parsed.path == "/search" and set(query) <= {"q"} and bool(query.get("q", [""])[0])
    if host in {"en.wikipedia.org", "hi.wikipedia.org"}:
        return parsed.path.startswith("/wiki/") and ":" not in unquote(parsed.path[6:]) and not query
    return False


def inspect_action(action, confirmed=False, payload=None):
    action = str(action or "unknown")
    risk = ACTION_RISK.get(action, "high")
    if is_stopped():
        return {"allowed": False, "stopped": True, "risk": risk, "error": "SARA is stopped. Resume it from the dashboard before requesting actions."}
    trusted = not confirmed and access_mode() == "trusted" and routine_action(action, payload)
    if not confirmed and not trusted:
        return {"allowed": False, "requires_confirmation": True, "risk": risk, "action": action}
    return {"allowed": True, "risk": risk, "action": action, "automatic": trusted}
