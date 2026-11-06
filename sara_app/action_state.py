"""Short-lived, session-scoped action proposals and authoritative outcomes.

The store holds no executable callbacks and never performs an action. Callers must
atomically ``begin`` the reviewed proposal before executing its stored action and
then ``finish`` it with the real outcome. All public values are detached JSON
copies, so changing a response cannot change a proposal that was approved.
"""

import json
import time
from collections import OrderedDict
from threading import RLock
from uuid import uuid4


def _copy(value):
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("Action state must contain JSON-safe values.") from exc


def _compact(value, depth=0):
    """Keep model grounding bounded even for large drafts or tool results."""
    if isinstance(value, str):
        return value if len(value) <= 1600 else value[:1600] + "… [truncated]"
    if depth >= 4 and isinstance(value, (dict, list)):
        return "[details omitted]"
    if isinstance(value, dict):
        return {key: _compact(item, depth + 1) for key, item in list(value.items())[:16]}
    if isinstance(value, list):
        return [_compact(item, depth + 1) for item in value[:8]]
    return value


class ActionStore:
    def __init__(self, ttl_seconds=300, max_sessions=64, max_records=10, clock=None):
        if ttl_seconds <= 0 or max_sessions < 1 or max_records < 1:
            raise ValueError("TTL and store limits must be positive.")
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.max_records = max_records
        self._clock = clock or time.time
        self._sessions = OrderedDict()
        self._lock = RLock()

    def _session(self, session_id, create=False):
        if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 256:
            raise ValueError("A valid dashboard session id is required.")
        records = self._sessions.get(session_id)
        if records is None and create:
            records = OrderedDict()
            self._sessions[session_id] = records
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)
        if records is not None:
            self._sessions.move_to_end(session_id)
            now = self._clock()
            for record in records.values():
                if record["status"] == "pending" and now >= record["expires_at"]:
                    record.update(status="expired", updated_at=now, finished_at=now)
        return records

    def propose(self, session_id, action):
        action = _copy(action)
        if not isinstance(action, dict) or not action:
            raise ValueError("A non-empty action object is required.")
        proposal_id = action.pop("proposal_id", None)
        if not action:
            raise ValueError("A non-empty action object is required.")
        with self._lock:
            records = self._session(session_id, create=True)
            if proposal_id is not None:
                record = records.get(proposal_id) if isinstance(proposal_id, str) else None
                if record is None or record["action"] != action:
                    raise ValueError("Proposal token does not match this session and action.")
                return _copy(record)
            now = self._clock()
            for record in records.values():
                if record["status"] == "pending":
                    record.update(status="superseded", updated_at=now, finished_at=now)
            record = {
                "id": str(uuid4()), "action": action, "status": "pending",
                "created_at": now, "updated_at": now,
                "expires_at": now + self.ttl_seconds,
            }
            records[record["id"]] = record
            while len(records) > self.max_records:
                records.popitem(last=False)
            return _copy(record)

    def pending(self, session_id):
        with self._lock:
            records = self._session(session_id)
            if records:
                for record in reversed(records.values()):
                    if record["status"] == "pending":
                        return _copy(record)
            return None

    def get(self, session_id, proposal_id):
        with self._lock:
            records = self._session(session_id)
            record = records.get(proposal_id) if records and isinstance(proposal_id, str) else None
            return _copy(record) if record is not None else None

    def begin(self, session_id, proposal_id):
        with self._lock:
            records = self._session(session_id)
            record = records.get(proposal_id) if records and isinstance(proposal_id, str) else None
            if record is None:
                raise ValueError("This action proposal was not found in this session. Request it again.")
            if record["status"] != "pending":
                raise ValueError("This action proposal is " + record["status"] + "; it cannot execute.")
            record.update(status="executing", updated_at=self._clock())
            return _copy(record)

    def finish(self, session_id, proposal_id, status, result):
        if status not in {"completed", "failed"}:
            raise ValueError("An executed action must finish as completed or failed.")
        result = _copy(result)
        with self._lock:
            records = self._session(session_id)
            record = records.get(proposal_id) if records and isinstance(proposal_id, str) else None
            if record is None or record["status"] != "executing":
                raise ValueError("Only an executing action in this session can be finished.")
            now = self._clock()
            record.update(status=status, result=result, updated_at=now, finished_at=now)
            return _copy(record)

    def cancel(self, session_id, proposal_id=None):
        with self._lock:
            records = self._session(session_id)
            if not records:
                return None
            if proposal_id is None:
                record = next((item for item in reversed(records.values()) if item["status"] == "pending"), None)
            else:
                record = records.get(proposal_id) if isinstance(proposal_id, str) else None
            if record is None or record["status"] != "pending":
                return None
            now = self._clock()
            record.update(status="cancelled", updated_at=now, finished_at=now)
            return _copy(record)

    def context(self, session_id):
        with self._lock:
            records = self._session(session_id)
            pending_record = None
            outcomes = []
            if records:
                for record in records.values():
                    if record["status"] == "pending":
                        pending_record = record
                    elif record["status"] != "executing":
                        outcomes.append(record)
            outcomes.sort(key=lambda record: record["updated_at"])
            return _copy({
                "pending": _compact(pending_record),
                "recent_outcomes": [_compact(record) for record in outcomes[-3:]],
            })


_store = ActionStore()


def propose(session_id, action):
    return _store.propose(session_id, action)


def pending(session_id):
    return _store.pending(session_id)


def get(session_id, proposal_id):
    return _store.get(session_id, proposal_id)


def begin(session_id, proposal_id):
    return _store.begin(session_id, proposal_id)


def finish(session_id, proposal_id, status, result):
    return _store.finish(session_id, proposal_id, status, result)


def cancel(session_id, proposal_id=None):
    return _store.cancel(session_id, proposal_id)


def context(session_id):
    return _store.context(session_id)
