"""Trusted mode remains a narrow persisted grant, not unrestricted execution."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sara_app import browser_control, config, policy, tools


class TrustedActionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        self.patch = patch.object(config, "DATA_DIR", self.directory)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(policy.set_stopped, False)
        policy.set_stopped(False)

    def test_default_review_and_persisted_round_trip(self):
        self.assertEqual(policy.access_mode(), "review")
        self.assertFalse(policy.inspect_action("open_app", payload={"app": "notepad"})["allowed"])
        policy.set_access_mode("trusted")
        self.assertEqual(policy.access_mode(), "trusted")
        self.assertTrue(policy.inspect_action("open_app", payload={"app": "notepad"})["automatic"])
        policy.set_access_mode("review")
        self.assertEqual(policy.access_mode(), "review")
        self.assertFalse(policy.inspect_action("youtube_play", payload={"query": "music"})["allowed"])

    def test_missing_malformed_or_unknown_mode_fails_closed_and_preserves_bytes(self):
        target = self.directory / "access_policy.json"
        for raw in (b'not-json', b'[{"mode":"full"}]', b'[{"mode":"trusted"},{"mode":"review"}]'):
            target.write_bytes(raw)
            self.assertEqual(policy.access_mode(), "review")
        original = b'\xffbroken'
        target.write_bytes(original)
        policy.set_access_mode("trusted")
        backups = list(self.directory.glob("access_policy.json.recovery-*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)

    def test_invalid_mode_does_not_replace_preference(self):
        policy.set_access_mode("review")
        for invalid in (None, True, [], {}, "full", "admin"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                policy.set_access_mode(invalid)
        self.assertEqual(policy.access_mode(), "review")

    def test_trusted_routine_payloads_and_emergency_stop(self):
        policy.set_access_mode("trusted")
        for action, payload in (
            ("open_app", {"app": "notepad"}),
            ("open_app", {"app": "calculator"}),
            ("youtube_play", {"query": "Arijit Singh"}),
            ("open_browser_url", {"url": "https://www.youtube.com"}),
            ("browser_open", {"url": "https://www.youtube.com/results?search_query=Hindi+music"}),
            ("open_browser_url", {"url": "https://www.google.com/search?q=Python"}),
            ("open_browser_url", {"url": "https://en.wikipedia.org/wiki/Python_(programming_language)"}),
        ):
            with self.subTest(action=action, payload=payload):
                self.assertTrue(policy.inspect_action(action, payload=payload)["allowed"])
        policy.set_stopped(True)
        for confirmed in (False, True):
            verdict = policy.inspect_action("youtube_play", confirmed, {"query": "Hindi music"})
            self.assertFalse(verdict["allowed"])
            self.assertTrue(verdict["stopped"])

    def test_trust_does_not_authorize_writes_sends_input_unknown_or_custom_apps(self):
        policy.set_access_mode("trusted")
        for action in ("write_file", "delete_file", "type_text", "hotkey", "click_point", "browser_click_text", "browser_fill", "save_memory", "approve_memory", "update_memory", "delete_memory", "whatsapp_send", "email_draft", "unknown"):
            with self.subTest(action=action):
                self.assertFalse(policy.inspect_action(action, payload={"text": "hello"})["allowed"])
        for payload in ({"app": "my-custom-app"}, {"app": "notepad", "executable": "C:\\malicious.exe"}):
            self.assertFalse(policy.inspect_action("open_app", payload=payload)["allowed"])
        self.assertFalse(policy.inspect_action("open_app")["allowed"])

    def test_automatic_browser_scope_cannot_be_extended_by_url_tricks(self):
        policy.set_access_mode("trusted")
        rejected = ["http://www.youtube.com", "https://youtube.com.evil.invalid/", "https://user:secret@www.youtube.com/", "https://www.youtube.com:8080/", "javascript:alert(1)", "file:///C:/secret", "https://example.com", "https://www.youtube.com/logout", "https://www.youtube.com/results?search_query=x&next=https://evil.invalid", "https://www.google.com/search?q=x#other", "https://en.wikipedia.org/wiki/Special:UserLogout", "https://en.wikipedia.org/wiki/Special%3AUserLogout", "https://www.youtube.com/\n"]
        for url in rejected:
            with self.subTest(url=url):
                self.assertFalse(policy.inspect_action("open_browser_url", payload={"url": url})["allowed"])
        for query in ("", "x" * 201, "hello\n", None):
            self.assertFalse(policy.inspect_action("youtube_play", payload={"query": query})["allowed"])

    def test_dispatch_is_explicit_and_rechecks_revoked_trust_or_stop(self):
        policy.set_access_mode("trusted")
        with patch.object(tools, "open_app", return_value={"ok": True}) as app, \
             patch.object(tools, "open_browser_url", return_value={"ok": True}) as browser, \
             patch.object(browser_control, "open_page", return_value={"ok": True}) as controlled, \
             patch.object(browser_control, "play_youtube", return_value={"ok": True, "playback_verified": False}) as video:
            tools.execute_routine_action({"type": "open_app", "app": "notepad"})
            tools.execute_routine_action({"type": "open_browser_url", "url": "https://www.youtube.com"})
            tools.execute_routine_action({"type": "browser_open", "url": "https://www.youtube.com"})
            result = tools.execute_routine_action({"type": "youtube_play", "query": "Hindi songs"})
            self.assertFalse(result["playback_verified"])
            app.assert_called_once_with("notepad", confirmed=True, executable=None)
            browser.assert_called_once_with("https://www.youtube.com", confirmed=True)
            controlled.assert_called_once_with("https://www.youtube.com", confirmed=True)
            video.assert_called_once_with("Hindi songs", confirmed=True)
            for action in ({"type": "whatsapp_send", "phone": "919876543210", "text": "hello"}, {"type": "open_app", "app": "unregistered"}):
                with self.assertRaises(ValueError):
                    tools.execute_routine_action(action)
            policy.set_access_mode("review")
            with self.assertRaisesRegex(ValueError, "review"):
                tools.execute_routine_action({"type": "youtube_play", "query": "Hindi songs"})
            policy.set_access_mode("trusted")
            policy.set_stopped(True)
            with self.assertRaisesRegex(ValueError, "stopped"):
                tools.execute_routine_action({"type": "youtube_play", "query": "Hindi songs"})
            video.assert_called_once()


if __name__ == "__main__":
    unittest.main()
