import json
from threading import Lock
from datetime import datetime, timezone
from .config import DATA_DIR, MEMORY_FILE, REMINDER_FILE, LOG_FILE, CONVERSATION_FILE, TASK_FILE, EVENT_FILE
DATA_DIR.mkdir(exist_ok=True)
if not MEMORY_FILE.exists(): MEMORY_FILE.write_text("[]", encoding="utf-8")
if not REMINDER_FILE.exists(): REMINDER_FILE.write_text("[]", encoding="utf-8")
if not CONVERSATION_FILE.exists(): CONVERSATION_FILE.write_text("[]", encoding="utf-8")
if not TASK_FILE.exists(): TASK_FILE.write_text("[]", encoding="utf-8")
if not EVENT_FILE.exists(): EVENT_FILE.write_text("[]", encoding="utf-8")
CONVERSATION_LOCK = Lock()
def now(): return datetime.now(timezone.utc).isoformat()
def read_memories():
    try: return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return []
def write_memories(items): MEMORY_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
def read_reminders():
    try: return json.loads(REMINDER_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return []
def write_reminders(items): REMINDER_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
def read_conversations():
    try: return json.loads(CONVERSATION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return []
def append_conversation(item):
    with CONVERSATION_LOCK:
        items = read_conversations(); items.append(item)
        CONVERSATION_FILE.write_text(json.dumps(items[-200:], indent=2, ensure_ascii=False), encoding="utf-8")
def read_tasks():
    try: return json.loads(TASK_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return []
def write_tasks(items): TASK_FILE.write_text(json.dumps(items[-500:], indent=2, ensure_ascii=False), encoding="utf-8")
def read_events():
    try: return json.loads(EVENT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return []
def write_events(items): EVENT_FILE.write_text(json.dumps(items[-500:], indent=2, ensure_ascii=False), encoding="utf-8")
def log(event, detail):
    with LOG_FILE.open("a", encoding="utf-8") as f: f.write(json.dumps({"time": now(), "event": event, **detail}, ensure_ascii=False) + "\n")
