"""Bounded Windows audio controls without operating a real speaker or player."""
import json
import subprocess
import unittest
from unittest.mock import Mock, patch

from sara_app import system_controls as controls


class MediaPayloadTests(unittest.TestCase):
    def test_only_supported_canonical_payloads_are_accepted(self):
        for command in controls.COMMANDS - {"set_volume"}:
            self.assertEqual(controls.normalize_media_payload({"command": command}), {"command": command})
        for level in (0, 30, 100):
            self.assertEqual(controls.normalize_media_payload({"command": "set_volume", "level": level}), {"command": "set_volume", "level": level})

    def test_shapes_unknown_commands_and_extra_fields_are_rejected(self):
        for value in (None, [], "mute", {}, {"command": {}}, {"command": []}, {"command": True},
                      {"command": "shell"}, {"command": "mute", "keys": ["win", "r"]},
                      {"command": "mute", "level": None}, {"command": "mute", "level": 0}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                controls.normalize_media_payload(value)

    def test_volume_must_be_bounded_integer_not_boolean_or_numeric_text(self):
        for level in (None, True, False, -1, 101, "30", 30.0, float("nan"), float("inf"), {}, []):
            with self.subTest(level=level), self.assertRaises(ValueError):
                controls.normalize_media_payload({"command": "set_volume", "level": level})


class MediaExecutionTests(unittest.TestCase):
    def setUp(self):
        self.request = self.patched("_request")
        self.stopped = self.patched("is_stopped", return_value=False)
        self.log = self.patched("log")

    def patched(self, name, **kwargs):
        patcher = patch.object(controls, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_no_confirmation_never_invokes_windows(self):
        result = controls.execute_media_control("set_volume", 30)
        self.assertTrue(result["requires_confirmation"])
        self.request.assert_not_called()
        self.log.assert_not_called()

    def test_paused_actions_stop_even_a_confirmed_media_request(self):
        self.stopped.return_value = True
        result = controls.execute_media_control("mute", confirmed=True)
        self.assertTrue(result["stopped"])
        self.assertFalse(result["ok"])
        self.request.assert_not_called()

    def test_stop_rechecked_at_the_operating_system_boundary(self):
        self.stopped.side_effect = [False, True]
        result = controls.execute_media_control("play_pause", confirmed=True)
        self.assertTrue(result["stopped"])
        self.request.assert_not_called()

    def test_set_volume_returns_actual_readback_including_existing_mute(self):
        self.request.return_value = {"available": True, "volume": 30, "muted": True, "readback_verified": True, "changed": True}
        result = controls.execute_media_control("set_volume", 30, confirmed=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["volume"], 30)
        self.assertTrue(result["muted"])
        self.assertTrue(result["readback_verified"])
        self.assertIn("muted", result["result"])
        self.request.assert_called_once_with({"command": "set_volume", "level": 30})

    def test_unexpected_readback_is_an_honest_partial_failure(self):
        self.request.return_value = {"available": True, "volume": 65, "muted": False, "readback_verified": True, "changed": True}
        result = controls.execute_media_control("set_volume", 30, confirmed=True)
        self.assertFalse(result["ok"])
        self.assertFalse(result["readback_verified"])
        self.assertTrue(result["changed"])
        self.assertIn("not verified", result["result"])

    def test_mute_and_unmute_must_match_actual_readback(self):
        for command, muted in (("mute", True), ("unmute", False)):
            with self.subTest(command=command):
                self.request.return_value = {"available": True, "volume": 35, "muted": muted, "readback_verified": True}
                self.assertTrue(controls.execute_media_control(command, confirmed=True)["ok"])
                self.request.return_value["muted"] = not muted
                self.assertFalse(controls.execute_media_control(command, confirmed=True)["ok"])

    def test_relative_volume_commands_are_fixed_operations_not_arbitrary_values(self):
        self.request.return_value = {"available": True, "volume": 100, "muted": False, "readback_verified": True}
        self.assertTrue(controls.execute_media_control("volume_up", confirmed=True)["ok"])
        self.request.assert_called_once_with({"command": "volume_up"})
        with self.assertRaises(ValueError):
            controls.execute_media_control("volume_up", 1000, confirmed=True)

    def test_transport_reports_dispatch_without_claiming_playback(self):
        self.request.return_value = {"available": True, "key_sent": True, "playback_verified": False}
        for command in controls.TRANSPORT:
            with self.subTest(command=command):
                result = controls.execute_media_control(command, confirmed=True)
                self.assertTrue(result["ok"])
                self.assertTrue(result["key_sent"])
                self.assertFalse(result["playback_verified"])
                self.assertIn("not been verified", result["result"])
        self.assertEqual(self.request.call_count, len(controls.TRANSPORT))

    def test_missing_transport_dispatch_confirmation_is_not_success(self):
        self.request.return_value = {"available": True, "key_sent": False}
        with self.assertRaisesRegex(RuntimeError, "dispatch"):
            controls.execute_media_control("next_track", confirmed=True)
        self.log.assert_not_called()

    def test_invalid_device_readback_is_never_reported_as_success(self):
        for response in ({}, {"available": True, "volume": True, "muted": False},
                         {"available": True, "volume": 40, "muted": "false"},
                         {"available": True, "volume": 101, "muted": False}):
            with self.subTest(response=response):
                self.request.return_value = response
                with self.assertRaises(RuntimeError): controls.execute_media_control("mute", confirmed=True)

    def test_readonly_status_has_no_confirmation_or_stop_dependency(self):
        self.stopped.return_value = True
        self.request.return_value = {"available": True, "volume": 42, "muted": False}
        self.assertEqual(controls.read_audio_status(), {"available": True, "volume": 42, "muted": False, "device": "default multimedia output"})
        self.request.assert_called_once_with({"command": "read"})
        self.stopped.assert_not_called()
        self.log.assert_not_called()

    def test_device_failure_returns_unavailable_status_without_invented_state(self):
        for error in (RuntimeError("No audio device"), OSError("missing"), subprocess.TimeoutExpired("powershell", 12)):
            with self.subTest(error=error):
                self.request.side_effect = error
                result = controls.read_audio_status()
                self.assertFalse(result["available"])
                self.assertIsNone(result["volume"])
                self.assertIsNone(result["muted"])


class MediaIntentTests(unittest.TestCase):
    def test_explicit_english_hinglish_and_hindi_controls(self):
        cases = {
            "volume 30 percent karo": ("set_volume", 30), "Sara, set volume to 0%": ("set_volume", 0),
            "speaker volume 100 percent": ("set_volume", 100), "आवाज़ 25 प्रतिशत करो": ("set_volume", 25),
            "mute karo": ("mute", None), "unmute karo": ("unmute", None), "सारा म्यूट करो": ("mute", None),
            "awaz badhao": ("volume_up", None), "volume down": ("volume_down", None),
            "awaz kam karo": ("volume_down", None), "आवाज़ कम करो": ("volume_down", None),
            "play pause": ("play_pause", None), "song pause karo": ("play_pause", None),
            "resume music": ("play_pause", None), "next song": ("next_track", None),
            "previous song": ("previous_track", None), "अगला गाना": ("next_track", None),
            "stop music": ("stop", None), "gaana band karo": ("stop", None),
        }
        for text, (command, level) in cases.items():
            with self.subTest(text=text):
                proposal = controls.plan_media_control(text)
                self.assertIsNotNone(proposal)
                self.assertEqual(proposal["action"]["type"], "media_control")
                self.assertEqual(proposal["action"]["command"], command)
                self.assertEqual(proposal["action"].get("level"), level)
                self.assertTrue(proposal["requires_confirmation"])

    def test_negation_questions_unrelated_prose_and_youtube_titles_are_not_actions(self):
        for text in (None, "", "please don't mute", "do not unmute", "volume 30 mat karo", "आवाज़ कम मत करो",
                     "how to mute audio", "can you mute?", "why is volume low", "volume 101 percent", "volume -1",
                     "Explain the phrase next song", "play Arijit Singh on youtube", "play best song on youtube",
                     "play next song by someone on youtube", 'write "mute karo" in Notepad', "mute; delete file",
                     "next song and send WhatsApp", "open calculator", "stop SARA"):
            with self.subTest(text=text): self.assertIsNone(controls.plan_media_control(text))


class MediaProcessBoundaryTests(unittest.TestCase):
    def test_fixed_script_receives_json_data_without_shell(self):
        result = Mock(returncode=0, stdout=json.dumps({"available": True, "volume": 30, "muted": False}))
        with patch.object(controls.os, "name", "nt"), patch.object(controls.subprocess, "run", return_value=result) as run:
            response = controls._request({"command": "read"})
        self.assertEqual(response["volume"], 30)
        args, kwargs = run.call_args
        self.assertIn(str(controls.SCRIPT), args[0])
        self.assertEqual(json.loads(kwargs["input"]), {"command": "read"})
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["timeout"], 12)

    def test_engine_failure_and_malformed_json_have_generic_errors(self):
        for result in (Mock(returncode=1, stdout="", stderr="private details"), Mock(returncode=0, stdout="[]"), Mock(returncode=0, stdout="bad json")):
            with self.subTest(result=result), patch.object(controls.os, "name", "nt"), patch.object(controls.subprocess, "run", return_value=result):
                with self.assertRaises(RuntimeError) as error: controls._request({"command": "read"})
                self.assertNotIn("private details", str(error.exception))


if __name__ == "__main__":
    unittest.main()
