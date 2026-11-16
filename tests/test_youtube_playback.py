"""Playback evidence must distinguish search, video opened and actual player state."""
import unittest
from unittest.mock import MagicMock, patch

from sara_app import browser_control
from sara_app.intents import action_payload, plan_youtube


class YoutubeIntentTests(unittest.TestCase):
    def test_english_hinglish_and_hindi_requests_have_real_playback_route(self):
        for message in ("play Arijit Singh songs on youtube", "ek song play karo best on you tube", "Arijit Singh ka gaana chalao", "YouTube पर गाना चलाओ"):
            with self.subTest(message=message):
                plan = plan_youtube(message)
                self.assertEqual(plan["action"]["type"], "youtube_play")
                self.assertTrue(plan["action"]["query"])
                self.assertEqual(action_payload(plan["action"]), {"query": plan["action"]["query"]})
        self.assertEqual(plan_youtube("ek song play karo best on you tube")["action"]["query"], "best Hindi songs")
        self.assertEqual(plan_youtube("यूट्यूब पर गाना चलाओ")["action"]["query"], "best Hindi songs")
        self.assertEqual(plan_youtube("play Shape of You on YouTube")["action"]["query"], "Shape of You")

    def test_questions_and_stop_do_not_start_music(self):
        for message in ("how do I play songs on youtube", "youtube open karo", "do not play music", "song band karo", "explain youtube", "don't play any song"):
            with self.subTest(message=message):
                self.assertIsNone(plan_youtube(message))


class YoutubePlaybackTests(unittest.TestCase):
    def setUp(self):
        self.page = MagicMock()
        self.link = MagicMock()
        self.video = MagicMock()
        self.link.get_attribute.side_effect = lambda name, **kwargs: "/watch?v=abc123&other=x" if name == "href" else "A music video"
        self.page.locator.side_effect = lambda selector: MagicMock(first=self.video if selector == "video" else self.link)
        for name, value in (("_page_for_browser", self.page), ("_navigate", None), ("log", None)):
            patcher = patch.object(browser_control, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_unconfirmed_playback_never_submits_work(self):
        with patch.object(browser_control, "_run_browser") as work:
            self.assertTrue(browser_control.play_youtube("Hindi music")["requires_confirmation"])
            work.assert_not_called()

    def test_playback_is_verified_only_for_audible_non_ad_player(self):
        for player, verified in (({"playing": True, "audible": True, "ad": False}, True), ({"playing": True, "audible": False, "ad": False}, False), ({"playing": False, "audible": True, "ad": False}, False), ({"playing": True, "audible": True, "ad": True}, False)):
            with self.subTest(player=player):
                self.video.evaluate.return_value = player
                result = browser_control._play_youtube("Hindi music")
                self.assertEqual(result["playback_verified"], verified)
                self.assertTrue(result["video_opened"])
                self.assertEqual(result["url"], "https://www.youtube.com/watch?v=abc123")

    def test_missing_search_result_does_not_claim_playback(self):
        self.link.get_attribute.side_effect = RuntimeError("consent screen")
        result = browser_control._play_youtube("Hindi music")
        self.assertFalse(result["playback_verified"])
        self.assertTrue(result["search_opened"])
        self.video.evaluate.assert_not_called()

    def test_external_result_link_is_never_followed(self):
        self.link.get_attribute.side_effect = lambda name, **kwargs: "https://evil.invalid/watch?v=abc" if name == "href" else "Bad result"
        result = browser_control._play_youtube("Hindi music")
        self.assertFalse(result["playback_verified"])
        self.assertTrue(result["search_opened"])
        self.video.evaluate.assert_not_called()

    def test_failed_autoplay_is_reported_as_opened_only(self):
        self.video.evaluate.side_effect = RuntimeError("autoplay blocked")
        result = browser_control._play_youtube("Hindi music")
        self.assertFalse(result["playback_verified"])
        self.assertIn("Playback could not be verified", result["result"])


if __name__ == "__main__":
    unittest.main()
