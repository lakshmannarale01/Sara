"""Planner creation boundaries: reviewed future times and unique local records."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import io
import json
import unittest
from unittest.mock import Mock, patch

from sara_app import server, policy


class PlannerApiTests(unittest.TestCase):
    def setUp(self):
        self.readers, self.writers = {}, {}
        for name in ("reminders", "tasks", "events"):
            self.readers[name] = self.patched(server, "read_" + name, return_value=[])
            self.writers[name] = self.patched(server, "write_" + name)
        self.patched(server, "log")
        self.patched(server, "reminder_file_lock", side_effect=nullcontext)
        self.patched(policy, "_stopped", False)
        self.future = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)

    def patched(self, target, name, *args, **kwargs):
        patcher = patch.object(target, name, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def post(self, kind, payload):
        raw = json.dumps(payload).encode()
        handler = object.__new__(server.Handler)
        handler.path = "/api/" + kind
        handler.headers = {"Content-Length": str(len(raw))}
        handler.rfile, handler.wfile = io.BytesIO(raw), io.BytesIO()
        handler.send_response, handler.send_header, handler.end_headers = Mock(), Mock(), Mock()
        handler.trace = Mock()
        handler.do_POST()
        return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())

    def payload(self, kind, **overrides):
        value = {"confirmed": True, "id": "new-record"}
        if kind == "events":
            value.update(title="Team sync", start_at=self.future.isoformat())
        else:
            value["text"] = "Review the report"
            if kind == "reminders":
                value["due_at"] = self.future.isoformat()
        return {**value, **overrides}

    def test_reminder_and_event_offsets_are_normalized_to_same_utc_instant(self):
        local = self.future.astimezone(timezone(timedelta(hours=5, minutes=30))).isoformat()
        for kind, field in (("reminders", "due_at"), ("events", "start_at")):
            with self.subTest(kind=kind):
                status, result = self.post(kind, self.payload(kind, **{field: local}))
                self.assertEqual(status, 201, result)
                item = self.writers[kind].call_args.args[0][0]
                self.assertEqual(item[field], self.future.isoformat())

    def test_untimed_reminder_is_explicitly_null(self):
        status, result = self.post("reminders", self.payload("reminders", due_at=None))
        self.assertEqual(status, 201, result)
        self.assertIsNone(self.writers["reminders"].call_args.args[0][0]["due_at"])

    def test_invalid_naive_past_and_nonstring_times_never_persist(self):
        for kind, field in (("reminders", "due_at"), ("events", "start_at")):
            for bad in ("nonsense", "2030-01-01T09:00:00", "2000-01-01T09:00:00Z", "2030-02-30T09:00:00Z", 12, {}, ""):
                with self.subTest(kind=kind, bad=bad):
                    status, result = self.post(kind, self.payload(kind, **{field: bad}))
                    self.assertEqual(status, 400, result)
                    self.writers[kind].assert_not_called()

    def test_event_requires_a_time(self):
        status, result = self.post("events", self.payload("events", start_at=None))
        self.assertEqual(status, 400, result)
        self.writers["events"].assert_not_called()

    def test_duplicate_ids_rejected_in_each_planner_list(self):
        for kind in self.readers:
            with self.subTest(kind=kind):
                existing = {"id": "new-record", "text": "Existing item"}
                self.readers[kind].return_value = [existing]
                status, result = self.post(kind, self.payload(kind))
                self.assertEqual(status, 409, result)
                self.writers[kind].assert_not_called()
                self.assertEqual(self.readers[kind].return_value, [existing])

    def test_unsafe_or_nonstring_ids_never_persist(self):
        for kind in self.readers:
            for ident in ("../outside", "", "bad\nid", 17, {"id": "x"}):
                with self.subTest(kind=kind, ident=ident):
                    status, result = self.post(kind, self.payload(kind, id=ident))
                    self.assertEqual(status, 400, result)
                    self.writers[kind].assert_not_called()

    def test_missing_approval_never_writes(self):
        for kind in self.readers:
            with self.subTest(kind=kind):
                status, result = self.post(kind, self.payload(kind, confirmed=False))
                self.assertEqual(status, 409, result)
                self.writers[kind].assert_not_called()

    def test_ids_are_generated_when_omitted(self):
        payload = self.payload("tasks")
        del payload["id"]
        status, result = self.post("tasks", payload)
        self.assertEqual(status, 201, result)
        self.assertTrue(self.writers["tasks"].call_args.args[0][0]["id"])

    def test_text_and_title_require_nonempty_strings(self):
        for kind in self.readers:
            field = "title" if kind == "events" else "text"
            for bad in (None, {}, "  "):
                with self.subTest(kind=kind, bad=bad):
                    status, result = self.post(kind, self.payload(kind, **{field: bad}))
                    self.assertEqual(status, 400, result)
                    self.writers[kind].assert_not_called()


if __name__ == "__main__":
    unittest.main()
