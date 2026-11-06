import json, webbrowser, mimetypes, os, re, urllib.request, threading, time, subprocess, shutil
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote, parse_qs
from urllib.parse import quote_plus
from .config import ROOT, PORT
from .storage import now, read_memories, write_memories, read_pronunciations, write_pronunciations, read_apps, write_apps, read_capability_requests, write_capability_requests, read_reminders, write_reminders, read_conversations, append_conversation, read_tasks, write_tasks, read_events, write_events, read_recent_activity, log, LOG_FILE, MEMORY_LOCK, TASK_LOCK, EVENT_LOCK, PRONUNCIATION_LOCK, APP_LOCK, CAPABILITY_REQUEST_LOCK
from .ai import ask, request_performance, performance_snapshot, warmup_ollama
from .speech import prepare_speech
from .tools import open_url, open_browser_url, open_whatsapp_draft, open_app, open_email_draft
from .desktop import type_text, press_hotkey, click_point
from .browser_control import open_page as semantic_open_page, click_text as semantic_click_text, fill_text as semantic_fill_text, whatsapp_send, shutdown_browser
from .capabilities import capability_snapshot
from .policy import inspect_action, is_stopped, set_stopped
from .console import trace as console_trace
from . import action_state
from .intents import short_confirmation, is_action_status_question, is_capability_overview_question, memory_request_text, plan_notepad, unhandled_operation, capability_request, action_payload
from .notes import create_notepad_note, read_note
from .reminder_delivery import deliver_due_reminders, reminder_file_lock

_health_cache = {"checked_at": 0.0, "ollama": False}
_health_lock = threading.Lock()

def ollama_health():
    """Share a short cached probe across dashboard/status requests."""
    age = time.monotonic() - _health_cache["checked_at"]
    if age < (10 if _health_cache["ollama"] else 3):
        return _health_cache["ollama"]
    with _health_lock:
        age = time.monotonic() - _health_cache["checked_at"]
        if age >= (10 if _health_cache["ollama"] else 3):
            try:
                request = urllib.request.Request(os.getenv("SARA_OLLAMA_URL", "http://127.0.0.1:11434") + "/api/tags")
                with urllib.request.urlopen(request, timeout=1) as response:
                    _health_cache["ollama"] = response.status == 200
            except Exception:
                _health_cache["ollama"] = False
            _health_cache["checked_at"] = time.monotonic()
    return _health_cache["ollama"]

def reminder_watcher():
    while True:
        try:
            deliver_due_reminders()
        except Exception as exc: log("reminder_watcher_error", {"error": str(exc)})
        time.sleep(5)

def weather_report(location=""):
    target = quote_plus(location.strip() or "auto")
    request = urllib.request.Request(f"https://wttr.in/{target}?format=j1", headers={"User-Agent": "SARA/1.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode())
    current = data["current_condition"][0]
    area = data.get("nearest_area", [{}])[0]
    place = area.get("areaName", [{"value": location or "your area"}])[0]["value"]
    condition = current.get("weatherDesc", [{"value": "unknown conditions"}])[0]["value"]
    return f"Boss, {place} mein abhi {current['temp_C']}°C hai, feels like {current['FeelsLikeC']}°C, {condition.lower()}, humidity {current['humidity']}%."

def system_summary():
    ollama_ready = ollama_health()
    try:
        import pyautogui
        width, height = pyautogui.size(); desktop_ready = True
    except Exception:
        width = height = None; desktop_ready = False
    try:
        import playwright  # noqa: F401
        browser_ready = True
    except ImportError:
        browser_ready = False
    reminders = read_reminders()
    pending = sum(1 for item in reminders if item.get("status") == "pending")
    pending_tasks = sum(1 for item in read_tasks() if item.get("status") == "pending")
    upcoming_events = sum(1 for item in read_events() if item.get("status", "planned") == "planned")
    return {"ollama": ollama_ready, "model": os.getenv("SARA_OLLAMA_MODEL", "llama3.2"), "desktop": desktop_ready, "screen": {"width": width, "height": height} if desktop_ready else None, "browser": browser_ready, "approved_memories": len(read_memories()), "pending_reminders": pending, "pending_tasks": pending_tasks, "upcoming_events": upcoming_events}

def agenda_snapshot():
    tasks = [item for item in read_tasks() if item.get("status") == "pending"]
    reminders = [item for item in read_reminders() if item.get("status") == "pending"]
    events = sorted([item for item in read_events() if item.get("status", "planned") == "planned"], key=lambda item: item.get("start_at", ""))
    return {"tasks": tasks, "reminders": reminders, "events": events}

def format_event_time(item):
    try:
        return datetime.fromisoformat(item.get("start_at", "").replace("Z", "+00:00")).astimezone().strftime("%d %b, %I:%M %p")
    except (TypeError, ValueError):
        return "scheduled"

def agenda_reply(title="local agenda"):
    agenda = agenda_snapshot(); lines = [f"Boss, aapka {title}:"]
    lines += [f"Tasks: {item.get('text', '')}" for item in agenda["tasks"][:8]] or ["Tasks: koi pending task nahi hai."]
    lines += [f"Reminders: {item.get('text', '')}" for item in agenda["reminders"][:8]] or ["Reminders: koi pending reminder nahi hai."]
    lines += [f"Events: {item.get('title', 'Untitled')} — {format_event_time(item)}" for item in agenda["events"][:8]] or ["Events: koi planned event nahi hai."]
    return "\n".join(lines), agenda

def ics_escape(value):
    return str(value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")

def calendar_ics():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rows = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SARA//Local Calendar//EN", "CALSCALE:GREGORIAN"]
    for item in agenda_snapshot()["events"]:
        try:
            start = datetime.fromisoformat(item.get("start_at", "").replace("Z", "+00:00")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        end = start + timedelta(hours=1)
        rows.extend(["BEGIN:VEVENT", f"UID:{ics_escape(item.get('id'))}@sara.local", f"DTSTAMP:{stamp}", f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}", f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}", f"SUMMARY:{ics_escape(item.get('title', 'SARA event'))}", "END:VEVENT"])
    rows.append("END:VCALENDAR")
    return "\r\n".join(rows) + "\r\n"

def browser_executable(browser):
    """Find a supported Windows browser even when it is not on PATH."""
    names = {
        "edge": ["msedge.exe", "msedge"],
        "msedge": ["msedge.exe", "msedge"],
        "chrome": ["chrome.exe", "chrome"],
    }.get(browser, [])
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    local_app_data = os.getenv("LOCALAPPDATA", "")
    program_files = os.getenv("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)")
    candidates = []
    if browser in {"edge", "msedge"}:
        candidates = [
            os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(local_app_data, "Microsoft", "Edge", "Application", "msedge.exe"),
        ]
    elif browser == "chrome":
        candidates = [
            os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"),
        ]
    return next((candidate for candidate in candidates if os.path.isfile(candidate)), None)


def open_dashboard():
    """Open SARA as a standalone app window, with a browser tab fallback."""
    url = f"http://127.0.0.1:{PORT}"
    browser = os.getenv("SARA_UI_BROWSER", "edge").strip().lower()
    mode = os.getenv("SARA_UI_MODE", "app").strip().lower()
    if browser in {"0", "off", "none", "false"}:
        console_trace(f"Dashboard URL: {url}")
        return
    executable = browser_executable(browser)
    if executable:
        try:
            if mode in {"app", "standalone", "desktop"}:
                args = [executable, f"--app={url}", "--start-maximized"]
                launch_description = f"standalone {browser.title()} app window"
            else:
                args = [executable, "--new-window", url]
                launch_description = f"separate {browser.title()} window"
            subprocess.Popen(args, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            console_trace(f"Dashboard opened as a {launch_description}.")
            return
        except OSError as exc:
            console_trace(f"{browser.title()} launch failed: {exc}")
    if browser in {"edge", "msedge"}:
        console_trace("Microsoft Edge was not found. SARA will not open Chrome automatically.")
        console_trace(f"Dashboard URL: {url}")
        return
    try:
        webbrowser.open_new_tab(url)
        console_trace(f"Dashboard opened with the system browser ({browser}); app mode was unavailable.")
    except Exception as exc:
        console_trace(f"Open {url} manually. Browser launch failed: {exc}")

_WORKSPACE_EXCLUDED_DIRS = {".git", ".venv", "sara_data", "__pycache__", "node_modules", ".aws", ".ssh", ".azure", ".kube"}
_WORKSPACE_SECRET_NAMES = {"credentials.json", "secrets.json", "id_rsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc"}
_WORKSPACE_SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx", ".asc"}
_WORKSPACE_TEXT_SUFFIXES = {".md", ".txt", ".py", ".json", ".html", ".css", ".js", ".bat", ".ps1", ".yml", ".yaml", ".toml", ".ini", ".csv", ".xml", ".sql"}


def _workspace_path_is_private(relative):
    parts = [part.casefold() for part in str(relative).replace("\\", "/").split("/")]
    filename = parts[-1] if parts else ""
    return (
        bool(_WORKSPACE_EXCLUDED_DIRS & set(parts))
        or filename.startswith(".env")
        or filename in _WORKSPACE_SECRET_NAMES
        or (any(marker in filename for marker in ("secret", "credential")) and os.path.splitext(filename)[1] in {".json", ".yaml", ".yml", ".toml", ".ini", ".txt"})
        or os.path.splitext(filename)[1] in _WORKSPACE_SECRET_SUFFIXES
    )


def workspace_files():
    items = []
    for directory, folders, files in os.walk(ROOT):
        folders[:] = [name for name in folders if name.casefold() not in _WORKSPACE_EXCLUDED_DIRS]
        for name in files:
            relative = os.path.relpath(os.path.join(directory, name), ROOT)
            if not _workspace_path_is_private(relative): items.append(relative)
    return items

def workspace_target(relative):
    """Resolve a workspace path while excluding secrets and runtime state."""
    supplied = str(relative)
    target = (ROOT / supplied).resolve()
    resolved_relative = os.path.relpath(target, ROOT)
    if ROOT not in target.parents or not supplied.strip() or _workspace_path_is_private(resolved_relative):
        return None
    return target

def read_workspace_text(relative):
    target = workspace_target(relative)
    if target is None or not target.is_file():
        return None, "That file is outside SARA's readable workspace scope."
    try:
        with target.open("rb") as source: raw = source.read(100_001)
        if len(raw) > 100_000: return None, "That file is too large to read in chat."
        return raw.decode("utf-8"), None
    except (OSError, UnicodeDecodeError): return None, "That file is not a readable text file."


def search_workspace_text(query, limit=8):
    """Search only bounded, readable text files inside SARA's safe workspace."""
    query = str(query or "").strip()
    terms = list(dict.fromkeys(re.findall(r"[\w-]+", query.casefold(), re.UNICODE)))
    if not terms or len(query) > 200:
        return []
    patterns = [re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.I | re.UNICODE) for term in terms]
    results = []
    scanned_bytes = 0
    for relative in workspace_files()[:1500]:
        if os.path.splitext(relative)[1].casefold() not in _WORKSPACE_TEXT_SUFFIXES:
            continue
        target = workspace_target(relative)
        if target is None:
            continue
        try:
            size = target.stat().st_size
            if size > 100_000 or scanned_bytes + size > 20_000_000:
                continue
            with target.open("rb") as source: raw = source.read(100_001)
            if len(raw) > 100_000: continue
            content = raw.decode("utf-8")
            scanned_bytes += len(raw)
        except (OSError, UnicodeError):
            continue
        lowered = content.casefold()
        counts = [len(pattern.findall(lowered)) for pattern in patterns]
        score = sum(counts)
        if not score:
            continue
        snippets = []
        for line_number, line in enumerate(content.splitlines(), 1):
            if any(pattern.search(line) for pattern in patterns):
                excerpt = line.strip()
                if len(excerpt) > 220: excerpt = excerpt[:217] + "..."
                snippets.append({"line": line_number, "text": excerpt})
                if len(snippets) >= 3: break
        results.append({"path": relative, "score": score, "matches": sum(count > 0 for count in counts), "snippets": snippets})
    results.sort(key=lambda item: (item["matches"], item["score"]), reverse=True)
    return results[:max(1, min(12, int(limit)))]

def parse_due_at(message):
    match = re.search(r"in\s+(\d+)\s+(minute|minutes|hour|hours)", message, re.I)
    if match:
        amount = int(match.group(1)); amount *= 60 if match.group(2).lower().startswith("minute") else 3600
        return (datetime.now(timezone.utc) + timedelta(seconds=amount)).isoformat()
    match = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", message, re.I)
    if match:
        hour = int(match.group(1)); minute = int(match.group(2) or 0); meridiem = (match.group(3) or "").lower()
        if meridiem == "pm" and hour < 12: hour += 12
        if meridiem == "am" and hour == 12: hour = 0
        current = datetime.now().astimezone(); due = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= current: due += timedelta(days=1)
        return due.astimezone(timezone.utc).isoformat()
    return None

def parse_event_start(message):
    """Parse a simple local event time from natural language into UTC ISO."""
    text = str(message)
    match = re.search(r"(?:on\s+)?(today|tomorrow|kal)?\s*(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text, re.I)
    if not match: return None
    hour = int(match.group(2)); minute = int(match.group(3) or 0); meridiem = (match.group(4) or "").lower()
    if meridiem == "pm" and hour < 12: hour += 12
    if meridiem == "am" and hour == 12: hour = 0
    if hour > 23 or minute > 59: return None
    local = datetime.now().astimezone()
    day_word = (match.group(1) or "today").lower()
    if day_word in {"tomorrow", "kal"}: local += timedelta(days=1)
    local = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if day_word == "today" and local <= datetime.now().astimezone(): local += timedelta(days=1)
    return local.astimezone(timezone.utc).isoformat()

def event_title(message):
    match = re.match(r"(?:add|create|new|plan)\s+(?:an?\s+)?(?:event|meeting)\s+(.+)$|schedule\s+(?:(?:an?\s+)?(?:event|meeting)\s+)?(.+)$", message, re.I)
    if not match: return None
    title = next((group for group in match.groups() if group), "")
    title = re.sub(r"\s+(?:on\s+)?(?:today|tomorrow|kal)?\s*(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*$", "", title, flags=re.I).strip(" ,.-")
    return title or None
class Handler(BaseHTTPRequestHandler):
    def trace(self, message): console_trace(message)
    def stream_event(self, event):
        if not getattr(self, "chat_streaming", False):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.chat_streaming = True
            self.close_connection = True
        self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode())
        self.wfile.flush()
    def send_json(self, status, data):
        session = getattr(self, "session_id", None)
        executing = getattr(self, "executing_proposal", None)
        if executing and isinstance(data, dict):
            self.executing_proposal = None
            succeeded = status < 400 and data.get("ok") is not False and not data.get("error") and not data.get("requires_confirmation")
            outcome = action_state.finish(session, executing, "completed" if succeeded else "failed", data)
            data["action_result"] = {"proposal_id": executing, "type": outcome["action"]["type"], "status": outcome["status"]}
            result_text = data.get("result") if isinstance(data.get("result"), str) else data.get("error") or ("Action completed." if succeeded else "Action failed; its result needs review.")
            append_conversation({"time": now(), "question": "[Approved action] " + outcome["action"]["type"], "answer": result_text, "provider": "tool-result", "action_result": data["action_result"]})
            log("action_result", {**data["action_result"], "result": result_text})
        if urlparse(self.path).path == "/api/chat" and isinstance(data, dict) and data.get("reply"):
            if session and data.get("requires_confirmation") and data.get("action"):
                proposal = action_state.propose(session, data["action"])
                data["action"] = {**proposal["action"], "proposal_id": proposal["id"]}
                data["proposal_id"] = proposal["id"]
                data["action_status"] = proposal["status"]
            data["timing"] = {**getattr(self, "ai_timing", {}), "total_ms": round((time.perf_counter() - getattr(self, "chat_started", time.perf_counter())) * 1000)}
            question = getattr(self, "chat_message", "")
            answer = str(data["reply"])[:4000]
            provider = data.get("provider", "unknown")
            append_conversation({"time": now(), "question": question, "answer": answer, "provider": provider})
            log("conversation", {"question": question, "answer": answer, "provider": provider})
            self.trace(f"Boss: {question}")
            self.trace(f"SARA ({provider}): {answer.replace(chr(10), ' ')}")
            self.trace(f"Reply ready: {data['timing']['total_ms']} ms")
        if getattr(self, "chat_streaming", False):
            return self.stream_event({"type": "done" if status < 400 else "error", **data})
        body = json.dumps(data, ensure_ascii=False).encode()
        try:
            self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.trace("Client disconnected before SARA could deliver the response")
    def body(self):
        size = int(self.headers.get("Content-Length", "0")); return json.loads(self.rfile.read(size) or b"{}")
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/action-state":
            session = parse_qs(urlparse(self.path).query).get("session_id", [""])[0]
            if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", session): return self.send_json(400, {"error": "A dashboard session is required."})
            return self.send_json(200, {**action_state.context(session), "pending": action_state.pending(session)})
        if path.startswith("/api/notes/"):
            try: text = read_note(path.rsplit("/", 1)[-1])
            except ValueError: return self.send_json(400, {"error": "Invalid note ID"})
            except (OSError, UnicodeError): return self.send_json(404, {"error": "Saved note not found"})
            body = text.encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/plain; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if path.startswith("/assets/"):
            asset = (ROOT / path.lstrip("/")).resolve()
            assets_root = (ROOT / "assets").resolve()
            if asset.is_file() and assets_root in asset.parents:
                body = asset.read_bytes(); self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(str(asset))[0] or "application/octet-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            return self.send_json(404, {"error": "Asset not found"})
        if path == "/api/memories": return self.send_json(200, read_memories())
        if path == "/api/pronunciations": return self.send_json(200, read_pronunciations())
        if path == "/api/apps": return self.send_json(200, {"built_in": ["Chrome", "Notepad", "Calculator"], "custom": read_apps()})
        if path == "/api/capability-requests": return self.send_json(200, read_capability_requests())
        if path == "/api/reminders": return self.send_json(200, read_reminders())
        if path == "/api/events":
            events = [item for item in read_events() if item.get("status", "planned") == "planned"]
            return self.send_json(200, sorted(events, key=lambda item: item.get("start_at", "")))
        if path == "/api/agenda":
            agenda = agenda_snapshot()
            return self.send_json(200, agenda)
        if path == "/api/calendar.ics":
            body = calendar_ics().encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/calendar; charset=utf-8"); self.send_header("Content-Disposition", "attachment; filename=sara-calendar.ics"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if path == "/api/files":
            return self.send_json(200, {"files": workspace_files()})
        if path == "/api/files/read":
            relative = self.headers.get("X-SARA-Path", "")
            content, error = read_workspace_text(relative)
            if error: return self.send_json(400, {"error": error})
            return self.send_json(200, {"path": relative, "content": content})
        if path == "/api/status": return self.send_json(200, {"name": "SARA", "mode": "Ollama/OpenAI/local-safe", "port": PORT})
        if path == "/api/health":
            ollama_ok = ollama_health()
            return self.send_json(200, {"ok": True, "ollama": ollama_ok, "model": os.getenv("SARA_OLLAMA_MODEL", "llama3.2"), "natural_voice": bool(os.getenv("OPENAI_API_KEY"))})
        if path == "/api/performance": return self.send_json(200, performance_snapshot())
        if path == "/api/capabilities": return self.send_json(200, capability_snapshot())
        if path == "/api/policy":
            return self.send_json(200, {"stopped": is_stopped(), "actions": {name: inspect_action(name) for name in ("create_reminder", "delete_reminder", "create_task", "complete_task", "delete_task", "create_event", "delete_event", "save_memory", "delete_memory", "save_pronunciation", "delete_pronunciation", "add_custom_app", "delete_custom_app", "save_capability_request", "delete_capability_request", "write_file", "delete_file", "open_app", "open_browser_url", "browser_click_text", "browser_fill", "type_text", "hotkey", "click_point", "email_draft", "whatsapp_send")}})
        if path == "/api/desktop/status":
            try:
                import pyautogui
                width, height = pyautogui.size()
                return self.send_json(200, {"available": True, "screen": {"width": width, "height": height}, "note": "No screenshot is captured by this endpoint."})
            except Exception as exc:
                return self.send_json(200, {"available": False, "error": str(exc)})
        if path == "/api/browser/status":
            try:
                import playwright
                return self.send_json(200, {"available": True, "provider": "playwright", "profile": "sara_data/browser_profile"})
            except ImportError:
                return self.send_json(200, {"available": False, "error": "Playwright is not installed"})
        if path == "/api/activity":
            return self.send_json(200, read_recent_activity())
        if path == "/api/conversations":
            try:
                items = read_conversations()
                if not items:
                    items = list(reversed([item for item in read_recent_activity(500) if item.get("event") == "conversation"]))
                return self.send_json(200, items[-30:])
            except (OSError, json.JSONDecodeError): return self.send_json(200, [])
        if path == "/api/suggestions":
            agenda = agenda_snapshot(); tasks, reminders, events = agenda["tasks"], agenda["reminders"], agenda["events"]
            suggestions = []
            if tasks: suggestions.append({"type": "task", "text": f"Aapke paas {len(tasks)} pending task hai. Sabse pehle: {tasks[0].get('text', '')}"})
            if reminders: suggestions.append({"type": "reminder", "text": f"Aapka next reminder: {reminders[0].get('text', '')}"})
            if events:
                when = format_event_time(events[0])
                suggestions.append({"type": "event", "text": f"Next event: {events[0].get('title', 'Untitled')} ({when})"})
            if not suggestions: suggestions.append({"type": "status", "text": "Abhi koi urgent local task ya reminder nahi hai."})
            return self.send_json(200, {"suggestions": suggestions})
        if path in {"/", "/index.html"}:
            body = (ROOT / "index.html").read_bytes(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        self.send_json(404, {"error": "Not found"})
    def do_POST(self):
        # Item IDs contain ISO timestamp colons and plus signs, encoded by the UI.
        path = unquote(urlparse(self.path).path)
        self.chat_started = time.perf_counter()
        try:
            data = self.body()
            session = data.get("session_id")
            if session is not None and not (isinstance(session, str) and re.fullmatch(r"[A-Za-z0-9_-]{8,80}", session)):
                return self.send_json(400, {"error": "Invalid dashboard session."})
            self.session_id = session
            if path == "/api/actions/cancel":
                if not session: return self.send_json(400, {"error": "A dashboard session is required."})
                cancelled = action_state.cancel(session, data.get("proposal_id"))
                return self.send_json(200, {"ok": True, "cancelled": bool(cancelled)})
            if path == "/api/policy/stop":
                set_stopped(True); log("sara_stopped", {"source": "dashboard"})
                return self.send_json(200, {"stopped": True})
            if path == "/api/policy/resume":
                set_stopped(False); log("sara_resumed", {"source": "dashboard"})
                return self.send_json(200, {"stopped": False})
            action_by_path = {
                "/api/memories": "save_memory", "/api/pronunciations": "save_pronunciation", "/api/apps": "add_custom_app", "/api/capability-requests": "save_capability_request", "/api/reminders": "create_reminder", "/api/tasks": "create_task", "/api/events": "create_event",
                "/api/files/write": "write_file", "/api/files/delete": "delete_file",
                "/api/actions/open-browser-url": "open_browser_url", "/api/actions/whatsapp-draft": "whatsapp_draft",
                "/api/actions/open-app": "open_app", "/api/actions/email-draft": "email_draft",
                "/api/actions/type-text": "type_text", "/api/actions/hotkey": "hotkey", "/api/actions/click-point": "click_point",
                "/api/actions/notepad-write": "notepad_write",
                "/api/actions/browser-open": "browser_open", "/api/actions/browser-click-text": "browser_click_text",
                "/api/actions/browser-fill": "browser_fill", "/api/actions/whatsapp-send": "whatsapp_send",
                "/api/tools/open-url": "open_browser_url",
            }
            route_action = action_by_path.get(path)
            if not route_action and path.startswith("/api/memories/") and path.endswith("/delete"): route_action = "delete_memory"
            if not route_action and path.startswith("/api/pronunciations/") and path.endswith("/delete"): route_action = "delete_pronunciation"
            if not route_action and path.startswith("/api/apps/") and path.endswith("/delete"): route_action = "delete_custom_app"
            if not route_action and path.startswith("/api/capability-requests/") and path.endswith("/delete"): route_action = "delete_capability_request"
            if not route_action and path.startswith("/api/reminders/") and path.endswith("/delete"): route_action = "delete_reminder"
            if not route_action and path.startswith("/api/tasks/") and path.endswith("/complete"): route_action = "complete_task"
            if not route_action and path.startswith("/api/tasks/") and path.endswith("/delete"): route_action = "delete_task"
            if not route_action and path.startswith("/api/events/") and path.endswith("/delete"): route_action = "delete_event"
            if route_action:
                verdict = inspect_action(route_action, data.get("confirmed") is True)
                if not verdict["allowed"]: return self.send_json(409, {**verdict, "request": data})
                if session:
                    proposal_id = data.get("proposal_id")
                    if proposal_id:
                        proposal = action_state.get(session, proposal_id)
                        if not proposal or proposal["action"].get("type") != route_action:
                            return self.send_json(409, {"error": "This action does not match the pending proposal in this dashboard."})
                        expected = action_payload(proposal["action"])
                        actual = {key: value for key, value in data.items() if key not in {"session_id", "proposal_id", "confirmed"}}
                        if expected != actual:
                            return self.send_json(409, {"error": "Action details changed after review. Request and review the action again."})
                        if proposal["action"].get("id") and proposal["action"]["id"] != unquote(path).split("/")[-2]:
                            return self.send_json(409, {"error": "Selected item changed after review."})
                    else:
                        reviewed = {key: value for key, value in data.items() if key not in {"session_id", "confirmed", "proposal_id", "type"}}
                        if route_action in {"delete_memory", "delete_pronunciation", "delete_custom_app", "delete_capability_request", "delete_reminder", "delete_task", "complete_task", "delete_event"}: reviewed["id"] = path.split("/")[-2]
                        proposal = action_state.propose(session, {**reviewed, "type": route_action})
                        proposal_id = proposal["id"]
                    try: action_state.begin(session, proposal_id)
                    except ValueError as exc: return self.send_json(409, {"error": str(exc)})
                    self.executing_proposal = proposal_id
            if path == "/api/speech-text":
                text = str(data.get("text", "")).strip()
                if not text: return self.send_json(400, {"error": "Text is required"})
                prepared = prepare_speech(text[:1200])
                spoken_text = prepared["text"]
                devanagari = any("\u0900" <= char <= "\u097f" for char in spoken_text)
                self.trace(f"Speech text prepared: devanagari={devanagari}")
                log("speech_text_prepared", {"devanagari": devanagari, "input_chars": len(text)})
                return self.send_json(200, {**prepared, "devanagari": devanagari})
            if path == "/api/tts":
                text = prepare_speech(str(data.get("text", "")).strip()[:1200])["text"]
                key = os.getenv("OPENAI_API_KEY")
                self.trace(f"TTS request: {len(text)} chars; API key={'present' if key else 'missing'}")
                if not key or not text: return self.send_json(400, {"error": "OpenAI TTS is not configured"})
                from openai import OpenAI
                try: speed = min(1.4, max(0.85, float(data.get("speed", 1.12))))
                except (TypeError, ValueError): speed = 1.12
                audio = OpenAI(api_key=key, timeout=40).audio.speech.create(
                    model="gpt-4o-mini-tts", voice="coral", input=text, speed=speed,
                    instructions="Speak as SARA, a warm feminine AI companion. Sound natural and conversational, at a lively normal pace. Pronounce Hindi and Hinglish clearly, keep English terms natural, and avoid a robotic or theatrical delivery.",
                )
                body = getattr(audio, "content", None) or audio.read()
                self.trace(f"TTS success: {len(body)} bytes")
                self.send_response(200); self.send_header("Content-Type", "audio/mpeg"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            if path == "/api/chat":
                message = str(data.get("message", "")).strip()
                if not message: return self.send_json(400, {"error": "Message is required"})
                self.chat_message = message
                lower = message.lower()
                confirmation = short_confirmation(message)
                if confirmation:
                    pending = action_state.pending(session) if session else None
                    if confirmation == "cancel":
                        if session: action_state.cancel(session)
                        return self.send_json(200, {"reply": "Pending action cancel kar diya; execute nahi hua." if pending else "Koi pending action nahi hai.", "provider": "action-state", "pending_cancelled": bool(pending)})
                    if pending:
                        return self.send_json(200, {"reply": "Wahi pending action ka review khol rahi hoon. Exact details check karke Approve karein; abhi execute nahi hua.", "provider": "action-state", "requires_confirmation": True, "review_pending": True, "action": {**pending["action"], "proposal_id": pending["id"]}})
                    return self.send_json(200, {"reply": "Is dashboard mein koi pending action nahi hai. Batayein kaunsa app ya action chahiye; maine abhi kuch execute nahi kiya.", "provider": "action-state"})
                if is_action_status_question(message):
                    evidence = action_state.context(session) if session else {"pending": None, "recent_outcomes": []}
                    outcomes = evidence["recent_outcomes"]
                    if evidence["pending"]:
                        return self.send_json(200, {"reply": "Action abhi pending approval hai; execute nahi hua. Review action se exact details approve karein.", "provider": "action-state", "requires_confirmation": True, "action": {**action_state.pending(session)["action"], "proposal_id": evidence["pending"]["id"]}})
                    last = outcomes[-1] if outcomes else None
                    result = (last or {}).get("result", {})
                    detail = result.get("result") if isinstance(result, dict) else None
                    return self.send_json(200, {"reply": ("Last action: " + str(last["status"]) + ". " + str(detail or "No successful tool result was recorded.")) if last else "Is session mein koi executed action result nahi hai. Pehle ke AI chat claims execution ka proof nahi hain.", "provider": "action-state"})
                capability_gap = capability_request(message)
                if capability_gap:
                    registry_item = capability_snapshot().get(capability_gap["key"], {})
                    status = registry_item.get("status", "planned")
                    status_text = "partial hai" if status == "partial" else ("planned hai" if status == "planned" else "available hai")
                    if status == "available" and capability_gap["key"] == "custom_app_shortcuts":
                        reply = "Boss, custom app shortcuts ab available hain. Settings → App shortcuts mein naam aur full `.exe` path save karein; phir chat mein `open <naam>` ya `<naam> kholo` bolkar launch request dein. Har launch se pehle approval zaroori hai."
                        return self.send_json(200, {"reply": reply, "provider": "capability-planner", "capability": capability_gap["key"], "status": status})
                    steps = "\n".join(f"{index}. {step}" for index, step in enumerate(capability_gap["steps"], 1))
                    reply = (f"Boss, {capability_gap['title']} abhi SARA mein {status_text}; main isse bina aapki approval ke execute nahi karungi.\n"
                             f"Required access: {capability_gap['access']}.\n\nImplementation plan:\n{steps}\n\n"
                             "Kya main ise SARA ke local feature-request list mein save karoon? Approval se request track hogi; feature khud install ya enable nahi hoga.")
                    return self.send_json(200, {"reply": reply, "provider": "capability-planner", "capability": capability_gap["key"], "status": status, "implementation_plan": capability_gap["steps"], "required_access": capability_gap["access"], "requires_confirmation": True, "action": {"type": "save_capability_request", "title": capability_gap["title"], "description": message, "label": "Save this local feature request"}})
                if is_capability_overview_question(message):
                    registry = capability_snapshot()
                    def label(name): return name.replace("_", " ").title().replace("Api", "API").replace("Ui", "UI")
                    available = [label(name) for name, item in registry.items() if item["status"] == "available"]
                    partial = [(label(name), item.get("scope", "limited access")) for name, item in registry.items() if item["status"] == "partial"]
                    planned = [label(name) for name, item in registry.items() if item["status"] == "planned"]
                    ready_text = ", ".join(available[:10]) + (f", and {len(available) - 10} more in Settings" if len(available) > 10 else "")
                    partial_text = "; ".join(f"{name}: {scope}" for name, scope in partial[:5]) or "None"
                    planned_text = ", ".join(planned[:6]) + (f", and {len(planned) - 6} more in Settings" if len(planned) > 6 else "") or "None"
                    reply = (f"Abhi available: {ready_text}.\n\nLimited: {partial_text}.\n\n"
                             f"Not set up yet: {planned_text}. Settings → What SARA can do mein full current list hai."
                             " Agar koi missing feature chahiye, uska naam batao; main access aur implementation plan bata sakti hoon.")
                    return self.send_json(200, {"reply": reply, "provider": "capability-overview", "capabilities": registry})
                notepad = plan_notepad(message, read_memories())
                if notepad: return self.send_json(200, notepad)
                if re.search(r"(?:system|sara|environment)\s*(?:ka\s*)?(?:status|health|readiness)|status batao|how are you running", lower):
                    summary = system_summary()
                    reply = (f"Boss, SARA status: Ollama {'ready' if summary['ollama'] else 'offline'} ({summary['model']}), "
                             f"desktop control {'ready' if summary['desktop'] else 'unavailable'}, browser {'ready' if summary['browser'] else 'unavailable'}, "
                             f"{summary['approved_memories']} approved memories, {summary['pending_tasks']} pending tasks, {summary['pending_reminders']} pending reminders and {summary['upcoming_events']} planned events.")
                    return self.send_json(200, {"reply": reply, "provider": "system-status", "status": summary})
                if re.search(r"(?:show|list|dikhao|batao).*(?:memory|memories)|(?:memory|memories).*(?:show|list|dikhao|batao)|what do you remember|tumhe kya yaad", lower):
                    memories = read_memories()
                    if not memories:
                        return self.send_json(200, {"reply": "Boss, abhi koi approved memory save nahi hai.", "provider": "memory-list", "memories": []})
                    reply = "Boss, meri approved memories:\n" + "\n".join(f"{index}. {item.get('text', '')}" for index, item in enumerate(memories, 1))
                    return self.send_json(200, {"reply": reply, "provider": "memory-list", "memories": memories})
                pronunciation_match = re.match(r"(?:pronounce|say|speak)\s+['\"]?(.+?)['\"]?\s+(?:as|like)\s+['\"]?(.+?)['\"]?[.!?]*$", message, re.I)
                if pronunciation_match:
                    word, say_as = pronunciation_match.group(1).strip(), pronunciation_match.group(2).strip()
                    return self.send_json(200, {"reply": f"Boss, should I remember how to pronounce {word} in spoken replies?", "provider": "pronunciation-planner", "requires_confirmation": True, "action": {"type": "save_pronunciation", "word": word, "say_as": say_as, "label": f"say {word} as {say_as}"}})
                memory_delete = re.search(r"(?:forget|delete|remove|bhool jao|hatao)\s+(?:memory|yaad)\s+(\d+)", lower)
                if memory_delete:
                    memories = read_memories(); index = int(memory_delete.group(1)) - 1
                    if index < 0 or index >= len(memories):
                        return self.send_json(200, {"reply": "Boss, us number ki approved memory nahi mili.", "provider": "memory-list"})
                    item = memories[index]
                    return self.send_json(200, {"reply": f"Boss, kya main ye approved memory delete kar doon: {item.get('text', '')}?", "provider": "memory-planner", "requires_confirmation": True, "action": {"type": "delete_memory", "id": item.get("id"), "label": f"delete memory: {item.get('text', '')[:80]}"}})
                if re.search(r"(?:show|list|dikhao|batao).*(?:calendar|events?|meetings?)|(?:calendar|events?|meetings?).*(?:show|list|dikhao|batao)|aaj ke events?", lower):
                    events = [item for item in read_events() if item.get("status", "planned") == "planned"]
                    if not events:
                        return self.send_json(200, {"reply": "Boss, local calendar mein abhi koi planned event nahi hai.", "provider": "calendar-list", "events": []})
                    lines = []
                    for index, item in enumerate(sorted(events, key=lambda entry: entry.get("start_at", "")), 1):
                        try:
                            when = datetime.fromisoformat(item.get("start_at", "").replace("Z", "+00:00")).astimezone().strftime("%d %b, %I:%M %p")
                        except (TypeError, ValueError):
                            when = item.get("start_at", "unscheduled")
                        lines.append(f"{index}. {item.get('title', 'Untitled')} — {when}")
                    return self.send_json(200, {"reply": "Boss, aapke planned events:\n" + "\n".join(lines), "provider": "calendar-list", "events": events})
                event_cancel = re.search(r"(?:cancel|delete|remove|hatao)\s+(?:event|meeting)\s+(\d+)", lower)
                if event_cancel:
                    events = sorted([item for item in read_events() if item.get("status", "planned") == "planned"], key=lambda entry: entry.get("start_at", ""))
                    index = int(event_cancel.group(1)) - 1
                    if index < 0 or index >= len(events):
                        return self.send_json(200, {"reply": "Boss, us number ka planned event nahi mila.", "provider": "calendar-list"})
                    item = events[index]
                    return self.send_json(200, {"reply": f"Boss, kya main '{item.get('title', 'Untitled')}' ko cancel kar doon?", "provider": "calendar-planner", "requires_confirmation": True, "action": {"type": "delete_event", "id": item.get("id"), "label": f"cancel event: {item.get('title', '')[:80]}"}})
                event_text = event_title(message)
                if event_text and parse_event_start(message):
                    start_at = parse_event_start(message)
                    event = {"id": now(), "title": event_text, "start_at": start_at, "created": now(), "status": "planned"}
                    return self.send_json(200, {"reply": f"Boss, kya main '{event_text}' ko local calendar mein schedule kar doon?", "provider": "calendar-planner", "requires_confirmation": True, "action": {"type": "create_event", "event": event, "label": f"schedule event: {event_text[:80]}"}})
                email_command = re.match(r"(?:draft|write|prepare|compose)\s+(?:an?\s+)?email\s+to\s+([^\s]+@[^\s]+)\s*(?:subject\s*[:,-]\s*(.+?))?\s*(?:body|message|content)\s*[:,-]\s*(.+)$", message, re.I)
                if email_command:
                    recipient, subject, body = email_command.group(1), (email_command.group(2) or "SARA email draft"), email_command.group(3)
                    label = f"open an email draft to {recipient}"
                    return self.send_json(200, {"reply": f"Boss, should I open this email draft for {recipient}?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "email_draft", "to": recipient, "subject": subject.strip(), "body": body.strip(), "label": label}})
                if re.search(r"(?:daily plan|today(?:'s|s)? plan|plan for today|aaj ka plan|aaj ka schedule)", lower):
                    reply, agenda = agenda_reply("aaj ka local plan")
                    return self.send_json(200, {"reply": reply, "provider": "daily-plan", "plan": agenda})
                if re.search(r"(?:briefing|agenda|what(?:'s| is) next|next kya|aage kya|aaj ka briefing|meri priorities)", lower):
                    reply, agenda = agenda_reply("Jarvis briefing")
                    return self.send_json(200, {"reply": reply, "provider": "daily-briefing", "agenda": agenda})
                if re.search(r"(?:export|download|save)\s+(?:my\s+)?(?:calendar|events?)|calendar\s+export", lower):
                    return self.send_json(200, {"reply": "Boss, local calendar export ready hai. Browser mein `/api/calendar.ics` open karke `.ics` file download kar sakte ho.", "provider": "calendar-export", "download": "/api/calendar.ics"})
                if re.search(r"(?:show|list|dikhao|batao).*(?:reminder|reminders)|(?:reminder|reminders).*(?:show|list|dikhao|batao)", lower):
                    reminders = [item for item in read_reminders() if item.get("status") in {"pending", "due"}]
                    if not reminders:
                        return self.send_json(200, {"reply": "Boss, abhi koi pending reminder nahi hai.", "provider": "reminder-list", "reminders": []})
                    lines = [f"{index}. {item.get('text', '')}" for index, item in enumerate(reminders, 1)]
                    return self.send_json(200, {"reply": "Boss, aapke reminders:\n" + "\n".join(lines), "provider": "reminder-list", "reminders": reminders})
                reminder_delete = re.search(r"(?:delete|remove|hatao|cancel)\s+(?:reminder|yaad)\s+(\d+)", lower)
                if reminder_delete:
                    reminders = [item for item in read_reminders() if item.get("status") in {"pending", "due"}]
                    index = int(reminder_delete.group(1)) - 1
                    if index < 0 or index >= len(reminders):
                        return self.send_json(200, {"reply": "Boss, us number ka reminder nahi mila.", "provider": "reminder-list"})
                    item = reminders[index]
                    return self.send_json(200, {"reply": f"Boss, kya main ye reminder delete kar doon: {item.get('text', '')}?", "provider": "reminder-planner", "requires_confirmation": True, "action": {"type": "delete_reminder", "id": item.get("id"), "label": f"delete reminder: {item.get('text', '')[:80]}"}})
                task_add = re.match(r"(?:add|create|new)\s+(?:a\s+)?task\s+(.+)$|task\s+(?:add|create)\s+(.+)$|(?:task|kaam)\s+(?:likho|banao)\s+(.+)$", message, re.I)
                if task_add:
                    task_text = next(group for group in task_add.groups() if group).strip()
                    return self.send_json(200, {"reply": "Boss, kya main ye task local task list mein save kar doon?", "provider": "task-planner", "requires_confirmation": True, "action": {"type": "create_task", "text": task_text, "label": f"save task: {task_text[:80]}"}})
                if re.search(r"(?:show|list|dikhao|batao).*(?:tasks|to-do|todo|kaam)|(?:tasks|to-do|todo|kaam).*(?:show|list|dikhao|batao)", lower):
                    tasks = read_tasks()
                    pending = [item for item in tasks if item.get("status") == "pending"]
                    reply = "Boss, pending tasks:\n" + "\n".join(f"{index + 1}. {item.get('text')}" for index, item in enumerate(pending)) if pending else "Boss, koi pending task nahi hai."
                    return self.send_json(200, {"reply": reply, "provider": "task-list", "tasks": pending})
                task_delete = re.search(r"(?:delete|remove|hatao|cancel)\s+(?:task|kaam)\s+(\d+)", lower)
                if task_delete:
                    pending = [item for item in read_tasks() if item.get("status") == "pending"]
                    index = int(task_delete.group(1)) - 1
                    if index < 0 or index >= len(pending):
                        return self.send_json(200, {"reply": "Boss, us number ka pending task nahi mila.", "provider": "task-list"})
                    item = pending[index]
                    return self.send_json(200, {"reply": f"Boss, kya main ye task delete kar doon: {item.get('text', '')}?", "provider": "task-planner", "requires_confirmation": True, "action": {"type": "delete_task", "id": item.get("id"), "label": f"delete task: {item.get('text', '')[:80]}"}})
                task_done = re.search(r"(?:complete|finish|done|pura|khatam)\s+task\s+(\d+)", lower)
                if task_done:
                    pending = [item for item in read_tasks() if item.get("status") == "pending"]
                    index = int(task_done.group(1)) - 1
                    if index < 0 or index >= len(pending): return self.send_json(200, {"reply": "Boss, us number ka pending task nahi mila.", "provider": "task-list"})
                    item = pending[index]
                    return self.send_json(200, {"reply": f"Boss, kya main task complete mark kar doon: {item.get('text')}?", "provider": "task-planner", "requires_confirmation": True, "action": {"type": "complete_task", "id": item.get("id"), "text": item.get("text"), "label": f"complete task: {item.get('text', '')[:80]}"}})
                if re.search(r"(?:workspace|project)\s*(?:ki\s*)?(?:files|file)\s*(?:dikhao|show|list|batao)?|list\s+(?:the\s+)?files", lower):
                    files = workspace_files()
                    shown = files[:80]
                    suffix = f"\n…and {len(files) - len(shown)} more." if len(files) > len(shown) else ""
                    return self.send_json(200, {"reply": "Boss, readable workspace files:\n" + "\n".join(shown) + suffix, "provider": "workspace-files"})
                write_match = re.match(r"(?:write|save|create)\s+(?:file\s+)?([^\s:]+\.(?:md|txt|py|json|html|css|js|bat|csv))\s*(?::|with\s+content|content)\s*(.+)$", message, re.I | re.S)
                if write_match:
                    relative, content = write_match.group(1).strip(), write_match.group(2).strip()
                    if workspace_target(relative) is None:
                        return self.send_json(200, {"reply": "Boss, woh path SARA ke safe workspace scope ke bahar hai.", "provider": "workspace-write"})
                    return self.send_json(200, {"reply": f"Boss, kya main `{relative}` ko create/update kar doon?", "provider": "workspace-write", "requires_confirmation": True, "action": {"type": "write_file", "path": relative, "content": content, "label": f"write workspace file: {relative}"}})
                delete_match = re.match(r"(?:delete|remove|hatao)\s+(?:file\s+)?([^\s]+\.(?:md|txt|py|json|html|css|js|bat|csv))\s*$", message, re.I)
                if delete_match:
                    relative = delete_match.group(1).strip()
                    target = workspace_target(relative)
                    if target is None or not target.is_file():
                        return self.send_json(200, {"reply": "Boss, woh file safe workspace scope mein nahi mili.", "provider": "workspace-delete"})
                    return self.send_json(200, {"reply": f"Boss, kya main `{relative}` permanently delete kar doon?", "provider": "workspace-delete", "requires_confirmation": True, "action": {"type": "delete_file", "path": relative, "label": f"delete workspace file: {relative}"}})
                read_match = re.search(r"(?:read\s+file|file\s+(?:padho|padhkar)|read)\s+([\\w./-]+\.(?:md|txt|py|json|html|css|js|bat|csv))\b", message, re.I)
                if read_match:
                    content, error = read_workspace_text(read_match.group(1))
                    if error: return self.send_json(200, {"reply": f"Boss, {error}", "provider": "workspace-read"})
                    return self.send_json(200, {"reply": f"Boss, `{read_match.group(1)}` ka content:\n\n{content[:12000]}", "provider": "workspace-read"})
                search_match = re.search(
                    r"\b(?:search|find)\s+(?:in\s+)?(?:the\s+)?(?:workspace|project|files|file)\s+(?:for\s+)?(.+)$"
                    r"|\b(?:workspace|project|files|file)\s+(?:mein|me)\s+(?:search|find)\s+(.+)$"
                    r"|\b(?:workspace|project|files|file)\s+(?:mein|me)\s+(.+?)\s+(?:dhoondo|khojo|search\s+karo)$",
                    message, re.I,
                )
                if search_match:
                    query = next((part.strip().strip('"\'') for part in search_match.groups() if part), "")
                    if not query or len(query) > 200:
                        return self.send_json(200, {"reply": "Boss, search ke liye 1–200 character ka topic batayein.", "provider": "workspace-search"})
                    matches = search_workspace_text(query)
                    if not matches:
                        return self.send_json(200, {"reply": f"Boss, safe readable workspace text mein '{query}' ka match nahi mila.", "provider": "workspace-search", "matches": []})
                    lines = []
                    for item in matches:
                        lines.append(f"{item['path']} (lines {', '.join(str(snippet['line']) for snippet in item['snippets'])})")
                        lines.extend(f"  {snippet['text']}" for snippet in item["snippets"])
                    reply = f"Boss, '{query}' ke sabse relevant workspace matches ye hain:\n" + "\n".join(lines)
                    return self.send_json(200, {"reply": reply, "provider": "workspace-search", "matches": matches})
                if re.search(r"remind me|reminder|yaad dila", lower):
                    reminder = {"id": now(), "text": message, "created": now(), "status": "pending", "due_at": parse_due_at(message)}
                    return self.send_json(200, {"reply": "Boss, main is reminder ko local SARA reminders mein save kar sakti hoon. Save kar doon?", "provider": "reminder-planner", "requires_confirmation": True, "action": {"type": "create_reminder", "reminder": reminder}})
                memory_text = memory_request_text(message)
                if memory_text:
                    return self.send_json(200, {"reply": "Kya main ise future chats ke liye SARA ki approved memory mein save karoon?", "provider": "memory-planner", "requires_confirmation": True, "action": {"type": "save_memory", "text": memory_text, "label": f"save approved preference: {memory_text[:80]}"}})
                if re.search(r"weather|mausam|temperature|tempreature", lower):
                    location_match = re.search(r"(?:in|at|for|mein)\s+([a-zA-Z][a-zA-Z .'-]{1,40})", message, re.I)
                    try:
                        reply = weather_report(location_match.group(1).strip() if location_match else "")
                        self.trace("Weather lookup completed")
                        return self.send_json(200, {"reply": reply, "provider": "weather-tool"})
                    except Exception as exc:
                        self.trace(f"Weather lookup failed: {type(exc).__name__}: {exc}")
                        return self.send_json(200, {"reply": "Boss, weather service abhi reachable nahi hai. Kya main browser mein weather page open kar doon?", "provider": "weather-tool", "requires_confirmation": True, "action": {"type": "open_browser_url", "url": "https://www.google.com/search?q=" + quote_plus("today weather"), "label": "open today's weather"}})
                action_url = None
                action_label = None
                app_action = None
                if re.search(r"youtube", lower) and re.search(r"\b(open|khol|play|chala)\b", lower):
                    play_match = re.search(r"(?:play|chala(?:o)?|bajao)\s+(.+?)(?:\s+on\s+youtube|\s+youtube)?$", message, re.I)
                    query = play_match.group(1).strip() if play_match else ""
                    action_url = "https://www.youtube.com/results?search_query=" + quote_plus(query) if query else "https://www.youtube.com"
                    action_label = f"search YouTube for {query}" if query else "open YouTube"
                    self.trace(f"Action requested: {action_label}; confirmation pending")
                    return self.send_json(200, {"reply": f"Boss, should I {action_label} in the browser?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "open_browser_url", "url": action_url, "label": action_label}})
                open_app_request = re.search(r"\b(open|launch|start)\b|(?<!\w)(?:khol(?:o|na|do)?|chalao)(?!\w)", lower)
                for app_name in ("chrome", "notepad", "calculator"):
                    if re.search(rf"\b{app_name}\b", lower) and open_app_request:
                        app_action, action_label = app_name, f"open {app_name}"
                        break
                if app_action:
                    self.trace(f"Action requested: {action_label}; confirmation pending")
                    return self.send_json(200, {"reply": f"Boss, I can {action_label}. Should I open it?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "open_app", "app": app_action, "label": action_label}})
                if open_app_request:
                    for app in sorted(read_apps(), key=lambda item: len(str(item.get("name", ""))), reverse=True):
                        app_name = str(app.get("name", "")).strip()
                        if app_name and re.search(rf"(?<!\w){re.escape(app_name)}(?!\w)", message, re.I):
                            action_label = f"open {app_name}"
                            self.trace(f"Action requested: {action_label}; confirmation pending")
                            return self.send_json(200, {"reply": f"Boss, should I open {app_name}?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "open_app", "app": app_name, "executable": app.get("executable"), "label": action_label}})
                whatsapp_command = re.search(r"(?:send|message|msg)\s+(?:a\s+)?whatsapp(?:\s+message)?\s+(\+?\d{8,15})\s*[:,-]?\s*(.+)$", message, re.I)
                if whatsapp_command:
                    phone, text_message = whatsapp_command.group(1), whatsapp_command.group(2).strip()
                    label = f"send WhatsApp message to {phone}"
                    return self.send_json(200, {"reply": f"Boss, should I send this exact WhatsApp message to {phone}?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "whatsapp_send", "phone": phone, "text": text_message, "label": label}})
                # Writing/creating content is not the same as typing into the focused desktop app.
                # Only an explicit type/enter command may trigger keyboard input.
                type_match = re.search(r"(?:type|enter|write|likho)\s+(.+?)\s+(?:in|into|mein)\s+(?:the\s+)?(?:current|focused|active)\s+(?:app|window)|(?:type|enter)\s+(.+?)(?:\s+in(?:to)?\s+(?:the\s+)?(?:current|focused)\s+app)?$", message, re.I)
                if type_match:
                    text_to_type = (type_match.group(1) or type_match.group(2)).strip().strip('"')
                    label = f"type '{text_to_type[:60]}{'...' if len(text_to_type) > 60 else ''}' in the focused app"
                    self.trace(f"Action requested: {label}; confirmation pending")
                    return self.send_json(200, {"reply": f"Boss, should I type that into the currently focused application?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "type_text", "text": text_to_type, "label": label}})
                hotkey_match = re.search(r"(?:press|hit|use)\s+((?:ctrl|shift|alt|win|enter|esc|tab|space|backspace|delete|home|end|left|right|up|down|[a-z]|f(?:[1-9]|1[0-2]))(?:\s*\+\s*(?:ctrl|shift|alt|win|enter|esc|tab|space|backspace|delete|home|end|left|right|up|down|[a-z]|f(?:[1-9]|1[0-2])))*)\b", lower, re.I)
                if hotkey_match:
                    keys = [key.strip() for key in hotkey_match.group(1).split("+")]
                    label = "press " + "+".join(keys)
                    self.trace(f"Action requested: {label}; confirmation pending")
                    return self.send_json(200, {"reply": f"Boss, should I send {label} to the focused application?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "hotkey", "keys": keys, "label": label}})
                click_match = re.search(r"(?:click|click karo|press)\s+(?:at\s+)?(\d+)\s*[, ]\s*(\d+)", lower)
                if click_match:
                    x, y = int(click_match.group(1)), int(click_match.group(2)); label = f"click at ({x}, {y})"
                    self.trace(f"Action requested: {label}; confirmation pending")
                    return self.send_json(200, {"reply": f"Boss, should I click screen coordinate ({x}, {y})?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "click_point", "x": x, "y": y, "label": label}})
                browser_click = re.search(r"click\s+['\"]?(.+?)['\"]?\s+on\s+(https://\S+)", message, re.I)
                if browser_click:
                    text_label, target = browser_click.group(1).strip(" '\""), browser_click.group(2).rstrip(".,)")
                    label = f"click '{text_label}' on {target}"
                    return self.send_json(200, {"reply": f"Boss, should I open the page and click '{text_label}'?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "browser_click_text", "url": target, "text": text_label, "label": label}})
                browser_fill = re.search(r"fill\s+['\"]?(.+?)['\"]?\s+with\s+['\"]?(.+?)['\"]?\s+on\s+(https://\S+)", message, re.I)
                if browser_fill:
                    field, value, target = browser_fill.group(1).strip(" '\""), browser_fill.group(2).strip(" '\""), browser_fill.group(3).rstrip(".,)")
                    label = f"fill '{field}' on {target}"
                    return self.send_json(200, {"reply": f"Boss, should I open the page and fill the '{field}' field?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "browser_fill", "url": target, "label": field, "value": value, "label_text": label}})
                browser_open = re.search(r"(?:open|khol)\s+(https://\S+)", message, re.I)
                if browser_open:
                    target = browser_open.group(1).rstrip(".,)"); label = f"open {target}"
                    return self.send_json(200, {"reply": f"Boss, should I open {target} in SARA's controlled browser?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "browser_open", "url": target, "label": label}})
                search_match = re.search(r"(?:search|search karo|find|look up)\s+(?:for\s+)?(.+)", message, re.I)
                if search_match:
                    query = search_match.group(1).strip()
                    action_url, action_label = "https://www.google.com/search?q=" + quote_plus(query), f"search for {query}"
                    self.trace(f"Action requested: {action_label}; confirmation pending")
                    return self.send_json(200, {"reply": f"Boss, should I search for '{query}' in the browser?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "open_browser_url", "url": action_url, "label": action_label}})
                if re.search(r"\b(chrome|browser)\b", lower) and re.search(r"\b(open|khol|launch|start)\b", lower):
                    action_url, action_label = "https://www.google.com", "open Chrome/browser"
                if action_url:
                    reply = f"Boss, I can {action_label}. Should I open it in your browser?"
                    self.trace(f"Action requested: {action_label}; confirmation pending")
                    return self.send_json(200, {"reply": reply, "provider": "action-planner", "requires_confirmation": True, "action": {"type": "open_browser_url", "url": action_url, "label": action_label}})
                if unhandled_operation(message):
                    return self.send_json(200, {"reply": "Is operation ka connected tool route nahi mila, isliye kuch execute nahi hua. Exact app/URL ya Notepad mein likhne wala text batayein.", "provider": "action-unavailable"})
                on_token = None
                if "application/x-ndjson" in self.headers.get("Accept", ""):
                    self.stream_event({"type": "start"})
                    on_token = lambda token: self.stream_event({"type": "delta", "text": token})
                reply, provider = ask(message, on_token, tool_context=action_state.context(session)) if session else ask(message, on_token)
                self.ai_timing = request_performance()
                self.trace(f"Chat provider: {provider}")
                return self.send_json(200, {"reply": reply, "provider": provider})
            if path == "/api/memories":
                text = str(data.get("text", "")).strip()
                verdict = inspect_action("save_memory", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, {**verdict, "text": text})
                verdict = inspect_action("save_memory", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, {**verdict, "text": text})
                if not text or len(text) > 500: return self.send_json(400, {"error": "Memory must be 1–500 characters"})
                item = {"id": now(), "text": text, "created": now(), "approved": True}
                with MEMORY_LOCK:
                    items = read_memories(); items.append(item); write_memories(items)
                log("memory_added", {"id": item["id"]}); return self.send_json(201, item)
            if path == "/api/pronunciations":
                word = str(data.get("word", "")).strip()
                say_as = str(data.get("say_as", "")).strip()
                verdict = inspect_action("save_pronunciation", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, {**verdict, "word": word})
                if not word or not say_as or len(word) > 80 or len(say_as) > 160:
                    return self.send_json(400, {"error": "Word/phrase must be 1–80 characters and its pronunciation 1–160 characters."})
                if any(ord(char) < 32 and char not in "\t" for char in word + say_as):
                    return self.send_json(400, {"error": "Control characters are not allowed in a pronunciation entry."})
                with PRONUNCIATION_LOCK:
                    items = read_pronunciations()
                    existing = next((item for item in items if str(item.get("word", "")).casefold() == word.casefold()), None)
                    if existing:
                        existing["say_as"] = say_as; existing["updated"] = now(); item = existing; status = 200
                    else:
                        item = {"id": now(), "word": word, "say_as": say_as, "created": now()}; items.append(item); status = 201
                    write_pronunciations(items)
                log("pronunciation_saved", {"id": item["id"], "word": word})
                return self.send_json(status, {"ok": True, "result": f"Pronunciation saved for {word}.", "pronunciation": item})
            if path == "/api/capability-requests":
                title = str(data.get("title", "")).strip()
                description = str(data.get("description", "")).strip()
                verdict = inspect_action("save_capability_request", data.get("confirmed") is True)
                if not verdict["allowed"]: return self.send_json(409, {**verdict, "title": title, "description": description})
                if not title or len(title) > 120 or not description or len(description) > 1000:
                    return self.send_json(400, {"error": "A request title (up to 120 characters) and description (up to 1000 characters) are required."})
                if any(ord(char) < 32 and char not in "\n\t" for char in title + description):
                    return self.send_json(400, {"error": "Control characters are not allowed in a feature request."})
                with CAPABILITY_REQUEST_LOCK:
                    items = read_capability_requests()
                    existing = next((item for item in items if str(item.get("title", "")).casefold() == title.casefold() and str(item.get("description", "")).casefold() == description.casefold()), None)
                    if existing:
                        return self.send_json(200, {"ok": True, "result": "This feature request is already saved.", "request": existing})
                    item = {"id": now(), "title": title, "description": description, "status": "requested", "created": now()}
                    items.append(item); write_capability_requests(items)
                log("capability_request_saved", {"id": item["id"], "title": title})
                return self.send_json(201, {"ok": True, "result": f"Saved feature request: {title}.", "request": item})
            if path == "/api/apps":
                name = str(data.get("name", "")).strip()
                executable = str(data.get("executable", "")).strip().strip('"')
                verdict = inspect_action("add_custom_app", data.get("confirmed") is True)
                if not verdict["allowed"]: return self.send_json(409, {**verdict, "name": name, "executable": executable})
                if not re.fullmatch(r"[\w .-]{2,60}", name, re.UNICODE) or name in {".", ".."}:
                    return self.send_json(400, {"error": "Shortcut name must be 2–60 letters, numbers, spaces, dots, underscores or hyphens."})
                if len(executable) > 500 or any(ord(char) < 32 for char in executable):
                    return self.send_json(400, {"error": "Executable path is invalid or too long."})
                if not os.path.isabs(executable) or not executable.lower().endswith(".exe") or not os.path.isfile(executable):
                    return self.send_json(400, {"error": "Choose the full path to an existing .exe file. Arguments are not supported."})
                executable = os.path.realpath(executable)
                reserved = {"chrome", "notepad", "calculator"}
                with APP_LOCK:
                    items = read_apps()
                    existing_names = reserved | {str(item.get("name", "")).casefold() for item in items}
                    if name.casefold() in existing_names:
                        return self.send_json(409, {"error": "That shortcut name is already in use."})
                    item = {"id": now(), "name": name, "executable": executable, "created": now()}
                    items.append(item); write_apps(items)
                log("custom_app_added", {"id": item["id"], "name": name})
                return self.send_json(201, {"ok": True, "result": f"Saved app shortcut for {name}.", "app": item})
            if path == "/api/reminders":
                text = str(data.get("text", "")).strip()
                verdict = inspect_action("create_reminder", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, {**verdict, "text": text})
                verdict = inspect_action("create_reminder", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, {**verdict, "text": text})
                if not text: return self.send_json(400, {"error": "Reminder text is required"})
                item = {"id": data.get("id") or now(), "text": text, "created": now(), "status": "pending", "due_at": data.get("due_at")}
                with reminder_file_lock():
                    items = read_reminders(); items.append(item); write_reminders(items)
                log("reminder_added", {"id": item["id"]}); return self.send_json(201, item)
            if path == "/api/tasks":
                text = str(data.get("text", "")).strip()
                if not text: return self.send_json(400, {"error": "Task text is required"})
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This adds a local task.", "text": text})
                item = {"id": data.get("id") or now(), "text": text, "created": now(), "status": "pending"}
                with TASK_LOCK:
                    tasks = read_tasks(); tasks.append(item); write_tasks(tasks)
                log("task_added", {"id": item["id"]}); return self.send_json(201, item)
            if path == "/api/events":
                title = str(data.get("title", "")).strip()
                start_at = str(data.get("start_at", "")).strip()
                verdict = inspect_action("create_event", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, {**verdict, "title": title, "start_at": start_at})
                if not title or not start_at: return self.send_json(400, {"error": "Event title and start time are required"})
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This adds a local calendar event.", "title": title, "start_at": start_at})
                item = {"id": data.get("id") or now(), "title": title, "start_at": start_at, "created": now(), "status": "planned"}
                with EVENT_LOCK:
                    events = read_events(); events.append(item); write_events(events)
                log("event_added", {"id": item["id"], "title": title}); return self.send_json(201, {"ok": True, "result": f"Event scheduled: {title}", "event": item})
            if path.startswith("/api/events/") and path.endswith("/delete"):
                ident = path.split("/")[-2]
                verdict = inspect_action("delete_event", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                with EVENT_LOCK:
                    events = read_events(); item = next((event for event in events if event.get("id") == ident), None)
                    if not item: return self.send_json(404, {"error": "Event not found"})
                    if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This cancels a local calendar event.", "title": item.get("title")})
                    item["status"] = "cancelled"; item["cancelled_at"] = now(); write_events(events)
                log("event_cancelled", {"id": ident, "title": item.get("title", "")}); return self.send_json(200, {"ok": True, "result": f"Event cancelled: {item.get('title', 'Untitled')}", "event": item})
            if path.startswith("/api/tasks/") and path.endswith("/complete"):
                ident = path.split("/")[-2]
                verdict = inspect_action("complete_task", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                with TASK_LOCK:
                    tasks = read_tasks(); item = next((task for task in tasks if task.get("id") == ident), None)
                    if not item: return self.send_json(404, {"error": "Task not found"})
                    if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This marks a local task complete.", "text": item.get("text")})
                    item["status"] = "completed"; item["completed_at"] = now(); write_tasks(tasks)
                log("task_completed", {"id": ident}); return self.send_json(200, item)
            if path.startswith("/api/tasks/") and path.endswith("/delete"):
                ident = path.split("/")[-2]
                verdict = inspect_action("delete_task", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                with TASK_LOCK:
                    tasks = read_tasks(); item = next((task for task in tasks if task.get("id") == ident), None)
                    if not item: return self.send_json(404, {"error": "Task not found"})
                    if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This deletes a local task.", "text": item.get("text")})
                    write_tasks([task for task in tasks if task.get("id") != ident])
                log("task_deleted", {"id": ident}); return self.send_json(200, {"ok": True, "result": f"Task deleted: {item.get('text', '')}", "task": item})
            if path.startswith("/api/reminders/") and path.endswith("/delete"):
                verdict = inspect_action("delete_reminder", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                ident = path.split("/")[-2]
                with reminder_file_lock(): write_reminders([r for r in read_reminders() if r.get("id") != ident])
                log("reminder_deleted", {"id": ident}); return self.send_json(200, {"ok": True})
            if path == "/api/files/write":
                relative = str(data.get("path", "")).strip(); content = str(data.get("content", ""))
                target = workspace_target(relative)
                if target is None or len(content) > 1_000_000: return self.send_json(400, {"error": "Path must stay inside the readable workspace and content must be under 1 MB"})
                verdict = inspect_action("write_file", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, {**verdict, "path": relative})
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This creates or overwrites a workspace file.", "path": relative})
                target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content, encoding="utf-8"); log("file_written", {"path": relative}); self.trace(f"File written: {relative}"); return self.send_json(200, {"ok": True, "path": relative})
            if path == "/api/files/delete":
                relative = str(data.get("path", "")).strip(); target = workspace_target(relative)
                if target is None or not target.is_file(): return self.send_json(400, {"error": "File is outside the safe workspace scope or missing"})
                verdict = inspect_action("delete_file", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, {**verdict, "path": relative})
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This permanently deletes a workspace file.", "path": relative})
                target.unlink(); log("file_deleted", {"path": relative}); self.trace(f"File deleted: {relative}"); return self.send_json(200, {"ok": True, "path": relative})
            if path.startswith("/api/memories/") and path.endswith("/delete"):
                verdict = inspect_action("delete_memory", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                ident = path.split("/")[-2]
                with MEMORY_LOCK: write_memories([m for m in read_memories() if m.get("id") != ident])
                log("memory_deleted", {"id": ident}); return self.send_json(200, {"ok": True})
            if path.startswith("/api/pronunciations/") and path.endswith("/delete"):
                verdict = inspect_action("delete_pronunciation", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                ident = path.split("/")[-2]
                with PRONUNCIATION_LOCK:
                    items = read_pronunciations(); selected = next((item for item in items if item.get("id") == ident), None)
                    if not selected: return self.send_json(404, {"error": "Pronunciation entry not found"})
                    if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This removes a local pronunciation preference.", "word": selected.get("word")})
                    write_pronunciations([item for item in items if item.get("id") != ident])
                log("pronunciation_deleted", {"id": ident})
                return self.send_json(200, {"ok": True, "result": f"Pronunciation removed for {selected.get('word', 'word')}"})
            if path.startswith("/api/capability-requests/") and path.endswith("/delete"):
                verdict = inspect_action("delete_capability_request", data.get("confirmed") is True)
                if not verdict["allowed"]: return self.send_json(409, verdict)
                ident = path.split("/")[-2]
                with CAPABILITY_REQUEST_LOCK:
                    items = read_capability_requests(); selected = next((item for item in items if item.get("id") == ident), None)
                    if not selected: return self.send_json(404, {"error": "Feature request not found."})
                    write_capability_requests([item for item in items if item.get("id") != ident])
                log("capability_request_deleted", {"id": ident, "title": selected.get("title")})
                return self.send_json(200, {"ok": True, "result": f"Removed feature request: {selected.get('title', 'request')}"})
            if path.startswith("/api/apps/") and path.endswith("/delete"):
                verdict = inspect_action("delete_custom_app", data.get("confirmed") is True)
                if not verdict["allowed"]: return self.send_json(409, verdict)
                ident = path.split("/")[-2]
                with APP_LOCK:
                    items = read_apps(); selected = next((item for item in items if item.get("id") == ident), None)
                    if not selected: return self.send_json(404, {"error": "Custom app shortcut not found."})
                    write_apps([item for item in items if item.get("id") != ident])
                log("custom_app_deleted", {"id": ident, "name": selected.get("name")})
                return self.send_json(200, {"ok": True, "result": f"Removed app shortcut for {selected.get('name', 'application')}"})
            if path == "/api/tools/open-url":
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This opens a browser window."})
                return self.send_json(200, {"result": open_url(str(data.get("url", "")))})
            if path == "/api/actions/open-browser-url":
                verdict = inspect_action("open_browser_url", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                result = open_browser_url(str(data.get("url", "")), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: open_browser_url {data.get('url')}")
                return self.send_json(200, result)
            if path == "/api/actions/whatsapp-draft":
                verdict = inspect_action("whatsapp_draft", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                result = open_whatsapp_draft(data.get("phone", ""), str(data.get("text", "")), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace("Action completed: WhatsApp draft opened"); return self.send_json(200, result)
            if path == "/api/actions/open-app":
                verdict = inspect_action("open_app", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                result = open_app(data.get("app", ""), bool(data.get("confirmed")), data.get("executable"))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: open_app {data.get('app')}"); return self.send_json(200, result)
            if path == "/api/actions/notepad-write":
                result = create_notepad_note(data.get("text", ""), confirmed=data.get("confirmed") is True)
                return self.send_json(200 if result.get("ok") else 502, result)
            if path == "/api/actions/email-draft":
                verdict = inspect_action("email_draft", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                result = open_email_draft(data.get("to", ""), data.get("subject", ""), data.get("body", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace("Action completed: email draft opened"); return self.send_json(200, result)
            if path == "/api/actions/type-text":
                verdict = inspect_action("type_text", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                result = type_text(data.get("text", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace("Action completed: desktop text typed"); return self.send_json(200, result)
            if path == "/api/actions/hotkey":
                verdict = inspect_action("hotkey", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                result = press_hotkey(data.get("keys", []), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: desktop hotkey {data.get('keys')}"); return self.send_json(200, result)
            if path == "/api/actions/click-point":
                verdict = inspect_action("click_point", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                result = click_point(data.get("x"), data.get("y"), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: desktop click {data.get('x')},{data.get('y')}"); return self.send_json(200, result)
            if path == "/api/actions/browser-open":
                verdict = inspect_action("browser_open", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                result = semantic_open_page(data.get("url", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: browser open {data.get('url')}"); return self.send_json(200, result)
            if path == "/api/actions/browser-click-text":
                verdict = inspect_action("browser_click_text", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                result = semantic_click_text(data.get("url", ""), data.get("text", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: browser click text {data.get('text')}"); return self.send_json(200, result)
            if path == "/api/actions/browser-fill":
                verdict = inspect_action("browser_fill", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                result = semantic_fill_text(data.get("url", ""), data.get("label", ""), data.get("value", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: browser fill {data.get('label')}"); return self.send_json(200, result)
            if path == "/api/actions/whatsapp-send":
                verdict = inspect_action("whatsapp_send", bool(data.get("confirmed")))
                if not verdict["allowed"]: return self.send_json(409, verdict)
                result = whatsapp_send(data.get("phone", ""), data.get("text", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: WhatsApp send to {data.get('phone')}"); return self.send_json(200, result)
            self.send_json(404, {"error": "Not found"})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): self.trace("Client disconnected; stopped delivering this generation")
        except ValueError as exc: self.send_json(400, {"error": str(exc)})
        except Exception as exc: self.trace(f"ERROR: {type(exc).__name__}: {exc}"); log("server_error", {"error": str(exc)}); self.send_json(500, {"error": "SARA encountered an internal error"})
    def log_message(self, format, *args): self.trace(format % args)
def run():
    threading.Thread(target=reminder_watcher, daemon=True, name="sara-reminder-watcher").start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    console_trace(f"Server starting at http://127.0.0.1:{PORT}")
    console_trace(f"OPENAI_API_KEY={'present' if os.getenv('OPENAI_API_KEY') else 'missing'}")
    console_trace("Reminder watcher active")
    console_trace("Console colors enabled" if os.getenv("SARA_COLOR", "1").lower() not in {"0", "off", "false", "no"} else "Console colors disabled (SARA_COLOR=0)")
    console_trace("Press Ctrl+C to stop")
    threading.Thread(target=warmup_ollama, daemon=True, name="sara-model-warmup").start()
    open_dashboard()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console_trace("Stopping SARA; cancelling queued browser actions.")
    finally:
        server.server_close()
        shutdown_browser()
