"""Pure regressions for short scheduling follow-ups across dashboard sessions."""

from concurrent.futures import ThreadPoolExecutor
import unittest

from sara_app.scheduling_dialogue import (
    MAX_FOLLOWUP_CHARS, MAX_ORIGINAL_CHARS, MAX_TITLE_CHARS,
    SchedulingDialogueStore,
)


class SchedulingDialogueTests(unittest.TestCase):
    SESSION = "dashboard_one"

    def setUp(self):
        self.now = [100.0]
        self.store = SchedulingDialogueStore(clock=lambda: self.now[0])

    def remember(self, original, phrase=None, title=None, kind="reminder"):
        span = (original.index(phrase), original.index(phrase) + len(phrase)) if phrase else None
        self.assertTrue(self.store.remember(self.SESSION, kind, original, title=title, span=span))

    def test_time_followup_appends_when_original_has_no_time_span(self):
        original = "remind me to drink water"
        self.remember(original)

        result = self.store.resume(self.SESSION, "subah 9 baje")

        self.assertEqual(result, {"kind": "reminder", "original": original, "title": None,
                                  "message": "remind me to drink water subah 9 baje"})
        self.assertIsNone(self.store.resume(self.SESSION, "10 am"))

    def test_numeric_replacement_preserves_old_day_inside_span(self):
        self.remember("remind me water kal 5", "kal 5")

        self.assertEqual(self.store.resume(self.SESSION, "9 am")["message"], "remind me water kal 9 am")

    def test_numeric_replacement_preserves_date_outside_narrow_span(self):
        self.remember("remind me water tomorrow at 5", "5")

        self.assertEqual(self.store.resume(self.SESSION, "9 am")["message"], "remind me water tomorrow at 9 am")

    def test_new_day_overrides_old_day_within_span(self):
        self.remember("remind me water aaj 5", "aaj 5")

        self.assertEqual(self.store.resume(self.SESSION, "tomorrow 9 am")["message"], "remind me water tomorrow 9 am")

    def test_new_day_overrides_adjacent_day_outside_narrow_span(self):
        self.remember("remind me water tomorrow at 5", "5")

        self.assertEqual(self.store.resume(self.SESSION, "today 9 am")["message"], "remind me water at today 9 am")

    def test_title_date_word_is_not_removed_when_separated_from_time(self):
        self.remember("schedule tomorrow planning meeting at 5", "5", title="tomorrow planning meeting", kind="event")

        result = self.store.resume(self.SESSION, "today 9 am")

        self.assertEqual(result["kind"], "event")
        self.assertEqual(result["title"], "tomorrow planning meeting")
        self.assertIn("tomorrow planning meeting", result["message"])

    def test_daypart_only_keeps_ambiguous_clock_and_day(self):
        self.remember("remind me water kal 5", "kal 5")

        self.assertEqual(self.store.resume(self.SESSION, "shaam")["message"], "remind me water kal 5 shaam")

    def test_new_daypart_replaces_old_period_without_losing_clock(self):
        self.remember("remind me water kal 5 am", "kal 5 am")

        self.assertEqual(self.store.resume(self.SESSION, "shaam")["message"], "remind me water kal 5 shaam")

    def test_day_only_keeps_existing_clock_period(self):
        self.remember("remind me water aaj 5 pm", "aaj 5 pm")

        self.assertEqual(self.store.resume(self.SESSION, "kal")["message"], "remind me water 5 pm kal")

    def test_compact_time_and_hindi_words_are_accepted(self):
        for followup in ("9baje", "5 pm", "शाम", "सुबह ९:३० बजे", "tomorrow morning 9", "after 10 minutes", "das minute baad", "दस मिनट बाद", "subah nau baje", "shaam paanch bajey", "after half an hour", "aadha ghanta baad", "आधे घंटे बाद", "in two days", "do din baad", "दो दिन बाद", "p.m."):
            with self.subTest(followup=followup):
                self.remember("remind me water")
                self.assertIsNotNone(self.store.resume(self.SESSION, followup))

    def test_word_hour_replaces_old_clock_preserving_day(self):
        self.remember("remind me water kal 5", "kal 5")

        self.assertEqual(self.store.resume(self.SESSION, "subah nau baje")["message"], "remind me water kal subah nau baje")

    def test_hindi_word_hour_replaces_old_clock_preserving_day(self):
        self.remember("याद दिलाओ पानी कल 5 बजे", "कल 5 बजे")

        self.assertEqual(self.store.resume(self.SESSION, "सुबह नौ बजे")["message"], "याद दिलाओ पानी कल सुबह नौ बजे")

    def test_unrelated_question_or_complete_command_clears_the_draft(self):
        for followup in ("open notepad", "what is the weather tomorrow", "remind me to call at 5 pm", "schedule a meeting tomorrow", "5 pm and open Chrome", "hello", "baje"):
            with self.subTest(followup=followup):
                self.remember("remind me water")
                self.assertIsNone(self.store.resume(self.SESSION, followup))
                self.assertIsNone(self.store.resume(self.SESSION, "9 am"))

    def test_two_sessions_never_share_a_draft(self):
        self.remember("remind me water")
        self.assertIsNone(self.store.resume("dashboard_two", "5 pm"))
        self.assertEqual(self.store.resume(self.SESSION, "9 am")["original"], "remind me water")

    def test_expiry_occurs_at_the_ttl_boundary(self):
        self.remember("remind me water")
        self.now[0] += 300

        self.assertIsNone(self.store.resume(self.SESSION, "9 am"))

    def test_draft_can_be_replaced_after_another_clarification(self):
        self.remember("remind me water kal 5", "kal 5")
        first = self.store.resume(self.SESSION, "9")
        self.assertEqual(first["message"], "remind me water kal 9")
        self.assertTrue(self.store.remember(self.SESSION, first["kind"], first["message"], span=(first["message"].index("kal"), len(first["message"]))))

        self.assertEqual(self.store.resume(self.SESSION, "shaam")["message"], "remind me water kal 9 shaam")

    def test_capacity_evicts_oldest_session_and_overwrite_refreshes_it(self):
        store = SchedulingDialogueStore(max_sessions=2, clock=lambda: self.now[0])
        store.remember("dashboard_one", "reminder", "remind water")
        store.remember("dashboard_two", "reminder", "remind milk")
        store.remember("dashboard_one", "event", "schedule team", title="team")
        store.remember("dashboard_three", "reminder", "remind walk")

        self.assertIsNone(store.resume("dashboard_two", "9 am"))
        self.assertEqual(store.resume("dashboard_one", "9 am")["kind"], "event")
        self.assertIsNotNone(store.resume("dashboard_three", "9 am"))

    def test_clear_is_session_scoped_and_idempotent(self):
        self.remember("remind me water")
        self.assertFalse(self.store.clear("dashboard_two"))
        self.assertTrue(self.store.clear(self.SESSION))
        self.assertFalse(self.store.clear(self.SESSION))
        self.assertIsNone(self.store.resume(self.SESSION, "5 pm"))

    def test_invalid_sessions_and_input_types_are_safe(self):
        for session in (None, "", "short", "with spaces", "x" * 81, [], 42):
            with self.subTest(session=session):
                self.assertFalse(self.store.remember(session, "event", "schedule team"))
                self.assertIsNone(self.store.resume(session, "5 pm"))
                self.assertFalse(self.store.clear(session))
        self.assertFalse(self.store.remember(self.SESSION, "unsupported", "request"))
        self.assertFalse(self.store.remember(self.SESSION, [], "request"))
        self.assertFalse(self.store.remember(self.SESSION, "event", None))
        self.remember("remind me water")
        self.assertIsNone(self.store.resume(self.SESSION, None))
        self.assertIsNone(self.store.resume(self.SESSION, "5 pm"))

    def test_length_limits_reject_unbounded_drafts_and_followups(self):
        self.assertFalse(self.store.remember(self.SESSION, "event", "x" * (MAX_ORIGINAL_CHARS + 1)))
        self.assertFalse(self.store.remember(self.SESSION, "event", "schedule meeting", title="x" * (MAX_TITLE_CHARS + 1)))
        self.remember("remind me water")
        self.assertIsNone(self.store.resume(self.SESSION, "9" * (MAX_FOLLOWUP_CHARS + 1)))

    def test_invalid_spans_fall_back_to_appending(self):
        for span in ((-1, 4), (10, 3), (0, 1000), (True, 4), "9 am"):
            with self.subTest(span=span):
                self.assertTrue(self.store.remember(self.SESSION, "reminder", "remind water", span=span))
                self.assertEqual(self.store.resume(self.SESSION, "5 pm")["message"], "remind water 5 pm")

    def test_parallel_dashboard_clarifications_remain_isolated(self):
        def conversation(index):
            session = f"dashboard_{index:03d}"
            original = f"remind water {index}"
            self.assertTrue(self.store.remember(session, "reminder", original))
            return self.store.resume(session, "5 pm")

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(conversation, range(24)))

        self.assertEqual([item["original"] for item in results], [f"remind water {index}" for index in range(24)])
        self.assertTrue(all(item["message"].endswith("5 pm") for item in results))


if __name__ == "__main__":
    unittest.main()
