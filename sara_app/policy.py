"""Local action policy and emergency-stop state for SARA."""
from threading import RLock

_lock = RLock()
_stopped = False

# High-impact actions stay confirmation gated regardless of UI preferences.
ACTION_RISK = {
    "create_reminder": "medium", "delete_reminder": "high",
    "create_task": "low", "complete_task": "low", "delete_task": "high",
    "create_event": "medium", "delete_event": "high",
    "save_memory": "medium", "delete_memory": "high",
    "save_pronunciation": "low", "delete_pronunciation": "medium",
    "add_custom_app": "medium", "delete_custom_app": "medium",
    "save_capability_request": "low", "delete_capability_request": "medium",
    "write_file": "high", "delete_file": "critical",
    "open_app": "medium", "notepad_write": "high", "open_browser_url": "medium",
    "browser_open": "medium", "browser_click_text": "high", "browser_fill": "high",
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

def inspect_action(action, confirmed=False):
    action = str(action or "unknown")
    risk = ACTION_RISK.get(action, "high")
    if is_stopped():
        return {"allowed": False, "stopped": True, "risk": risk, "error": "SARA is stopped. Resume it from the dashboard before requesting actions."}
    if not confirmed:
        return {"allowed": False, "requires_confirmation": True, "risk": risk, "action": action}
    return {"allowed": True, "risk": risk, "action": action}
