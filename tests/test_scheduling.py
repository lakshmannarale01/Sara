"""Natural-time parsing regressions use a fixed local clock and no app data."""
from datetime import datetime, timedelta, timezone
import unittest

from sara_app.scheduling import parse_schedule_time


class ScheduleParsingTests(unittest.TestCase):
    def setUp(self):
        self.reference = datetime(2026, 11, 13, 10, 15, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    def parse(self, text):
        return parse_schedule_time(text, self.reference)

    def assert_due(self, text, expected):
        result = self.parse(text)
        self.assertEqual(result.status, "ready", result)
        self.assertEqual(datetime.fromisoformat(result.due_at), datetime.fromisoformat(expected))
        return result

    def test_english_and_hinglish_relative_minutes(self):
        for text in ("remind me in 10 minutes", "10 minute baad pani yaad dilana", "१० मिनट बाद पानी याद दिलाना", "after ten minutes remind me"):
            with self.subTest(text=text):
                self.assert_due(text, "2026-11-13T04:55:00+00:00")

    def test_relative_hours_and_days(self):
        self.assert_due("remind me in 2 hours", "2026-11-13T06:45:00+00:00")
        self.assert_due("दो घंटे बाद याद दिलाओ", "2026-11-13T06:45:00+00:00")
        self.assert_due("in two days remind me", "2026-11-15T04:45:00+00:00")

    def test_fractional_relative_delay_is_not_partially_parsed(self):
        self.assert_due("in 1.5 hours", "2026-11-13T06:15:00+00:00")
        self.assert_due("1.5 hours baad", "2026-11-13T06:15:00+00:00")

    def test_half_hour_forms(self):
        for text in ("in half an hour", "aadhe ghante baad", "आधे घंटे बाद"):
            with self.subTest(text=text):
                self.assert_due(text, "2026-11-13T05:15:00+00:00")

    def test_relative_zero_and_giant_delays_are_invalid(self):
        for text in ("in 0 minutes", "0 मिनट बाद", "in -5 minutes", "in -0.5 hours", "in 999999999999999 hours", "in 366 days"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text).status, "invalid")

    def test_tomorrow_is_not_dropped_from_english_clock(self):
        self.assert_due("remind me tomorrow at 5 pm", "2026-11-14T11:30:00+00:00")
        self.assert_due("at 5 pm tomorrow", "2026-11-14T11:30:00+00:00")

    def test_hindi_day_periods_and_devanagari_digits(self):
        self.assert_due("कल सुबह ९ बजे दवाई याद दिलाओ", "2026-11-14T03:30:00+00:00")
        self.assert_due("kal shaam 5 baje meeting", "2026-11-14T11:30:00+00:00")
        self.assert_due("aaj dopahar 2 baje", "2026-11-13T08:30:00+00:00")
        self.assert_due("aaj raat 9 baje", "2026-11-13T15:30:00+00:00")

    def test_spoken_hour_words_preserve_their_raw_span(self):
        for text in ("kal shaam paanch baje", "कल शाम पांच बजे", "tomorrow at five pm"):
            with self.subTest(text=text):
                result = self.assert_due(text, "2026-11-14T11:30:00+00:00")
                self.assertEqual(text[slice(*result.span)].strip(), text)

    def test_clock_postfix_day_period(self):
        self.assert_due("tomorrow at 5 in the evening", "2026-11-14T11:30:00+00:00")

    def test_24_hour_clock_is_clear(self):
        self.assert_due("at 17:30 call", "2026-11-13T12:00:00+00:00")
        self.assert_due("कल १७:३० बजे", "2026-11-14T12:00:00+00:00")
        self.assert_due("at 17", "2026-11-13T11:30:00+00:00")

    def test_bare_clock_without_am_pm_requests_clarification(self):
        for text in ("remind me at 5", "kal 5 baje", "कल ५ बजे", "at 5:30"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text).status, "clarify")
                self.assertIsNone(self.parse(text).due_at)

    def test_day_without_clock_requests_time(self):
        for text in ("remind me tomorrow", "kal yaad dilana", "कल याद दिलाओ", "on 2026-11-14"):
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result.status, "clarify")
                self.assertIsNotNone(result.span)

    def test_explicit_today_in_past_is_not_moved_to_tomorrow(self):
        result = self.parse("today at 9 am")
        self.assertEqual(result.status, "invalid")
        self.assertIn("passed", result.message)
        self.assertIsNone(result.due_at)

    def test_clock_without_day_uses_next_occurrence(self):
        self.assert_due("at 9 am", "2026-11-14T03:30:00+00:00")

    def test_midnight_and_noon_am_pm(self):
        self.assert_due("tomorrow at 12 am", "2026-11-13T18:30:00+00:00")
        self.assert_due("today at 12 pm", "2026-11-13T06:30:00+00:00")

    def test_impossible_clock_values_do_not_raise(self):
        for text in ("at 25:00", "at 10:99", "at -5 pm", "at -5", "at 0 pm", "at 13 pm", "at 999999999999999999:00", "at 17:300"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text).status, "invalid")

    def test_conflicting_period_and_am_pm_is_not_guessed(self):
        self.assertEqual(self.parse("shaam 5 am").status, "clarify")
        self.assertEqual(self.parse("subah 17:00").status, "clarify")
        self.assertEqual(self.parse("raat 2 baje").status, "clarify")

    def test_multiple_clocks_and_relative_absolute_conflicts(self):
        for text in ("at 5 pm or 6 pm", "today tomorrow at 5 pm", "in 10 minutes at 5 pm", "in 1 hour and 20 minutes"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text).status, "clarify")

    def test_content_numbers_are_not_clock_times(self):
        for text in ("remind me to read chapter 5", "call 9876543210", "project 17 is ready", "version 3.14 release", "remind me at home"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text).status, "missing")

    def test_unframed_duration_requests_a_schedule_instead_of_guessing(self):
        self.assertEqual(self.parse("a 10 minute meeting").status, "clarify")
        self.assertEqual(self.parse("at 17:30:45").status, "clarify")

    def test_content_number_does_not_replace_real_relative_schedule(self):
        self.assert_due("remind me to read chapter 5 in 10 minutes", "2026-11-13T04:55:00+00:00")

    def test_raw_span_preserves_original_hindi_digits_and_day(self):
        text = "schedule team sync कल शाम ५ बजे"
        result = self.assert_due(text, "2026-11-14T11:30:00+00:00")
        self.assertEqual(text[slice(*result.span)].strip(), "कल शाम ५ बजे")

    def test_raw_span_includes_day_prefix_and_on(self):
        text = "schedule chapter 5 on tomorrow at 5 pm"
        result = self.assert_due(text, "2026-11-14T11:30:00+00:00")
        self.assertEqual(text[slice(*result.span)].strip(), "on tomorrow at 5 pm")

    def test_iso_calendar_dates(self):
        self.assert_due("on 2026-11-16 at 5 pm", "2026-11-16T11:30:00+00:00")
        self.assertEqual(self.parse("on 2026-02-30 at 5 pm").status, "invalid")
        self.assertEqual(self.parse("on 2026-11-12 at 5 pm").status, "invalid")

    def test_aware_reference_required_for_deterministic_timezone_handling(self):
        result = parse_schedule_time("in 10 minutes", datetime(2026, 11, 13, 10, 15))
        self.assertEqual(result.status, "invalid")

    def test_oversized_and_nontext_input_is_safe(self):
        self.assertEqual(self.parse("x" * 10001).status, "invalid")
        self.assertEqual(self.parse(None).status, "invalid")


if __name__ == "__main__":
    unittest.main()
