"""Small, dependency-free colored console logging for SARA.

ANSI output is supported by modern Windows Terminal, PowerShell and most IDE
terminals. Set ``SARA_COLOR=0`` to disable colors when output is redirected.
"""

import os
import sys

RESET = "\x1b[0m"
COLORS = {
    "cyan": "\x1b[36m",
    "blue": "\x1b[94m",
    "green": "\x1b[92m",
    "yellow": "\x1b[93m",
    "magenta": "\x1b[95m",
    "red": "\x1b[91m",
    "dim": "\x1b[90m",
}


def colors_enabled():
    value = os.getenv("SARA_COLOR", "1").strip().lower()
    if value in {"0", "off", "false", "no"}:
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)()) or os.getenv("SARA_COLOR", "").strip() not in {"", "auto"}


def color_for(message):
    text = str(message).lower()
    if any(token in text for token in ("error", "failed", "exception", "traceback")):
        return COLORS["red"]
    if "boss:" in text:
        return COLORS["blue"]
    if "sara (" in text or "provider" in text or "connected" in text:
        return COLORS["green"]
    if any(token in text for token in ("confirmation", "action requested", "action completed", "paused")):
        return COLORS["yellow"]
    if any(token in text for token in ("speech", "tts", "voice")):
        return COLORS["magenta"]
    if text.startswith(('get /api', 'post /api', '"get /api', '"post /api')):
        return COLORS["dim"]
    return COLORS["cyan"]


def trace(message):
    line = f"[SARA] {message}"
    if colors_enabled():
        line = f"{color_for(line)}{line}{RESET}"
    print(line, flush=True)
