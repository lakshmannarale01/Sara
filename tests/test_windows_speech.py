"""Validate the local speech boundary without invoking voices or audio hardware."""
import base64
import subprocess
import unittest
from unittest.mock import patch

from sara_app import windows_speech


def wav():
    return b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + bytes(32)


class WindowsSpeechTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("_cached", None), ("_checked", 0.0)):
            patcher = patch.object(windows_speech, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_installed_voice_inventory_filters_invalid_entries_and_caches(self):
        voice = {"id": "kalpana", "name": "Microsoft Kalpana", "lang": "hi-IN"}
        with patch.object(windows_speech, "_request", return_value={"voices": [voice, {}, None, {"id": "bad"}]}) as request:
            result = windows_speech.voice_status()
            self.assertTrue(result["available"])
            self.assertEqual(result["voices"], [voice])
            windows_speech.voice_status()
            request.assert_called_once_with({"operation": "voices"}, timeout=10)
            windows_speech.voice_status(force=True)
            self.assertEqual(request.call_count, 2)

    def test_inventory_engine_failure_leaves_browser_fallback_available(self):
        for error in (RuntimeError("engine failed"), OSError("missing"), subprocess.TimeoutExpired("speech", 10)):
            with self.subTest(error=error), patch.object(windows_speech, "_request", side_effect=error):
                result = windows_speech.voice_status(force=True)
                self.assertFalse(result["available"])
                self.assertEqual(result["voices"], [])
                self.assertIn("browser", result["reason"])

    def test_synthesis_preserves_hindi_text_voice_and_speed_as_data(self):
        text = 'नमस्ते। OpenAI के साथ बात करें। "$() `"'
        response = {"audio": base64.b64encode(wav()).decode(), "voice": "Microsoft Kalpana", "lang": "hi-IN"}
        with patch.object(windows_speech, "_request", return_value=response) as request:
            audio, voice, lang = windows_speech.synthesize(text, "kalpana", "hi-IN", 1.15)
            self.assertEqual(audio, wav())
            self.assertEqual((voice, lang), ("Microsoft Kalpana", "hi-IN"))
            request.assert_called_once_with({"operation": "synthesize", "text": text, "voice": "kalpana", "lang": "hi-IN", "rate": 1.15})

    def test_invalid_text_or_voice_never_starts_engine(self):
        with patch.object(windows_speech, "_request") as request:
            for text in (None, "", "  ", "x" * 1201):
                with self.subTest(text=text), self.assertRaises(ValueError):
                    windows_speech.synthesize(text)
            for voice, lang in ((None, ""), ("x" * 1001, ""), ("kalpana", "unknown")):
                with self.subTest(voice=voice, lang=lang), self.assertRaises(ValueError):
                    windows_speech.synthesize("hello", voice, lang)
            request.assert_not_called()

    def test_invalid_speed_is_rejected_before_engine_invocation(self):
        with patch.object(windows_speech, "_request") as request:
            for speed in (None, "fast", .84, 1.41, float("nan"), float("inf")):
                with self.subTest(speed=speed), self.assertRaises(ValueError):
                    windows_speech.synthesize("hello", rate=speed)
            request.assert_not_called()

    def test_invalid_base64_or_non_wav_response_is_never_played(self):
        for response in ({}, {"audio": "?not-base64?"}, {"audio": base64.b64encode(b"not wav" * 12).decode()}, {"audio": None}):
            with self.subTest(response=response), patch.object(windows_speech, "_request", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "audio|WAV"):
                    windows_speech.synthesize("नमस्ते।")


if __name__ == "__main__":
    unittest.main()
