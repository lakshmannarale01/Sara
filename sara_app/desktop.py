"""Confirmation-gated Windows desktop actions for SARA."""
import re
import pyautogui
from .storage import log

pyautogui.PAUSE = 0.08
pyautogui.FAILSAFE = True

def click_point(x, y, confirmed=False):
    try: point = (int(x), int(y))
    except (TypeError, ValueError): raise ValueError("x and y must be screen coordinates.")
    width, height = pyautogui.size()
    if not (0 <= point[0] < width and 0 <= point[1] < height): raise ValueError(f"Coordinates must be inside the current {width}x{height} screen.")
    if not confirmed: return {"requires_confirmation": True, "risk": "This clicks the current Windows desktop at the specified coordinates.", "x": point[0], "y": point[1]}
    pyautogui.click(*point); log("desktop_action", {"action": "click_point", "x": point[0], "y": point[1], "confirmed": True})
    return {"ok": True, "result": f"Clicked screen coordinate ({point[0]}, {point[1]})."}

def type_text(text, confirmed=False):
    value = str(text or "")
    if not value: raise ValueError("Text is required.")
    if len(value) > 2000: raise ValueError("Text is limited to 2000 characters.")
    if not confirmed: return {"requires_confirmation": True, "risk": "This types text into the currently focused application.", "text": value}
    pyautogui.write(value, interval=0.01)
    log("desktop_action", {"action": "type_text", "characters": len(value), "confirmed": True})
    return {"ok": True, "result": "Text typed into the focused application."}

def press_hotkey(keys, confirmed=False):
    if not isinstance(keys, list) or not keys or len(keys) > 4: raise ValueError("keys must be a list of 1 to 4 key names.")
    normalized = [str(key).strip().lower() for key in keys]
    allowed = {"ctrl", "shift", "alt", "win", "enter", "esc", "tab", "space", "backspace", "delete", "home", "end", "left", "right", "up", "down", "c", "v", "x", "a", "f", "s"}
    if any(key not in allowed and not re.fullmatch(r"f(?:[1-9]|1[0-2])", key) for key in normalized): raise ValueError("That key is not in SARA's safe key allowlist.")
    if not confirmed: return {"requires_confirmation": True, "risk": "This sends a keyboard shortcut to the focused application.", "keys": normalized}
    pyautogui.press(normalized[0]) if len(normalized) == 1 else pyautogui.hotkey(*normalized)
    log("desktop_action", {"action": "press_hotkey", "keys": normalized, "confirmed": True})
    return {"ok": True, "result": "Keyboard action sent to the focused application."}
