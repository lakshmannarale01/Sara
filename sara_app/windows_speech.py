"""Local Windows OneCore speech, including voices unavailable to browser TTS.

Input is JSON on stdin to a fixed script; text is never shell source or saved.
The returned WAV is played by the browser so animation follows playback events.
"""
import base64
import json
import math
import os
from pathlib import Path
import subprocess
from threading import Lock
import time

_lock = Lock()
_cached = None
_checked = 0.0
SCRIPT = Path(__file__).with_name("windows_voice.ps1")


def _request(data, timeout=35):
    if os.name != "nt":
        raise RuntimeError("Local Windows speech is available on Windows only.")
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run(
        [str(executable), "-NoProfile", "-NonInteractive", "-File", str(SCRIPT)],
        input=json.dumps(data, ensure_ascii=False), capture_output=True,
        encoding="utf-8", errors="replace", timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )
    if result.returncode:
        # Do not return script stderr: engines can echo text being synthesized.
        raise RuntimeError("Windows speech engine could not synthesize audio. Check installed voices and Windows speech settings.")
    try:
        payload = json.loads(result.stdout.lstrip("\ufeff"))
        if not isinstance(payload, dict): raise ValueError("Expected object")
        return payload
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Windows speech returned an invalid response.") from exc


def voice_status(force=False):
    global _cached, _checked
    with _lock:
        if not force and _cached is not None and time.monotonic() - _checked < 60:
            return _cached
        try:
            payload = _request({"operation": "voices"}, timeout=10)
            voices = [v for v in payload.get("voices", []) if isinstance(v, dict) and v.get("id") and v.get("name") and v.get("lang")]
            _cached = {"available": bool(voices), "voices": voices, "provider": "windows-local"}
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            _cached = {"available": False, "voices": [], "provider": "windows-local", "reason": "Windows speech is unavailable; browser system voices can still be used."}
        _checked = time.monotonic()
        return _cached


def synthesize(text, voice="", lang="", rate=1.0):
    if not isinstance(text, str) or not text.strip() or len(text) > 1200:
        raise ValueError("Speech text must contain 1–1200 characters.")
    if not isinstance(voice, str) or len(voice) > 1000 or not isinstance(lang, str) or lang not in {"", "hi-IN", "en-IN", "en-US", "en-GB"}:
        raise ValueError("Invalid Windows voice selection.")
    try:
        rate = float(rate)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid speaking speed.") from exc
    if not math.isfinite(rate) or not .85 <= rate <= 1.4:
        raise ValueError("Speaking speed must be between 0.85 and 1.4.")
    payload = _request({"operation": "synthesize", "text": text, "voice": voice, "lang": lang, "rate": rate})
    try:
        audio = base64.b64decode(payload["audio"], validate=True)
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("Windows speech returned invalid audio.") from exc
    if len(audio) < 44 or len(audio) > 24 * 1024 * 1024 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise RuntimeError("Windows speech returned invalid WAV audio.")
    return audio, str(payload.get("voice", "Windows voice")), str(payload.get("lang", lang))
