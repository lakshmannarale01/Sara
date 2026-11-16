"""Named, reviewed sequences of bounded SARA actions; never scripts or shell.

Stored routines are data. Every run is bound to the exact saved revision and
steps, and each step rechecks Stop and any automatic-execution grant.
"""
import hashlib
import json
import re
from threading import Lock, RLock
from uuid import uuid4

from . import config, policy
from .storage import _read_json_list, _write_json_atomic, log, now

MAX_ROUTINES = 30
MAX_STEPS = 8
_lock = RLock()
_run_lock = Lock()
_FIELDS = {
    "open_app": {"type", "app"},
    "open_browser_url": {"type", "url"},
    "browser_open": {"type", "url"},
    "youtube_play": {"type", "query"},
    "media_control": {"type", "command", "level"},
}


def _copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _name(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 60 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Routine name must contain 1–60 characters without control characters.")
    return re.sub(r"\s+", " ", value.strip())


def normalize_name(value):
    """Public name normalization shared by chat and settings builders."""
    return _name(value)


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Invalid routine ID.")
    return value


def _revision_token(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Invalid routine revision; reload and review this routine.")
    return value


def normalize_steps(steps):
    """Return detached canonical actions, rejecting unknown fields and effects."""
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError(f"A routine must contain 1–{MAX_STEPS} steps.")
    normalized = []
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict) or not isinstance(step.get("type"), str):
            raise ValueError(f"Step {index} must be a supported action object.")
        kind = step["type"]
        if kind not in _FIELDS or set(step) - _FIELDS[kind]:
            raise ValueError(f"Step {index} contains an unsupported action or extra fields.")
        payload = {key: value for key, value in step.items() if key != "type"}
        if kind == "media_control":
            from .system_controls import normalize_media_payload
            payload = normalize_media_payload(payload)
        elif kind == "open_app":
            app = payload.get("app")
            if not isinstance(app, str):
                raise ValueError(f"Step {index} needs a built-in application name.")
            payload = {"app": app.strip().casefold()}
        else:
            key = "query" if kind == "youtube_play" else "url"
            value = payload.get(key)
            if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError(f"Step {index} needs a valid {key}.")
            payload = {key: value.strip()}
        if not policy.routine_action(kind, payload):
            raise ValueError(f"Step {index} is outside the supported routine scope.")
        normalized.append({"type": kind, **payload})
    return normalized


def _revision(name, steps):
    text = json.dumps({"name": name, "steps": steps}, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_record(item):
    if not isinstance(item, dict) or set(item) != {"id", "name", "steps", "revision", "created", "updated"}:
        raise ValueError("Invalid saved routine record.")
    name, steps = _name(item["name"]), normalize_steps(item["steps"])
    _identifier(item["id"])
    _revision_token(item["revision"])
    if name != item["name"] or steps != item["steps"] or item["revision"] != _revision(name, steps):
        raise ValueError("Saved routine content does not match its revision.")
    if any(not isinstance(item[key], str) or not 1 <= len(item[key]) <= 64 for key in ("created", "updated")):
        raise ValueError("Invalid saved routine timestamp.")
    return _copy(item)


def _records(strict=False):
    raw = _read_json_list(config.DATA_DIR / "routines.json")
    records, identifiers, names = [], set(), set()
    invalid = len(raw) > MAX_ROUTINES
    for item in raw:
        try:
            record = _canonical_record(item)
            if record["id"] in identifiers or record["name"].casefold() in names:
                raise ValueError("Duplicate saved routine.")
            identifiers.add(record["id"])
            names.add(record["name"].casefold())
            records.append(record)
        except (ValueError, TypeError, KeyError, ImportError):
            invalid = True
    if invalid and strict:
        # Do not drop semantically invalid records from otherwise valid JSON.
        raise ValueError("Saved routines contain invalid or duplicate records. Preserve and repair routines.json before modifying it.")
    return records[:MAX_ROUTINES]


def list_routines():
    with _lock:
        return _records()


def _find(identifier, revision, steps=None, name=None):
    _identifier(identifier)
    _revision_token(revision)
    record = next((item for item in _records(strict=True) if item["id"] == identifier), None)
    if not record or record["revision"] != revision:
        raise ValueError("This routine changed or was removed after review. Reload and review it again.")
    if steps is not None and normalize_steps(steps) != record["steps"]:
        raise ValueError("Routine steps changed after review.")
    if name is not None and _name(name) != record["name"]:
        raise ValueError("Routine name changed after review.")
    return record


def validate_run_payload(payload):
    """Bind a run proposal to the current immutable saved snapshot."""
    if not isinstance(payload, dict) or set(payload) != {"id", "name", "revision", "steps"}:
        raise ValueError("A routine run requires its exact ID, name, revision and steps.")
    with _lock:
        record = _find(payload["id"], payload["revision"], payload["steps"], payload["name"])
        return {key: record[key] for key in ("id", "name", "revision", "steps")}


def routine_action_for_name(name):
    key = _name(name).casefold()
    with _lock:
        record = next((item for item in _records(strict=True) if item["name"].casefold() == key), None)
        if not record:
            raise ValueError("No saved routine with that name was found. Create it in Settings first.")
        return {"type": "run_routine", **{key: record[key] for key in ("id", "name", "revision", "steps")},
                "label": "Run saved routine: " + record["name"]}


def _paused():
    return {"ok": False, "stopped": True, "result": "SARA actions are paused. Resume actions before changing or running a routine."}


def save_routine(name, steps, confirmed=False, id=None, revision=None):
    name, steps = _name(name), normalize_steps(steps)
    if (id is None) != (revision is None):
        raise ValueError("An update requires the saved routine ID and reviewed revision.")
    with _lock:
        records = _records(strict=True)
        current = _find(id, revision) if id is not None else None
        if any(item["name"].casefold() == name.casefold() and (not current or item["id"] != current["id"]) for item in records):
            raise ValueError("A routine with that name already exists. Edit its reviewed version or choose another name.")
        if not current and len(records) >= MAX_ROUTINES:
            raise ValueError(f"At most {MAX_ROUTINES} saved routines are supported.")
        if policy.is_stopped():
            return _paused()
        if confirmed is not True:
            return {"requires_confirmation": True, "name": name, "steps": steps, **({"id": id, "revision": revision} if current else {})}
        stamp = now()
        record = {"id": current["id"] if current else uuid4().hex, "name": name, "steps": steps,
                  "revision": _revision(name, steps), "created": current["created"] if current else stamp, "updated": stamp}
        records = [record if current and item["id"] == current["id"] else item for item in records]
        if not current:
            records.append(record)
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(config.DATA_DIR / "routines.json", records)
        log("routine_saved", {"routine_id": record["id"], "name": name, "step_count": len(steps)})
        return {"ok": True, "routine": _copy(record), "result": f"Routine '{name}' saved with {len(steps)} steps."}


def delete_routine(id, revision, confirmed=False):
    with _lock:
        current = _find(id, revision)
        if policy.is_stopped():
            return _paused()
        if confirmed is not True:
            return {"requires_confirmation": True, "id": id, "revision": revision, "name": current["name"]}
        _write_json_atomic(config.DATA_DIR / "routines.json", [item for item in _records(strict=True) if item["id"] != id])
        log("routine_deleted", {"routine_id": id, "name": current["name"]})
        return {"ok": True, "result": f"Routine '{current['name']}' removed."}


def _execute_step(step, automatic):
    from . import browser_control, tools
    if automatic:
        return tools.execute_routine_action(step)
    kind = step["type"]
    if kind == "open_app":
        return tools.open_app(step["app"], confirmed=True)
    if kind == "open_browser_url":
        return tools.open_browser_url(step["url"], confirmed=True)
    if kind == "browser_open":
        return browser_control.open_page(step["url"], confirmed=True)
    if kind == "youtube_play":
        return browser_control.play_youtube(step["query"], confirmed=True)
    if kind == "media_control":
        from .system_controls import execute_media_control
        return execute_media_control(step["command"], level=step.get("level"), confirmed=True)
    raise ValueError("The routine step has no connected executor.")


def execute_saved_routine(id, revision, steps, confirmed=False, automatic=False):
    """Run once, keep real per-step evidence, and stop before further effects."""
    if not isinstance(automatic, bool):
        raise ValueError("Invalid routine execution mode.")
    with _lock:
        record = _find(id, revision, steps)
    if policy.is_stopped():
        return _paused()
    if confirmed is not True and not automatic:
        return {"requires_confirmation": True, **{key: record[key] for key in ("id", "name", "revision", "steps")}}
    if not _run_lock.acquire(blocking=False):
        return {"ok": False, "running": True, "result": "Another saved routine is already running. Wait for its result before retrying."}
    outcomes, stopped, revoked, stale, failure = [], False, False, False, ""
    try:
        for index, step in enumerate(record["steps"], 1):
            with _lock:
                try:
                    _find(id, revision, record["steps"])
                except ValueError:
                    stale = True
                    failure = "The saved routine changed or was removed before the next step. Reload it before retrying."
                    break
                try:
                    if policy.is_stopped():
                        stopped = True
                        failure = "Actions were paused before the next step."
                        break
                    if automatic and policy.access_mode() != "trusted":
                        revoked = True
                        failure = "Trusted routine permission was revoked before the next step."
                        break
                    result = _execute_step(_copy(step), automatic)
                    if not isinstance(result, dict):
                        result = {"ok": False, "result": "This step did not return a verifiable tool result."}
                    result = _copy(result)
                except Exception as exc:
                    result = {"ok": False, "result": "Step completion could not be verified.", "error": str(exc)[:300]}
            succeeded = result.get("ok") is True and not result.get("requires_confirmation") and not result.get("error")
            outcomes.append({"index": index, "action": _copy(step), "status": "completed" if succeeded else "failed", "result": _copy(result)})
            if not succeeded:
                failure = "A step failed or did not report success; later steps were not requested."
                detail = result.get("error") or result.get("result")
                if isinstance(detail, str) and detail:
                    failure += " " + detail[:300]
                break
        completed = sum(item["status"] == "completed" for item in outcomes)
        ok = completed == len(record["steps"])
        detail = f"Routine '{record['name']}': {completed}/{len(record['steps'])} steps completed."
        if failure:
            detail += " " + failure
        result = {"ok": ok, "result": detail, "routine_id": id, "revision": revision,
                  "completed_steps": completed, "attempted_steps": len(outcomes), "total_steps": len(record["steps"]),
                  "partial": bool(completed and not ok), "step_results": outcomes}
        if stopped:
            result["stopped"] = True
        if revoked:
            result["permission_revoked"] = True
        if stale:
            result["stale"] = True
        log("routine_result", {"routine_id": id, "completed_steps": completed, "total_steps": len(record["steps"]), "ok": ok, "stopped": stopped, "permission_revoked": revoked})
        return result
    finally:
        _run_lock.release()
