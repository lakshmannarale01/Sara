"""Bounded image validation and local-model routing, without image/device access."""
import base64
import io
import json
import os
import threading
import unittest
from unittest.mock import patch

from sara_app import ai, vision


class JsonResponse:
    def __init__(self, value):
        self.value = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size=-1):
        return self.value if size < 0 else self.value[:size]


def image_attachment(size=(24, 16), source="upload", file_format="PNG"):
    output = io.BytesIO()
    vision.Image.new("RGB", size, "blue").save(output, format=file_format)
    mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[file_format]
    return {"source": source, "data_url": "data:" + mime + ";base64," + base64.b64encode(output.getvalue()).decode()}


class AttachmentValidationTests(unittest.TestCase):
    def test_empty_inputs_need_no_optional_decoder(self):
        with patch.object(vision, "Image", None):
            self.assertEqual(vision.validate_attachments(None), [])
            self.assertEqual(vision.validate_attachments([]), [])

    def test_missing_decoder_has_actionable_failure(self):
        with patch.object(vision, "Image", None):
            with self.assertRaisesRegex(ValueError, "Pillow"):
                vision.validate_attachments([{"data_url": "data:image/png;base64,AA=="}])

    def test_non_list_or_too_many_attachments_rejected(self):
        for value in ("image.png", {}, [None] * 5):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "four"):
                vision.validate_attachments(value)

    @unittest.skipIf(vision.Image is None, "Pillow required for real image decoding")
    def test_raster_formats_and_each_explicit_source_are_normalized(self):
        for file_format in ("PNG", "JPEG", "WEBP"):
            for source in ("upload", "screen", "camera"):
                with self.subTest(file_format=file_format, source=source):
                    normalized = vision.validate_attachments([image_attachment(source=source, file_format=file_format)])[0]
                    self.assertEqual((normalized["width"], normalized["height"]), (24, 16))
                    self.assertEqual(normalized["source"], source)
                    self.assertTrue(normalized["data_url"].startswith("data:image/jpeg;base64,"))
                    with vision.Image.open(io.BytesIO(base64.b64decode(normalized["base64"]))) as decoded:
                        self.assertEqual(decoded.format, "JPEG")

    @unittest.skipIf(vision.Image is None, "Pillow required for real image decoding")
    def test_remote_paths_svg_invalid_base64_and_unknown_sources_rejected(self):
        values = [
            {"data_url": "https://example.com/image.png"},
            {"data_url": "file:///C:/private.png"},
            {"data_url": "data:image/svg+xml;base64,PHN2Zz4="},
            {"data_url": "data:image/png;base64,not-base64"},
            {"data_url": "data:image/png;base64,AA=="},
            dict(image_attachment(), source="background-spy"),
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                vision.validate_attachments([value])

    @unittest.skipIf(vision.Image is None, "Pillow required for real image decoding")
    def test_spoofed_mime_and_truncated_image_rejected(self):
        attachment = image_attachment()
        with self.assertRaisesRegex(ValueError, "match"):
            vision.validate_attachments([dict(attachment, data_url=attachment["data_url"].replace("image/png", "image/jpeg"))])
        encoded = attachment["data_url"].split(",")[1]
        with self.assertRaises(ValueError):
            vision.validate_attachments([{"data_url": "data:image/png;base64," + base64.b64encode(base64.b64decode(encoded)[:45]).decode()}])

    @unittest.skipIf(vision.Image is None, "Pillow required for real image decoding")
    def test_dimensions_are_bounded_and_metadata_is_stripped(self):
        output = io.BytesIO()
        image = vision.Image.new("RGB", (2400, 1200), "blue")
        exif = image.getexif()
        exif[270] = "private metadata"
        image.save(output, format="JPEG", exif=exif)
        normalized = vision.validate_attachments([{"data_url": "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode()}])[0]
        self.assertEqual((normalized["width"], normalized["height"]), (1920, 960))
        with vision.Image.open(io.BytesIO(base64.b64decode(normalized["base64"]))) as decoded:
            self.assertFalse(decoded.getexif())

    @unittest.skipIf(vision.Image is None, "Pillow required for real image decoding")
    def test_encoded_and_total_limits_are_enforced(self):
        attachment = image_attachment()
        with patch.object(vision, "MAX_IMAGE_BYTES", 20):
            with self.assertRaisesRegex(ValueError, "10 MB"):
                vision.validate_attachments([attachment])
        raw_bytes = len(base64.b64decode(attachment["data_url"].split(",")[1]))
        with patch.object(vision, "MAX_IMAGE_BYTES", raw_bytes + 1):
            with self.assertRaisesRegex(ValueError, "10 MB"):
                vision.validate_attachments([attachment, attachment])

    def test_summary_contains_no_pixels_or_data_url(self):
        item = {"source": "screen", "width": 800, "height": 600, "base64": "private", "data_url": "private"}
        self.assertEqual(vision.attachment_summary([item]), [{"source": "screen", "width": 800, "height": 600}])


class VisionDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(vision, "Image", object()),
                        patch.object(vision, "OLLAMA_URL", "http://127.0.0.1:11434"),
                        patch.object(vision, "_status_cache", {"until": 0, "key": None, "value": None}),
                        patch.dict(os.environ, {}, clear=True)]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_discovery_verifies_capability_not_model_name(self):
        def metadata(path, payload=None, **_):
            if path == "/api/tags":
                return {"models": [{"name": "text-only-vision-name", "size": 1}, {"name": "actual-model", "size": 2}]}
            return {"capabilities": ["completion", "vision"] if payload["model"] == "actual-model" else ["completion"]}
        with patch.object(vision, "_json_request", side_effect=metadata) as request:
            status = vision.vision_status()
            again = vision.vision_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["model"], "actual-model")
        self.assertFalse(status["cloud_upload"])
        self.assertEqual(again, status)
        self.assertEqual(request.call_count, 3)

    def test_preferred_model_still_requires_actual_vision_capability(self):
        def metadata(path, payload=None, **_):
            if path == "/api/tags":
                return {"models": [{"name": "smaller", "size": 1}, {"name": "preferred:latest", "size": 5}]}
            return {"capabilities": ["vision"]}
        with patch.dict(os.environ, {"SARA_VISION_MODEL": "preferred"}), patch.object(vision, "_json_request", side_effect=metadata) as request:
            status = vision.vision_status()
        self.assertEqual(status["model"], "preferred:latest")
        self.assertEqual(request.call_args_list[1].args, ("/api/show", {"model": "preferred:latest"}))

    def test_text_only_and_unreachable_provider_explain_missing_capability(self):
        with patch.object(vision, "_json_request", return_value={"models": []}):
            status = vision.vision_status(force=True)
        self.assertFalse(status["available"])
        self.assertIn("llama3.2", status["reason"])
        with patch.object(vision, "_json_request", side_effect=TimeoutError):
            status = vision.vision_status(force=True)
        self.assertFalse(status["available"])
        self.assertIn("not reachable", status["reason"])

    def test_remote_ollama_is_not_contacted_for_images(self):
        with patch.object(vision, "OLLAMA_URL", "https://remote.example"), patch.object(vision, "_json_request") as request:
            status = vision.vision_status(force=True)
        self.assertFalse(status["available"])
        self.assertIn("stay local", status["reason"])
        request.assert_not_called()


class VisionAiRoutingTests(unittest.TestCase):
    def setUp(self):
        self.images = [{"source": "screen", "base64": "safe-test-bytes"}]
        patches = [patch.object(ai, "validate_attachments", return_value=self.images),
                   patch.object(ai, "log"), patch.object(ai, "console_trace"),
                   patch.object(ai, "read_memories", return_value=[]),
                   patch.object(ai, "read_conversations", return_value=[]),
                   patch.object(ai, "capability_snapshot", return_value={}),
                   patch.object(ai, "CONVERSATION_HISTORY", []),
                   patch.object(ai, "_ask_lock", threading.Lock()),
                   patch.object(ai, "_ollama_retry_at", 0.0)]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_image_with_greeting_is_not_ignored_and_never_falls_back_to_cloud(self):
        chunks = []
        with patch.object(ai, "vision_status", return_value={"available": True, "model": "local-eyes"}), patch.object(ai, "ask_ollama", return_value="I see a blue panel.") as ollama, patch.object(ai, "ask_openai") as cloud:
            reply, provider = ai.ask("Hello Sara", chunks.append, attachments=[{}])
        self.assertEqual(provider, "ollama-vision")
        self.assertEqual(reply, "I see a blue panel.")
        self.assertEqual(ollama.call_args.kwargs["vision_model"], "local-eyes")
        self.assertEqual(ollama.call_args.kwargs["attachments"], self.images)
        cloud.assert_not_called()
        self.assertNotIn("safe-test-bytes", json.dumps(ai.CONVERSATION_HISTORY))

    def test_missing_vision_is_honest_and_streams_one_actionable_reply(self):
        chunks = []
        with patch.object(ai, "vision_status", return_value={"available": False, "reason": "Install a local vision model."}), patch.object(ai, "ask_ollama") as ollama, patch.object(ai, "ask_openai") as cloud:
            reply, provider = ai.ask("What is this?", chunks.append, attachments=[{}])
        self.assertEqual(provider, "vision-unavailable")
        self.assertIn("could not inspect", reply)
        self.assertEqual(chunks, [reply])
        ollama.assert_not_called()
        cloud.assert_not_called()

    def test_vision_generation_failure_does_not_upload_to_cloud(self):
        chunks = []
        with patch.object(ai, "vision_status", return_value={"available": True, "model": "local-eyes"}), patch.object(ai, "ask_ollama", return_value=None), patch.object(ai, "ask_openai") as cloud:
            reply, provider = ai.ask("What is this?", chunks.append, attachments=[{}])
        self.assertEqual(provider, "vision-unavailable")
        self.assertIn("not sent to cloud", reply)
        self.assertEqual(chunks, [reply])
        cloud.assert_not_called()

    def test_ollama_payload_uses_base64_and_actual_selected_vision_model(self):
        with patch.object(ai.urllib.request, "urlopen", return_value=JsonResponse({"response": "A blue panel", "done": True})) as request:
            reply = ai.ask_ollama("Explain this screenshot", attachments=self.images, vision_model="local-eyes")
        self.assertEqual(reply, "A blue panel")
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(payload["model"], "local-eyes")
        self.assertEqual(payload["images"], ["safe-test-bytes"])
        self.assertIn("untrusted data", payload["system"])
        self.assertIn("snapshots", payload["system"])


if __name__ == "__main__":
    unittest.main()
