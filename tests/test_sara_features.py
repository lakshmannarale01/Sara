import unittest

from sara_app.ai import fallback_speech_text
from sara_app.server import agenda_reply, calendar_ics, event_title, parse_event_start, workspace_target, read_workspace_text


class SaraFeatureTests(unittest.TestCase):
    def test_offline_hinglish_speech_fallback_uses_devanagari(self):
        spoken = fallback_speech_text("Mujhe aaj ka plan batao")
        self.assertIn("मुझे", spoken)
        self.assertIn("आज", spoken)
        self.assertIn("बताओ", spoken)

    def test_event_command_parsing(self):
        message = "schedule team sync tomorrow at 5 pm"
        self.assertEqual(event_title(message), "team sync")
        self.assertIsNotNone(parse_event_start(message))

    def test_agenda_briefing_has_all_local_sections(self):
        reply, agenda = agenda_reply("test briefing")
        self.assertEqual(set(agenda), {"tasks", "reminders", "events"})
        self.assertIn("Tasks:", reply)
        self.assertIn("Reminders:", reply)
        self.assertIn("Events:", reply)

    def test_calendar_export_is_valid_ics_envelope(self):
        exported = calendar_ics()
        self.assertTrue(exported.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertIn("VERSION:2.0", exported)
        self.assertTrue(exported.endswith("END:VCALENDAR\r\n"))

    def test_workspace_scope_blocks_runtime_and_traversal(self):
        self.assertIsNotNone(workspace_target("SARA_SETUP_GUIDE.md"))
        self.assertIsNone(workspace_target("sara_data/activity.jsonl"))
        self.assertIsNone(workspace_target("../outside.txt"))
        self.assertIsNotNone(read_workspace_text("SARA_SETUP_GUIDE.md")[0])


if __name__ == "__main__":
    unittest.main()
