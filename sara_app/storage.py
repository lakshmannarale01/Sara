import json
import os
import tempfile
from threading import Lock, RLock
from datetime import datetime, timezone
from uuid import uuid4
from .config import DATA_DIR, MEMORY_FILE, PRONUNCIATION_FILE, APP_FILE, CAPABILITY_REQUEST_FILE, REMINDER_FILE, LOG_FILE, CONVERSATION_FILE, TASK_FILE, EVENT_FILE
from .console import trace as console_trace
DATA_DIR.mkdir(exist_ok=True)
if not MEMORY_FILE.exists(): MEMORY_FILE.write_text("[]", encoding="utf-8")
if not PRONUNCIATION_FILE.exists(): PRONUNCIATION_FILE.write_text("[]", encoding="utf-8")
if not APP_FILE.exists(): APP_FILE.write_text("[]", encoding="utf-8")
if not CAPABILITY_REQUEST_FILE.exists(): CAPABILITY_REQUEST_FILE.write_text("[]", encoding="utf-8")
if not REMINDER_FILE.exists(): REMINDER_FILE.write_text("[]", encoding="utf-8")
if not CONVERSATION_FILE.exists(): CONVERSATION_FILE.write_text("[]", encoding="utf-8")
if not TASK_FILE.exists(): TASK_FILE.write_text("[]", encoding="utf-8")
if not EVENT_FILE.exists(): EVENT_FILE.write_text("[]", encoding="utf-8")
CONVERSATION_LOCK = Lock()
MEMORY_LOCK = RLock()
PRONUNCIATION_LOCK = RLock()
APP_LOCK = RLock()
CAPABILITY_REQUEST_LOCK = RLock()
TASK_LOCK = RLock()
EVENT_LOCK = RLock()
_ACTIVITY_TAIL_BYTES = 1024 * 1024
_ACTIVITY_CHUNK_BYTES = 16 * 1024


def read_recent_activity(limit=30):
    """Read newest activity records without scanning the growing log.

    Read backwards in small binary chunks, stopping when enough records have
    been found or one MiB has been inspected. A chunk may begin inside a UTF-8
    character or a JSON record; its leading fragment is retained until the
    previous chunk arrives. Invalid/incomplete records are skipped separately.
    """
    try:
        limit = min(500, max(0, int(limit)))
    except (TypeError, ValueError):
        return []
    if not limit:
        return []
    records = []
    try:
        with LOG_FILE.open("rb") as source:
            source.seek(0, 2)
            position = source.tell()
            oldest_position = max(0, position - _ACTIVITY_TAIL_BYTES)
            fragment = b""
            while position > oldest_position:
                amount = min(_ACTIVITY_CHUNK_BYTES, position - oldest_position)
                position -= amount
                source.seek(position)
                lines = (source.read(amount) + fragment).split(b"\n")
                fragment = lines.pop(0) if position else b""
                for raw in reversed(lines):
                    if not raw.strip():
                        continue
                    try:
                        record = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if isinstance(record, dict):
                        records.append(record)
                        if len(records) >= limit:
                            return records
    except OSError:
        return []
    return records


def now(): return datetime.now(timezone.utc).isoformat()


def _write_json_atomic(path, items, limit=None):
    """Replace a local JSON list atomically so a crash cannot leave half a file."""
    values = items[-limit:] if limit else items
    payload = json.dumps(values, indent=2, ensure_ascii=False)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        _preserve_malformed_json(path)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _preserve_malformed_json(path):
    """Preserve unreadable records before a repaired list replaces their source.

    The backup is published only after all original bytes are flushed. Any read
    or backup failure aborts the caller's replacement so recovery cannot silently
    destroy a file that it could not preserve.
    """
    try:
        original = path.read_bytes()
    except FileNotFoundError:
        return
    try:
        records = json.loads(original.decode("utf-8"))
        valid = isinstance(records, list) and all(isinstance(item, dict) for item in records)
    except (UnicodeDecodeError, json.JSONDecodeError):
        valid = False
    if valid:
        return
    backup = path.with_name(f"{path.name}.recovery-{uuid4().hex}.bak")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.recovery.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(original)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, backup)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    console_trace(f"Local data recovery: preserved {path.name} as {backup.name} before updating it.")


def _read_json_list(path):
    """Return only valid top-level JSON lists; treat malformed local data as empty."""
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return []
    except (UnicodeDecodeError, json.JSONDecodeError):
        console_trace(f"Local data warning: {path.name} contains invalid UTF-8 JSON; ignoring it.")
        return []
    if not isinstance(items, list):
        console_trace(f"Local data warning: {path.name} must contain a JSON list; ignoring it.")
        return []
    valid = [item for item in items if isinstance(item, dict)]
    if len(valid) != len(items):
        console_trace(f"Local data warning: skipped malformed records in {path.name}.")
    return valid


def read_memories():
    return _read_json_list(MEMORY_FILE)
def write_memories(items): _write_json_atomic(MEMORY_FILE, items)
def read_pronunciations():
    return _read_json_list(PRONUNCIATION_FILE)
def write_pronunciations(items):
    with PRONUNCIATION_LOCK: _write_json_atomic(PRONUNCIATION_FILE, items, limit=100)
def read_apps():
    return _read_json_list(APP_FILE)
def write_apps(items):
    with APP_LOCK: _write_json_atomic(APP_FILE, items, limit=100)
def read_capability_requests():
    return _read_json_list(CAPABILITY_REQUEST_FILE)
def write_capability_requests(items):
    with CAPABILITY_REQUEST_LOCK: _write_json_atomic(CAPABILITY_REQUEST_FILE, items, limit=200)
def read_reminders(): return _read_json_list(REMINDER_FILE)
def write_reminders(items): _write_json_atomic(REMINDER_FILE, items)
def read_conversations(): return _read_json_list(CONVERSATION_FILE)
def append_conversation(item):
    if item.get('chat_id'):
        from .chats import append
        return append(item['chat_id'], item)
    with CONVERSATION_LOCK:
        items = read_conversations(); items.append(item)
        _write_json_atomic(CONVERSATION_FILE, items, limit=200)
def read_tasks(): return _read_json_list(TASK_FILE)
def write_tasks(items):
    with TASK_LOCK: _write_json_atomic(TASK_FILE, items, limit=500)
def read_events(): return _read_json_list(EVENT_FILE)
def write_events(items):
    with EVENT_LOCK: _write_json_atomic(EVENT_FILE, items, limit=500)
def log(event, detail):
    with LOG_FILE.open("a", encoding="utf-8") as f: f.write(json.dumps({"time": now(), "event": event, **detail}, ensure_ascii=False) + "\n")
    console_trace(f"Event: {event}")
