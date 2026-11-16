"""HTTP-handler contracts for ephemeral images and native speech, without sockets."""
import base64
import io
import json
import unittest
from unittest.mock import Mock, patch

from sara_app import server, vision, windows_speech


class VisionServerTests(unittest.TestCase):
    def setUp(self):
        self.append = self.patched(server, "append_conversation")
        self.log = self.patched(server, "log")
        self.ask = self.patched(server, "ask", return_value=("A green test image.", "ollama-vision"))
        self.patched(server, "read_memories", return_value=[])
        self.patched(server, "request_performance", return_value={"first_token_ms": 10})
        self.patched(server.action_state, "context", return_value={"pending": None, "recent_outcomes": []})

    def patched(self, target, name, **kwargs):
        patcher = patch.object(target, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    @staticmethod
    def handler(path, data=None, headers=None):
        handler = object.__new__(server.Handler)
        raw = json.dumps(data if data is not None else {}).encode()
        handler.path = path
        handler.headers = {"Content-Length": str(len(raw)), "Accept": "application/json", **(headers or {})}
        handler.rfile, handler.wfile = io.BytesIO(raw), io.BytesIO()
        handler.send_response, handler.send_header, handler.end_headers = Mock(), Mock(), Mock()
        handler.trace = Mock()
        return handler

    def post(self, data, path="/api/chat", headers=None):
        handler = self.handler(path, data, headers)
        handler.do_POST()
        return handler, handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())

    @staticmethod
    def image(source="upload"):
        output = io.BytesIO()
        vision.Image.new("RGB", (16, 8), "green").save(output, format="PNG")
        return {"source": source, "data_url": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()}

    @unittest.skipIf(vision.Image is None, "Pillow required for real attachment decoding")
    def test_image_only_chat_supplies_default_question_and_model_input(self):
        _, status, result = self.post({"attachments": [self.image()]})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["provider"], "ollama-vision")
        question = self.ask.call_args.args[0]
        self.assertIn("image", question)
        self.assertTrue(question.strip())
        attachment = self.ask.call_args.kwargs["attachments"][0]
        self.assertEqual((attachment["width"], attachment["height"]), (16, 8))
        self.assertTrue(attachment["base64"])

    @unittest.skipIf(vision.Image is None, "Pillow required for real attachment decoding")
    def test_greeting_with_image_bypasses_deterministic_text_routing(self):
        youtube = self.patched(server, "plan_youtube", side_effect=AssertionError("Image request must bypass text action routing"))
        _, status, result = self.post({"message": "hi", "attachments": [self.image("camera")]})
        self.assertEqual(status, 200, result)
        self.assertEqual(self.ask.call_args.args[0], "hi")
        self.assertEqual(self.ask.call_args.kwargs["attachments"][0]["source"], "camera")
        youtube.assert_not_called()

    @unittest.skipIf(vision.Image is None, "Pillow required for real attachment decoding")
    def test_image_stream_delivers_start_deltas_and_metadata_only_done(self):
        def reply(message, on_token, **kwargs):
            on_token("A green ")
            on_token("test image.")
            return "A green test image.", "ollama-vision"
        self.ask.side_effect = reply
        handler = self.handler("/api/chat", {"message": "Explain", "attachments": [self.image("screen")]}, {"Accept": "application/x-ndjson"})
        handler.do_POST()
        events = [json.loads(line) for line in handler.wfile.getvalue().splitlines()]
        self.assertEqual([item["type"] for item in events], ["start", "delta", "delta", "done"])
        self.assertEqual(events[-1]["attachments"], [{"source": "screen", "width": 16, "height": 8}])
        self.assertNotIn("base64", json.dumps(events))
        handler.send_response.assert_called_once_with(200)

    @unittest.skipIf(vision.Image is None, "Pillow required for real attachment decoding")
    def test_history_activity_and_trace_do_not_contain_image_bytes(self):
        original = self.image("screen")
        handler, status, result = self.post({"message": "What is visible?", "attachments": [original]})
        self.assertEqual(status, 200, result)
        turn = self.append.call_args.args[0]
        self.assertEqual(turn["attachments"], [{"source": "screen", "width": 16, "height": 8}])
        recorded = repr(self.append.call_args_list) + repr(self.log.call_args_list) + repr(handler.trace.call_args_list)
        self.assertNotIn(original["data_url"], recorded)
        self.assertNotIn("data:image", recorded)
        self.assertNotIn("base64", recorded)
        self.assertNotIn(self.ask.call_args.kwargs["attachments"][0]["base64"], recorded)

    def test_malformed_images_fail_before_any_stream_headers_or_model_call(self):
        malformed = [[{"data_url": "https://example.com/image.png"}], [{"data_url": "data:image/png;base64,broken"}], [{}] * 5, "not-a-list"]
        for attachments in malformed:
            with self.subTest(attachments=attachments):
                handler, status, result = self.post({"message": "hi", "attachments": attachments}, headers={"Accept": "application/x-ndjson"})
                self.assertEqual(status, 400, result)
                self.assertFalse(getattr(handler, "chat_streaming", False))
                content_types = [call.args[1] for call in handler.send_header.call_args_list if call.args[0] == "Content-Type"]
                self.assertEqual(content_types, ["application/json; charset=utf-8"])
        self.ask.assert_not_called()
        self.append.assert_not_called()

    def test_empty_message_without_image_is_rejected(self):
        _, status, result = self.post({"message": " ", "attachments": []})
        self.assertEqual(status, 400, result)
        self.ask.assert_not_called()

    def test_untrusted_origin_is_rejected_before_reading_body(self):
        for origin in ("https://evil.example", "null", "http://localhost:12", "https://localhost:" + str(server.PORT)):
            with self.subTest(origin=origin):
                handler = self.handler("/api/chat", {"message": "hi"}, {"Origin": origin})
                handler.rfile = Mock()
                handler.do_POST()
                handler.send_response.assert_called_once_with(403)
                handler.rfile.read.assert_not_called()
        self.ask.assert_not_called()

    @unittest.skipIf(vision.Image is None, "Pillow required for real attachment decoding")
    def test_local_dashboard_origin_is_accepted(self):
        _, status, result = self.post({"attachments": [self.image()]}, headers={"Origin": "http://127.0.0.1:" + str(server.PORT)})
        self.assertEqual(status, 200, result)

    def test_oversized_or_negative_body_is_rejected_before_read(self):
        for content_length in (str(16 * 1024 * 1024 + 1), "-1"):
            with self.subTest(content_length=content_length):
                handler = self.handler("/api/chat", headers={"Content-Length": content_length})
                handler.rfile = Mock()
                handler.do_POST()
                handler.send_response.assert_called_once_with(400)
                self.assertIn("too large", json.loads(handler.wfile.getvalue())["error"])
                handler.rfile.read.assert_not_called()
        self.ask.assert_not_called()

    def test_nonobject_json_is_rejected(self):
        handler = self.handler("/api/chat")
        handler.rfile = io.BytesIO(b"[]")
        handler.headers["Content-Length"] = "2"
        handler.do_POST()
        handler.send_response.assert_called_once_with(400)
        self.assertIn("JSON object", json.loads(handler.wfile.getvalue())["error"])
        self.ask.assert_not_called()

    def test_status_endpoint_reuses_cache_and_explicit_refresh_reprobes(self):
        self.patched(vision, "Image", new=object())
        self.patched(vision, "OLLAMA_URL", new="http://127.0.0.1:11434")
        self.patched(vision, "_status_cache", new={"until": 0, "key": None, "value": None})
        def metadata(path, payload=None, **kwargs):
            return {"models": [{"name": "local-eyes"}]} if path == "/api/tags" else {"capabilities": ["vision"]}
        upstream = self.patched(vision, "_json_request", side_effect=metadata)
        for path in ("/api/vision/status", "/api/vision/status"):
            handler = self.handler(path)
            handler.do_GET()
            result = json.loads(handler.wfile.getvalue())
            self.assertTrue(result["available"])
            self.assertEqual(result["model"], "local-eyes")
            self.assertFalse(result["images_saved"])
            self.assertFalse(result["cloud_upload"])
        self.assertEqual(upstream.call_count, 2)
        handler = self.handler("/api/vision/status?refresh=1")
        handler.do_GET()
        self.assertEqual(upstream.call_count, 4)

    def test_native_wav_invalid_input_never_reaches_windows_process(self):
        self.patched(server, "prepare_speech", side_effect=lambda text: {"text": text})
        process = self.patched(windows_speech, "_request", side_effect=AssertionError("Invalid speech must not reach Windows process"))
        invalid = [{"text": value} for value in (None, {}, 12, "", " ", "x" * 1201)]
        invalid += [{"text": "Hello", "speed": speed} for speed in ("fast", -1, 3, float("nan"), float("inf"))]
        invalid += [{"text": "Hello", "voice": {}}, {"text": "Hello", "lang": "unknown"}]
        for payload in invalid:
            with self.subTest(payload=payload):
                _, status, result = self.post(payload, path="/api/tts/windows")
                self.assertEqual(status, 400, result)
        process.assert_not_called()

    def test_native_wav_response_is_uncached_binary_and_reports_selected_voice(self):
        self.patched(server, "prepare_speech", side_effect=lambda text: {"text": text})
        audio = b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 32
        synthesize = self.patched(server, "windows_synthesize", return_value=(audio, "Microsoft Kalpana", "hi-IN"))
        handler = self.handler("/api/tts/windows", {"text": "नमस्ते", "speed": 1.1, "voice": "kalpana", "lang": "hi-IN"})
        handler.do_POST()
        handler.send_response.assert_called_once_with(200)
        self.assertEqual(handler.wfile.getvalue(), audio)
        handler.send_header.assert_any_call("Content-Type", "audio/wav")
        handler.send_header.assert_any_call("Cache-Control", "no-store")
        handler.send_header.assert_any_call("X-SARA-Voice", "Microsoft+Kalpana")
        synthesize.assert_called_once_with("नमस्ते", voice="kalpana", lang="hi-IN", rate=1.1)


if __name__ == "__main__":
    unittest.main()
