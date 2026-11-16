"""Optional snapshot check-ins must never own foreground chat or retain images."""
import json
import threading
import unittest
from unittest.mock import patch

from sara_app import ai


class VisualCheckInTests(unittest.TestCase):
    def setUp(self):
        self.images = [{"source": "screen", "base64": "ephemeral-image"}]
        self.foreground = threading.Lock()
        self.background = threading.Lock()
        patches = [patch.object(ai, "_ask_lock", self.foreground),
                   patch.object(ai, "_visual_check_in_lock", self.background),
                   patch.object(ai, "CONVERSATION_HISTORY", [("user", "existing conversation")]),
                   patch.object(ai, "validate_attachments", return_value=self.images),
                   patch.object(ai, "vision_status", return_value={"available": True, "model": "local-vision"}),
                   patch.object(ai, "ask_openai", side_effect=AssertionError("No cloud upload"))]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_foreground_busy_skips_without_model_call(self):
        self.foreground.acquire()
        with patch.object(ai, "ask_ollama") as request:
            self.assertEqual(ai.ask_visual_check_in([{}]), ("", "check-in-skipped"))
        request.assert_not_called()

    def test_overlapping_background_check_in_skips(self):
        self.background.acquire()
        with patch.object(ai, "ask_ollama") as request:
            self.assertEqual(ai.ask_visual_check_in([{}]), ("", "check-in-skipped"))
        request.assert_not_called()

    def test_visible_result_does_not_hold_foreground_lock_or_append_history(self):
        before = list(ai.CONVERSATION_HISTORY)
        def generate(*args, **kwargs):
            self.assertTrue(self.foreground.acquire(blocking=False), "check-in owns foreground lock")
            self.foreground.release()
            self.assertTrue(kwargs["snapshot_only"])
            self.assertEqual(kwargs["attachments"], self.images)
            self.assertEqual(kwargs["vision_model"], "local-vision")
            return "A settings panel is visible. Want help with it?"
        with patch.object(ai, "ask_ollama", side_effect=generate):
            reply, provider = ai.ask_visual_check_in([{}])
        self.assertIn("settings panel", reply)
        self.assertEqual(provider, "ollama-vision")
        self.assertEqual(ai.CONVERSATION_HISTORY, before)
        self.assertFalse(self.background.locked())

    def test_only_one_shared_view_is_accepted(self):
        for images in ([], [{"source": "upload"}], self.images * 2):
            with self.subTest(images=images), patch.object(ai, "validate_attachments", return_value=images), self.assertRaisesRegex(ValueError, "one explicitly shared"):
                ai.ask_visual_check_in([{}])
            self.assertFalse(self.background.locked())

    def test_unavailable_or_failed_model_does_not_use_cloud_or_fabricate_reply(self):
        with patch.object(ai, "vision_status", return_value={"available": False}), patch.object(ai, "ask_ollama") as request:
            self.assertEqual(ai.ask_visual_check_in([{}]), ("", "vision-unavailable"))
        request.assert_not_called()
        with patch.object(ai, "ask_ollama", return_value=None):
            self.assertEqual(ai.ask_visual_check_in([{}]), ("", "vision-unavailable"))

    def test_exception_releases_background_lock(self):
        with patch.object(ai, "ask_ollama", side_effect=RuntimeError("provider stopped")), self.assertRaises(RuntimeError):
            ai.ask_visual_check_in([{}])
        self.assertFalse(self.background.locked())

    def test_foreground_started_during_model_discovery_takes_priority(self):
        def status():
            self.foreground.acquire()
            return {"available": True, "model": "local-vision"}
        with patch.object(ai, "vision_status", side_effect=status), patch.object(ai, "ask_ollama") as request:
            self.assertEqual(ai.ask_visual_check_in([{}]), ("", "check-in-skipped"))
        request.assert_not_called()
        self.assertFalse(self.background.locked())

    def test_snapshot_payload_omits_conversation_and_approved_memories(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self): return b'{"response":"A panel is visible.","done":true}'
        with patch.object(ai, "build_instructions", side_effect=AssertionError("No personal context for a periodic snapshot")), patch.object(ai, "conversation_context", side_effect=AssertionError("No chat history for a periodic snapshot")), patch.object(ai.urllib.request, "urlopen", return_value=Response()) as request, patch.object(ai, "log"), patch.object(ai, "console_trace"):
            reply = ai.ask_ollama("Observe this shared view.", attachments=self.images, vision_model="local-vision", snapshot_only=True)
        self.assertEqual(reply, "A panel is visible.")
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(payload["prompt"], "Observe this shared view.")
        self.assertEqual(payload["options"]["num_predict"], 64)
        self.assertEqual(payload["options"]["temperature"], .2)
        self.assertIn("untrusted data", payload["system"])
        self.assertIn("never claim to execute", payload["system"])
        self.assertIn("Devanagari", payload["system"])


if __name__ == "__main__":
    unittest.main()
