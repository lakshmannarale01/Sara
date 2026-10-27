import json, webbrowser, mimetypes, os, re, urllib.request, threading, time, subprocess
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.parse import quote_plus
from .config import ROOT, PORT
from .storage import now, read_memories, write_memories, read_reminders, write_reminders, read_conversations, append_conversation, read_tasks, write_tasks, read_events, write_events, log, LOG_FILE
from .ai import ask, speech_text
from .tools import open_url, open_browser_url, open_whatsapp_draft, open_app, open_email_draft
from .desktop import type_text, press_hotkey, click_point
from .browser_control import open_page as semantic_open_page, click_text as semantic_click_text, fill_text as semantic_fill_text, whatsapp_send
from .capabilities import capability_snapshot
PENDING_REMINDER = None

def reminder_watcher():
    while True:
        try:
            reminders = read_reminders(); changed = False; now_utc = datetime.now(timezone.utc)
            for item in reminders:
                due = item.get("due_at")
                if due and item.get("status") == "pending":
                    try:
                        if datetime.fromisoformat(due.replace("Z", "+00:00")) <= now_utc:
                            item["status"] = "due"; item["due_at"] = due; log("reminder_due", {"id": item.get("id"), "text": item.get("text", "")}); changed = True
                            try:
                                subprocess.run(["msg.exe", "*", "/TIME:60", f"SARA reminder: {item.get('text', '')}"], check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                                log("reminder_notification_attempted", {"id": item.get("id")})
                            except Exception as notify_exc: log("reminder_notification_failed", {"id": item.get("id"), "error": str(notify_exc)})
                    except ValueError: pass
            if changed: write_reminders(reminders)
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
    try:
        request = urllib.request.Request(f"{os.getenv('SARA_OLLAMA_URL', 'http://127.0.0.1:11434')}/api/tags")
        with urllib.request.urlopen(request, timeout=2) as response: ollama_ready = response.status == 200
    except Exception: ollama_ready = False
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

def workspace_files():
    return [str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.is_file() and not ({".venv", ".git", "sara_data", "__pycache__"} & set(path.parts)) and path.name != ".env"]

def workspace_target(relative):
    """Resolve a workspace path while excluding secrets and runtime state."""
    target = (ROOT / str(relative)).resolve()
    protected = {".venv", ".git", "sara_data", "__pycache__"}
    if ROOT not in target.parents or not str(relative).strip() or target.name == ".env" or protected & set(target.parts):
        return None
    return target

def read_workspace_text(relative):
    target = workspace_target(relative)
    if target is None or not target.is_file():
        return None, "That file is outside SARA's readable workspace scope."
    if target.stat().st_size > 100_000:
        return None, "That file is too large to read in chat."
    try: return target.read_text(encoding="utf-8"), None
    except UnicodeDecodeError: return None, "That file is not a readable text file."

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
    def trace(self, message): print(f"[SARA] {message}", flush=True)
    def send_json(self, status, data):
        if urlparse(self.path).path == "/api/chat" and isinstance(data, dict) and data.get("reply"):
            question = getattr(self, "chat_message", "")
            answer = str(data["reply"])[:4000]
            provider = data.get("provider", "unknown")
            append_conversation({"time": now(), "question": question, "answer": answer, "provider": provider})
            log("conversation", {"question": question, "answer": answer, "provider": provider})
            self.trace(f"Boss: {question}")
            self.trace(f"SARA ({provider}): {answer.replace(chr(10), ' ')}")
        body = json.dumps(data, ensure_ascii=False).encode()
        try:
            self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.trace("Client disconnected before SARA could deliver the response")
    def body(self):
        size = int(self.headers.get("Content-Length", "0")); return json.loads(self.rfile.read(size) or b"{}")
    def do_GET(self):
        path = urlparse(self.path).path
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
            try:
                request = urllib.request.Request(f"{os.getenv('SARA_OLLAMA_URL', 'http://127.0.0.1:11434')}/api/tags")
                with urllib.request.urlopen(request, timeout=2) as response: ollama_ok = response.status == 200
            except Exception: ollama_ok = False
            return self.send_json(200, {"ok": True, "ollama": ollama_ok, "model": os.getenv("SARA_OLLAMA_MODEL", "llama3.2")})
        if path == "/api/capabilities": return self.send_json(200, capability_snapshot())
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
            try:
                lines = LOG_FILE.read_text(encoding="utf-8").splitlines()[-30:]
                return self.send_json(200, [json.loads(line) for line in reversed(lines)])
            except (OSError, json.JSONDecodeError): return self.send_json(200, [])
        if path == "/api/conversations":
            try:
                items = read_conversations()
                if not items:
                    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()[-1000:]
                    items = []
                    for line in lines:
                        item = json.loads(line)
                        if item.get("event") == "conversation": items.append(item)
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
        path = urlparse(self.path).path
        try:
            data = self.body()
            if path == "/api/speech-text":
                text = str(data.get("text", "")).strip()
                if not text: return self.send_json(400, {"error": "Text is required"})
                spoken_text = speech_text(text[:1200])
                devanagari = any("\u0900" <= char <= "\u097f" for char in spoken_text)
                self.trace(f"Speech text prepared: devanagari={devanagari}")
                log("speech_text_prepared", {"devanagari": devanagari, "input_chars": len(text)})
                return self.send_json(200, {"text": spoken_text, "devanagari": devanagari})
            if path == "/api/tts":
                text = str(data.get("text", "")).strip()[:420]
                key = os.getenv("OPENAI_API_KEY")
                self.trace(f"TTS request: {len(text)} chars; API key={'present' if key else 'missing'}")
                if not key or not text: return self.send_json(400, {"error": "OpenAI TTS is not configured"})
                from openai import OpenAI
                audio = OpenAI(api_key=key).audio.speech.create(model="gpt-4o-mini-tts", voice="coral", input=text, instructions="Warm, natural female assistant voice. Conversational and concise.")
                body = getattr(audio, "content", None) or audio.read()
                self.trace(f"TTS success: {len(body)} bytes")
                self.send_response(200); self.send_header("Content-Type", "audio/mpeg"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            if path == "/api/chat":
                message = str(data.get("message", "")).strip()
                if not message: return self.send_json(400, {"error": "Message is required"})
                self.chat_message = message
                lower = message.lower()
                global PENDING_REMINDER
                if PENDING_REMINDER and re.search(r"^(yes|haan|save|save kar|kar do|confirm|ok|okay)\b", lower):
                    item = PENDING_REMINDER; PENDING_REMINDER = None
                    items = read_reminders(); items.append(item); write_reminders(items); log("reminder_added", {"id": item["id"]})
                    return self.send_json(200, {"reply": "Done Boss, reminder save kar diya.", "provider": "reminder-tool"})
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
                if re.search(r"remind me|reminder|yaad dila", lower):
                    reminder = {"id": now(), "text": message, "created": now(), "status": "pending", "due_at": parse_due_at(message)}
                    PENDING_REMINDER = reminder
                    return self.send_json(200, {"reply": "Boss, main is reminder ko local SARA reminders mein save kar sakti hoon. Save kar doon?", "provider": "reminder-planner", "requires_confirmation": True, "action": {"type": "create_reminder", "reminder": reminder}})
                memory_match = re.match(r"(?:remember|learn that|yaad rakho|yaad rakhna|save this|i prefer|my name is|call me)\s*[:,-]?\s*(.+)$", message, re.I)
                if memory_match:
                    memory_text = memory_match.group(1).strip()
                    return self.send_json(200, {"reply": "Boss, kya main ise approved memory mein save kar doon?", "provider": "memory-planner", "requires_confirmation": True, "action": {"type": "save_memory", "text": memory_text, "label": f"save memory: {memory_text[:80]}"}})
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
                for app_name in ("chrome", "notepad", "calculator"):
                    if re.search(rf"\b{app_name}\b", lower) and re.search(r"\b(open|khol|launch|start)\b", lower):
                        app_action, action_label = app_name, f"open {app_name}"
                        break
                if app_action:
                    self.trace(f"Action requested: {action_label}; confirmation pending")
                    return self.send_json(200, {"reply": f"Boss, I can {action_label}. Should I open it?", "provider": "action-planner", "requires_confirmation": True, "action": {"type": "open_app", "app": app_action, "label": action_label}})
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
                reply, provider = ask(message); self.trace(f"Chat provider: {provider}"); return self.send_json(200, {"reply": reply, "provider": provider})
            if path == "/api/memories":
                text = str(data.get("text", "")).strip()
                if not text or len(text) > 500: return self.send_json(400, {"error": "Memory must be 1–500 characters"})
                item = {"id": now(), "text": text, "created": now(), "approved": True}; items = read_memories(); items.append(item); write_memories(items); log("memory_added", {"id": item["id"]}); return self.send_json(201, item)
            if path == "/api/reminders":
                text = str(data.get("text", "")).strip()
                if not text: return self.send_json(400, {"error": "Reminder text is required"})
                item = {"id": data.get("id") or now(), "text": text, "created": now(), "status": "pending", "due_at": data.get("due_at")}; items = read_reminders(); items.append(item); write_reminders(items); log("reminder_added", {"id": item["id"]}); return self.send_json(201, item)
            if path == "/api/tasks":
                text = str(data.get("text", "")).strip()
                if not text: return self.send_json(400, {"error": "Task text is required"})
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This adds a local task.", "text": text})
                item = {"id": data.get("id") or now(), "text": text, "created": now(), "status": "pending"}; tasks = read_tasks(); tasks.append(item); write_tasks(tasks); log("task_added", {"id": item["id"]}); return self.send_json(201, item)
            if path == "/api/events":
                title = str(data.get("title", "")).strip()
                start_at = str(data.get("start_at", "")).strip()
                if not title or not start_at: return self.send_json(400, {"error": "Event title and start time are required"})
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This adds a local calendar event.", "title": title, "start_at": start_at})
                item = {"id": data.get("id") or now(), "title": title, "start_at": start_at, "created": now(), "status": "planned"}
                events = read_events(); events.append(item); write_events(events); log("event_added", {"id": item["id"], "title": title}); return self.send_json(201, {"ok": True, "result": f"Event scheduled: {title}", "event": item})
            if path.startswith("/api/events/") and path.endswith("/delete"):
                ident = path.split("/")[-2]; events = read_events(); item = next((event for event in events if event.get("id") == ident), None)
                if not item: return self.send_json(404, {"error": "Event not found"})
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This cancels a local calendar event.", "title": item.get("title")})
                item["status"] = "cancelled"; item["cancelled_at"] = now(); write_events(events); log("event_cancelled", {"id": ident, "title": item.get("title", "")}); return self.send_json(200, {"ok": True, "result": f"Event cancelled: {item.get('title', 'Untitled')}", "event": item})
            if path.startswith("/api/tasks/") and path.endswith("/complete"):
                ident = path.split("/")[-2]; tasks = read_tasks(); item = next((task for task in tasks if task.get("id") == ident), None)
                if not item: return self.send_json(404, {"error": "Task not found"})
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This marks a local task complete.", "text": item.get("text")})
                item["status"] = "completed"; item["completed_at"] = now(); write_tasks(tasks); log("task_completed", {"id": ident}); return self.send_json(200, item)
            if path.startswith("/api/tasks/") and path.endswith("/delete"):
                ident = path.split("/")[-2]; tasks = read_tasks(); item = next((task for task in tasks if task.get("id") == ident), None)
                if not item: return self.send_json(404, {"error": "Task not found"})
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This deletes a local task.", "text": item.get("text")})
                write_tasks([task for task in tasks if task.get("id") != ident]); log("task_deleted", {"id": ident}); return self.send_json(200, {"ok": True, "result": f"Task deleted: {item.get('text', '')}", "task": item})
            if path.startswith("/api/reminders/") and path.endswith("/delete"):
                ident = path.split("/")[-2]; write_reminders([r for r in read_reminders() if r.get("id") != ident]); log("reminder_deleted", {"id": ident}); return self.send_json(200, {"ok": True})
            if path == "/api/files/write":
                relative = str(data.get("path", "")).strip(); content = str(data.get("content", ""))
                target = workspace_target(relative)
                if target is None or len(content) > 1_000_000: return self.send_json(400, {"error": "Path must stay inside the readable workspace and content must be under 1 MB"})
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This creates or overwrites a workspace file.", "path": relative})
                target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content, encoding="utf-8"); log("file_written", {"path": relative}); self.trace(f"File written: {relative}"); return self.send_json(200, {"ok": True, "path": relative})
            if path == "/api/files/delete":
                relative = str(data.get("path", "")).strip(); target = workspace_target(relative)
                if target is None or not target.is_file(): return self.send_json(400, {"error": "File is outside the safe workspace scope or missing"})
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This permanently deletes a workspace file.", "path": relative})
                target.unlink(); log("file_deleted", {"path": relative}); self.trace(f"File deleted: {relative}"); return self.send_json(200, {"ok": True, "path": relative})
            if path.startswith("/api/memories/") and path.endswith("/delete"):
                ident = path.split("/")[-2]; write_memories([m for m in read_memories() if m.get("id") != ident]); log("memory_deleted", {"id": ident}); return self.send_json(200, {"ok": True})
            if path == "/api/tools/open-url":
                if not data.get("confirmed"): return self.send_json(409, {"requires_confirmation": True, "risk": "This opens a browser window."})
                return self.send_json(200, {"result": open_url(str(data.get("url", "")))})
            if path == "/api/actions/open-browser-url":
                result = open_browser_url(str(data.get("url", "")), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: open_browser_url {data.get('url')}")
                return self.send_json(200, result)
            if path == "/api/actions/whatsapp-draft":
                result = open_whatsapp_draft(data.get("phone", ""), str(data.get("text", "")), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace("Action completed: WhatsApp draft opened"); return self.send_json(200, result)
            if path == "/api/actions/open-app":
                result = open_app(data.get("app", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: open_app {data.get('app')}"); return self.send_json(200, result)
            if path == "/api/actions/email-draft":
                result = open_email_draft(data.get("to", ""), data.get("subject", ""), data.get("body", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace("Action completed: email draft opened"); return self.send_json(200, result)
            if path == "/api/actions/type-text":
                result = type_text(data.get("text", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace("Action completed: desktop text typed"); return self.send_json(200, result)
            if path == "/api/actions/hotkey":
                result = press_hotkey(data.get("keys", []), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: desktop hotkey {data.get('keys')}"); return self.send_json(200, result)
            if path == "/api/actions/click-point":
                result = click_point(data.get("x"), data.get("y"), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: desktop click {data.get('x')},{data.get('y')}"); return self.send_json(200, result)
            if path == "/api/actions/browser-open":
                result = semantic_open_page(data.get("url", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: browser open {data.get('url')}"); return self.send_json(200, result)
            if path == "/api/actions/browser-click-text":
                result = semantic_click_text(data.get("url", ""), data.get("text", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: browser click text {data.get('text')}"); return self.send_json(200, result)
            if path == "/api/actions/browser-fill":
                result = semantic_fill_text(data.get("url", ""), data.get("label", ""), data.get("value", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: browser fill {data.get('label')}"); return self.send_json(200, result)
            if path == "/api/actions/whatsapp-send":
                result = whatsapp_send(data.get("phone", ""), data.get("text", ""), bool(data.get("confirmed")))
                if result.get("requires_confirmation"): return self.send_json(409, result)
                self.trace(f"Action completed: WhatsApp send to {data.get('phone')}"); return self.send_json(200, result)
            self.send_json(404, {"error": "Not found"})
        except ValueError as exc: self.send_json(400, {"error": str(exc)})
        except Exception as exc: self.trace(f"ERROR: {type(exc).__name__}: {exc}"); log("server_error", {"error": str(exc)}); self.send_json(500, {"error": "SARA encountered an internal error"})
    def log_message(self, format, *args): self.trace(format % args)
def run():
    threading.Thread(target=reminder_watcher, daemon=True, name="sara-reminder-watcher").start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler); print(f"[SARA] Server starting at http://127.0.0.1:{PORT}", flush=True); print(f"[SARA] OPENAI_API_KEY={'present' if os.getenv('OPENAI_API_KEY') else 'missing'}", flush=True); print("[SARA] Reminder watcher active", flush=True); print("[SARA] Press Ctrl+C to stop", flush=True); webbrowser.open(f"http://127.0.0.1:{PORT}"); server.serve_forever()
