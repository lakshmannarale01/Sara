"""Exercise schedule clarification and reviewed writes without AI or disk I/O."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import io
import json
import unittest
from unittest.mock import Mock, patch

from sara_app import server, scheduling, scheduling_dialogue, action_state, policy
from sara_app.planner_validation import normalize_planner_time


class SchedulingWorkflowTests(unittest.TestCase):
    SESSION = "schedule_session_A"

    def setUp(self):
        self.reference = datetime(2026, 11, 13, 10, 15, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        self.clock = [100.0]
        self.patched(action_state, "_store", action_state.ActionStore(clock=lambda: self.clock[0]))
        self.patched(scheduling_dialogue, "_store", scheduling_dialogue.SchedulingDialogueStore(clock=lambda: self.clock[0]))
        self.patched(policy, "_stopped", False)
        self.patched(server, "parse_schedule_time", side_effect=lambda text: scheduling.parse_schedule_time(text, self.reference))
        self.patched(server, "normalize_planner_time", side_effect=lambda value, optional=False: normalize_planner_time(value, optional=optional, reference=self.reference))
        self.patched(server, "append_conversation")
        self.patched(server, "log")
        self.patched(server, "request_performance", return_value={})
        self.patched(server, "reminder_file_lock", side_effect=nullcontext)
        self.ask = self.patched(server, "ask", side_effect=AssertionError("Scheduling must not use an AI model"))
        self.writers = {}
        for kind in ("memories", "tasks", "events", "reminders", "conversations"):
            self.patched(server, "read_" + kind, return_value=[])
            if kind != "conversations":
                self.writers[kind] = self.patched(server, "write_" + kind)

    def patched(self, target, name, *args, **kwargs):
        patcher = patch.object(target, name, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def post(self, path, body, session=SESSION):
        raw = json.dumps({**body, "session_id": session}).encode()
        handler = object.__new__(server.Handler)
        handler.path, handler.headers = path, {"Content-Length": str(len(raw))}
        handler.rfile, handler.wfile = io.BytesIO(raw), io.BytesIO()
        handler.send_response, handler.send_header, handler.end_headers = Mock(), Mock(), Mock()
        handler.trace = Mock()
        handler.do_POST()
        return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())

    def chat(self, text, session=SESSION):
        status, data = self.post("/api/chat", {"message": text}, session)
        self.assertEqual(status, 200, data)
        return data

    def assert_unexecuted(self):
        self.ask.assert_not_called()
        for writer in self.writers.values():
            writer.assert_not_called()

    def test_hindi_relative_reminder_is_an_exact_unexecuted_proposal(self):
        data = self.chat("मुझे १० मिनट बाद पानी पीने की याद दिलाना")
        self.assertTrue(data["requires_confirmation"])
        self.assertEqual(data["action"]["type"], "create_reminder")
        self.assertEqual(data["action"]["reminder"]["due_at"], "2026-11-13T04:55:00+00:00")
        self.assert_unexecuted()

    def test_tomorrow_is_preserved_in_reminder(self):
        data = self.chat("remind me tomorrow at 5 pm to call home")
        self.assertEqual(data["action"]["reminder"]["due_at"], "2026-11-14T11:30:00+00:00")
        self.assert_unexecuted()

    def test_missing_time_accepts_short_followup_without_repeating_command(self):
        first = self.chat("remind me to take medicine")
        self.assertIn("clarification", first)
        self.assertNotIn("action", first)
        second = self.chat("kal subah 9 baje")
        self.assertEqual(second["action"]["reminder"]["due_at"], "2026-11-14T03:30:00+00:00")
        self.assertIn("medicine", second["action"]["reminder"]["text"])
        self.assert_unexecuted()

    def test_day_only_request_keeps_tomorrow_when_clock_is_given(self):
        self.chat("remind me tomorrow to take medicine")
        second = self.chat("subah nau baje")
        self.assertEqual(second["action"]["reminder"]["due_at"], "2026-11-14T03:30:00+00:00")

    def test_daypart_followup_resolves_ambiguous_hour(self):
        first = self.chat("kal 5 baje yaad dilana")
        self.assertEqual(first["clarification"]["reason"], "clarify")
        second = self.chat("shaam")
        self.assertEqual(second["action"]["reminder"]["due_at"], "2026-11-14T11:30:00+00:00")

    def test_corrected_clock_replaces_invalid_clock_and_keeps_day(self):
        first = self.chat("remind me kal at 25:90 to call home")
        self.assertEqual(first["clarification"]["reason"], "invalid")
        second = self.chat("5 pm")
        self.assertEqual(second["action"]["reminder"]["due_at"], "2026-11-14T11:30:00+00:00")

    def test_event_title_numbers_are_content_not_time(self):
        data = self.chat("schedule chapter 5 tomorrow at 5 pm")
        self.assertEqual(data["action"]["event"]["title"], "chapter 5")
        self.assertEqual(data["action"]["event"]["start_at"], "2026-11-14T11:30:00+00:00")
        self.assert_unexecuted()

    def test_hindi_event_command_keeps_title_and_exact_time(self):
        data = self.chat("कल शाम ५ बजे टीम मीटिंग रखो")
        self.assertEqual(data["action"]["event"]["title"], "टीम मीटिंग")
        self.assertEqual(data["action"]["event"]["start_at"], "2026-11-14T11:30:00+00:00")

    def test_event_clarification_preserves_title(self):
        first = self.chat("schedule team sync")
        self.assertNotIn("action", first)
        second = self.chat("tomorrow at 5 pm")
        self.assertEqual(second["action"]["event"]["title"], "team sync")

    def test_unrelated_message_clears_time_draft(self):
        self.chat("remind me to call home")
        self.ask.side_effect = None
        self.ask.return_value = ("A normal answer", "mock")
        self.chat("Explain sorting")
        data = self.chat("5 pm")
        self.assertNotIn("action", data)
        self.assertEqual(self.ask.call_count, 2)

    def test_cancel_discards_schedule_clarification(self):
        self.chat("remind me to call home")
        data = self.chat("cancel")
        self.assertTrue(data["schedule_cancelled"])
        self.assertIsNone(scheduling_dialogue.resume(self.SESSION, "5 pm"))
        self.assert_unexecuted()

    def test_other_session_cannot_complete_time_clarification(self):
        self.chat("remind me to call home")
        self.ask.side_effect = None
        self.ask.return_value = ("No pending schedule here", "mock")
        self.assertNotIn("action", self.chat("5 pm", session="schedule_session_B"))
        self.assertIn("action", self.chat("5 pm"))

    def test_explicit_untimed_reminder_has_no_notification(self):
        data = self.chat("remind me to read without a time")
        self.assertIsNone(data["action"]["reminder"]["due_at"])
        self.assertIn("बिना automatic notification", data["reply"])

    def test_explicit_past_today_is_not_moved_to_tomorrow(self):
        data = self.chat("remind me today at 9 am to call home")
        self.assertEqual(data["clarification"]["reason"], "invalid")
        self.assertNotIn("action", data)

    def test_reviewed_event_writes_only_after_approval_and_rejects_replay(self):
        data = self.chat("schedule team sync kal shaam 5 baje")
        self.assert_unexecuted()
        body = {**data["action"]["event"], "confirmed": True, "proposal_id": data["proposal_id"]}
        status, result = self.post("/api/events", body)
        self.assertEqual(status, 201, result)
        self.assertEqual(result["action_result"]["status"], "completed")
        self.writers["events"].assert_called_once()
        self.assertEqual(self.writers["events"].call_args.args[0][0]["title"], "team sync")
        self.assertEqual(self.post("/api/events", body)[0], 409)
        self.writers["events"].assert_called_once()

    def test_chapter_number_alone_does_not_schedule_an_event(self):
        data = self.chat("schedule chapter 5")
        self.assertNotIn("action", data)
        self.assertEqual(data["clarification"]["reason"], "missing")

    def test_devanagari_task_creation_is_reviewed_without_ai(self):
        data = self.chat("काम जोड़ो रिपोर्ट तैयार करना")
        self.assertEqual(data["action"]["text"], "रिपोर्ट तैयार करना")
        self.assertEqual(data["action"]["type"], "create_task")
        self.assert_unexecuted()

    def test_expired_time_clarification_needs_a_new_request(self):
        self.chat("remind me to call home")
        self.clock[0] += 301
        self.ask.side_effect = None
        self.ask.return_value = ("Please give the full reminder", "mock")
        self.assertNotIn("action", self.chat("5 pm"))


if __name__ == "__main__":
    unittest.main()
