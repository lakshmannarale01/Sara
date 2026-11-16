"""Bounded Windows speaker/media controls; input is data, never shell source."""
import json
import os
from pathlib import Path
import re
import subprocess

from .policy import is_stopped
from .storage import log

COMMANDS = frozenset({"set_volume", "volume_up", "volume_down", "mute", "unmute", "play_pause", "next_track", "previous_track", "stop"})
TRANSPORT = frozenset({"play_pause", "next_track", "previous_track", "stop"})
SCRIPT = Path(__file__).with_name("system_audio.ps1")


def normalize_media_payload(payload):
    if not isinstance(payload, dict) or set(payload) - {"command", "level"}:
        raise ValueError("Media controls accept only command and an optional volume level.")
    command = payload.get("command")
    if not isinstance(command, str) or command not in COMMANDS:
        raise ValueError("Unsupported media control.")
    if command == "set_volume":
        level = payload.get("level")
        if type(level) is not int or not 0 <= level <= 100:
            raise ValueError("Volume must be a whole number from 0 to 100.")
        return {"command": command, "level": level}
    if "level" in payload:
        raise ValueError("A level is allowed only when setting volume.")
    return {"command": command}


def _request(payload):
    if os.name != "nt":
        raise RuntimeError("Windows audio controls are available on Windows only.")
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(executable), "-NoProfile", "-NonInteractive", "-File", str(SCRIPT)],
                            input=json.dumps(payload), capture_output=True, encoding="utf-8", errors="replace",
                            timeout=12, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError("Windows audio control failed. Check the default output device and its availability.")
    try:
        response = json.loads(result.stdout.lstrip("\ufeff"))
        if not isinstance(response, dict): raise ValueError("Expected an audio response object.")
        return response
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Windows audio returned an invalid response.") from exc


def _audio_state(response):
    volume = response.get("volume")
    if response.get("available") is not True or type(volume) is not int or not 0 <= volume <= 100 or type(response.get("muted")) is not bool:
        raise RuntimeError("Windows audio returned invalid volume or mute state.")
    return {"available": True, "volume": volume, "muted": response["muted"], "device": "default multimedia output"}


def read_audio_status():
    """Read output volume/mute without changing either, even while actions pause."""
    try:
        return _audio_state(_request({"command": "read"}))
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "volume": None, "muted": None, "error": str(exc) if isinstance(exc, RuntimeError) else "Windows audio status is unavailable."}


def execute_media_control(command, level=None, confirmed=False):
    payload = normalize_media_payload({"command": command, **({"level": level} if level is not None else {})})
    if is_stopped():
        return {"ok": False, "stopped": True, "result": "SARA actions are paused. No media control was sent."}
    if not confirmed:
        return {"requires_confirmation": True, "command": command, "result": "Review this Windows speaker/media control first."}
    # Recheck immediately before crossing the operating-system boundary.
    if is_stopped():
        return {"ok": False, "stopped": True, "result": "SARA actions were paused before the media control started."}
    response = _request(payload)
    if command in TRANSPORT:
        if response.get("key_sent") is not True:
            raise RuntimeError("Windows did not confirm the media-key dispatch.")
        labels = {"play_pause": "Play/Pause", "next_track": "Next track", "previous_track": "Previous track", "stop": "Stop media"}
        result = {"ok": True, "key_sent": True, "playback_verified": False,
                  "result": f"{labels[command]} media key sent to Windows. The active player's response has not been verified."}
    else:
        state = _audio_state(response)
        verified = response.get("readback_verified") is True
        if command == "set_volume": verified = verified and abs(state["volume"] - payload["level"]) <= 1
        elif command in {"mute", "unmute"}: verified = verified and state["muted"] == (command == "mute")
        result = {"ok": verified, **state, "readback_verified": verified, "changed": response.get("changed") is True,
                  "result": f"Windows output is {state['volume']}%, {'muted' if state['muted'] else 'unmuted'}. " + ("Readback verified." if verified else "The requested change was not verified; check the output device.")}
    log("system_media_control", {"command": command, "ok": result["ok"], **({"level": level} if level is not None else {})})
    return result


def plan_media_control(message):
    """Recognize direct controls, not instructions quoted inside ordinary prose."""
    if not isinstance(message, str): return None
    text = re.sub(r"\s+", " ", message.strip().casefold()).strip(" .!।")
    text = re.sub(r"^(?:(?:hey|hi)\s+)?(?:sara|सारा)[, ]*", "", text)
    text = re.sub(r"^(?:please\s+|can you\s+|could you\s+)", "", text)
    if not text or "?" in text or re.search(r"\b(?:how|why|what|explain|kaise|kyun|don't|do not|never|mat|nahi|nahin)\b|मत|नहीं|कैसे|क्यों", text):
        return None
    suffix = r"(?:\s+(?:karo|kar do|kardo|karna|do|kar|please|करो|कर\s+दो))?"
    command = None; level = None
    match = re.fullmatch(r"(?:(?:set|change)\s+)?(?:volume|speaker volume|sound|awaz|aawaz|awaaz|आवाज़|आवाज|वॉल्यूम)\s*(?:ko|to|at|को)?\s*(\d{1,3})\s*(?:%|percent|प्रतिशत)?" + suffix, text)
    if match:
        level = int(match.group(1))
        if level > 100: return None
        command = "set_volume"
    elif re.fullmatch(r"(?:unmute(?:\s+(?:audio|sound|volume|speakers?))?|(?:audio|sound|speaker|speakers|volume)\s+unmute|अनम्यूट)" + suffix, text): command = "unmute"
    elif re.fullmatch(r"(?:mute(?:\s+(?:audio|sound|volume|speakers?))?|(?:audio|sound|speaker|speakers|volume)\s+mute|म्यूट)" + suffix, text): command = "mute"
    elif re.fullmatch(r"(?:(?:volume|sound|awaz|aawaz|awaaz)\s+(?:up|badhao|badha do|tez)|(?:increase|raise|turn up)\s+(?:the\s+)?(?:volume|sound)|(?:आवाज़|आवाज|वॉल्यूम)\s+(?:बढ़ाओ|बढाओ|तेज़\s+करो))" + suffix, text): command = "volume_up"
    elif re.fullmatch(r"(?:(?:volume|sound|awaz|aawaz|awaaz)\s+(?:down|kam|kam karo|kam kar do)|(?:decrease|lower|turn down)\s+(?:the\s+)?(?:volume|sound)|(?:आवाज़|आवाज|वॉल्यूम)\s+(?:कम|धीमी\s+करो))" + suffix, text): command = "volume_down"
    elif re.fullmatch(r"(?:(?:song|music|media|gaana|gana|video)\s+(?:pause|resume|play pause)|(?:pause|resume)(?:\s+(?:song|music|media|gaana|gana|video))?|play[ /-]+pause|(?:गाना|संगीत)\s+(?:रुको|रोक दो|पॉज़|पॉज))" + suffix, text): command = "play_pause"
    elif re.fullmatch(r"(?:(?:next|agla)\s+(?:song|track|gaana|gana)|(?:song|track)\s+next|अगला\s+(?:गाना|ट्रैक))" + suffix, text): command = "next_track"
    elif re.fullmatch(r"(?:(?:previous|pichla)\s+(?:song|track|gaana|gana)|(?:song|track)\s+previous|पिछला\s+(?:गाना|ट्रैक))" + suffix, text): command = "previous_track"
    elif re.fullmatch(r"(?:stop\s+(?:song|music|media|gaana|gana)|(?:song|music|media|gaana|gana)\s+(?:stop|band)|(?:गाना|संगीत)\s+बंद)" + suffix, text): command = "stop"
    if command is None: return None
    payload = normalize_media_payload({"command": command, **({"level": level} if level is not None else {})})
    labels = {"set_volume": f"Set output volume to {level}%", "volume_up": "Raise output volume by 10 percentage points", "volume_down": "Lower output volume by 10 percentage points", "mute": "Mute output", "unmute": "Unmute output", "play_pause": "Send Play/Pause media key", "next_track": "Send Next track media key", "previous_track": "Send Previous track media key", "stop": "Send Stop media key"}
    return {"reply": labels[command] + " request तैयार है; actual result बताऊँगी।", "provider": "media-planner", "requires_confirmation": True,
            "action": {"type": "media_control", **payload, "label": labels[command]}}
