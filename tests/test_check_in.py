"""Local initiated conversation checks without providers, writes or native actions."""
import io
import base64
import json
import unittest
from unittest.mock import Mock, patch

from sara_app import server
from sara_app import vision

SESSION = "isolated-check-in-session"


class CheckInTests(unittest.TestCase):
    def setUp(self):
        self.append = self.patched(server, "append_conversation")
        self.log = self.patched(server, "log")
        self.ask = self.patched(server, "ask", side_effect=AssertionError("A local check-in must not call a model"))
        self.visual = self.patched(server, "ask_visual_check_in", return_value=("A useful snapshot observation.", "ollama-vision"))
        self.execute = self.patched(server, "execute_routine_action", side_effect=AssertionError("A check-in must not execute an action"))
        self.propose = self.patched(server.action_state, "propose", side_effect=AssertionError("A check-in must not propose an action"))
        self.tasks = self.patched(server, "read_tasks", return_value=[{"id": "1", "text": "Review the draft", "status": "pending"}])
        self.reminders = self.patched(server, "read_reminders", return_value=[])
        self.events = self.patched(server, "read_events", return_value=[])
        self.writers = [self.patched(server, name, side_effect=AssertionError("Check-ins do not change assistant data"))
                        for name in ("write_memories", "write_tasks", "write_reminders", "write_events", "write_pronunciations")]

    def patched(self, target, name, **kwargs):
        patcher = patch.object(target, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    @staticmethod
    def handler(path="/api/check-in", data=None, origin=None):
        handler = object.__new__(server.Handler)
        raw = json.dumps(data if data is not None else {}).encode()
        handler.path = path
        handler.headers = {"Content-Length": str(len(raw)), "Accept": "application/json"}
        if origin is not None:
            handler.headers["Origin"] = origin
        handler.rfile, handler.wfile = io.BytesIO(raw), io.BytesIO()
        handler.send_response, handler.send_header, handler.end_headers = Mock(), Mock(), Mock()
        handler.trace = Mock()
        return handler

    def post(self, data, origin=None):
        handler = self.handler(data=data, origin=origin)
        handler.do_POST()
        return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())

    def assert_no_action(self):
        self.ask.assert_not_called()
        self.execute.assert_not_called()
        self.propose.assert_not_called()
        for writer in self.writers:
            writer.assert_not_called()

    @staticmethod
    def image(source="screen"):
        output = io.BytesIO()
        vision.Image.new("RGB", (12, 8), "blue").save(output, format="PNG")
        return {"source": source, "data_url": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()}

    @unittest.skipIf(vision.Image is None, "Pillow is required for image decoding")
    def test_opted_in_visual_check_in_persists_metadata_only_and_never_executes(self):
        image = self.image()
        status, result = self.post({"session_id": SESSION, "kind": "suggestion", "visual": True, "attachments": [image]})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["provider"], "ollama-vision")
        self.visual.assert_called_once()
        decoded = self.visual.call_args.args[0][0]
        self.assertEqual((decoded["source"], decoded["width"], decoded["height"]), ("screen", 12, 8))
        saved = self.append.call_args.args[0]
        self.assertEqual(saved["initiated_by"], "sara")
        self.assertEqual(saved["attachments"], [{"source": "screen", "width": 12, "height": 8}])
        self.assertNotIn(image["data_url"], repr(self.append.call_args_list) + repr(self.log.call_args_list))
        self.tasks.assert_not_called()
        self.assert_no_action()

    @unittest.skipIf(vision.Image is None, "Pillow is required for image decoding")
    def test_visual_check_in_rejects_uploads_multiple_images_and_bad_source(self):
        for images in ([self.image("upload")], [self.image(), self.image()], [self.image({})], []):
            with self.subTest(images=len(images)):
                status, _ = self.post({"session_id": SESSION, "kind": "suggestion", "visual": True, "attachments": images})
                self.assertEqual(status, 400)
        self.visual.assert_not_called()
        self.append.assert_not_called()
        self.log.assert_not_called()
        self.assert_no_action()

    @unittest.skipIf(vision.Image is None, "Pillow is required for image decoding")
    def test_busy_visual_check_in_is_skipped_without_empty_history_record(self):
        self.visual.return_value = ("", "check-in-skipped")
        status, result = self.post({"session_id": SESSION, "kind": "suggestion", "visual": True, "attachments": [self.image("camera")]})
        self.assertEqual(status, 200, result)
        self.assertTrue(result["skipped"])
        self.append.assert_not_called()
        self.log.assert_not_called()
        self.assert_no_action()

    @unittest.skipIf(vision.Image is None, "Pillow is required for image decoding")
    def test_snapshot_is_not_analyzed_without_explicit_visual_flag(self):
        status, result = self.post({"session_id": SESSION, "kind": "suggestion", "attachments": [self.image()]})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["provider"], "local-check-in")
        self.visual.assert_not_called()
        self.assertNotIn("attachments", self.append.call_args.args[0])
        self.assert_no_action()

    def test_greeting_is_local_devanagari_and_marked_as_sara_in_history(self):
        status, result = self.post({"session_id": SESSION, "kind": "greeting"})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["provider"], "local-check-in")
        self.assertIn("नमस्ते", result["reply"])
        self.assertNotIn("action", result)
        self.append.assert_called_once()
        saved = self.append.call_args.args[0]
        self.assertEqual(saved["initiated_by"], "sara")
        self.assertEqual(saved["provider"], "local-check-in")
        self.assertEqual(saved["answer"], result["reply"])
        self.assertEqual(saved["question"], "[SARA check-in]")
        self.log.assert_called_once_with("conversation", {"question": "[SARA check-in]", "answer": result["reply"], "provider": "local-check-in", "initiated_by": "sara"})
        self.tasks.assert_not_called()
        self.assert_no_action()

    def test_suggestion_reads_local_agenda_without_executing_or_saving_memory(self):
        status, result = self.post({"session_id": SESSION, "kind": "suggestion"})
        self.assertEqual(status, 200, result)
        self.assertIn("Review the draft", result["reply"])
        self.assertEqual(result["provider"], "local-check-in")
        self.assertNotIn("requires_confirmation", result)
        self.tasks.assert_called_once()
        self.reminders.assert_called_once()
        self.events.assert_called_once()
        self.assertEqual(self.append.call_args.args[0]["initiated_by"], "sara")
        self.assert_no_action()

    def test_missing_or_invalid_session_never_generates_or_persists_check_in(self):
        for session in (None, "", "short", 12, {}, "bad session has spaces", "x" * 81):
            with self.subTest(session=session):
                status, result = self.post({"session_id": session, "kind": "greeting"})
                self.assertEqual(status, 400, result)
        self.append.assert_not_called()
        self.log.assert_not_called()
        self.tasks.assert_not_called()
        self.assert_no_action()

    def test_cross_origin_cannot_initiate_a_check_in(self):
        status, result = self.post({"session_id": SESSION, "kind": "greeting"}, origin="https://external.example")
        self.assertEqual(status, 403, result)
        self.append.assert_not_called()
        self.log.assert_not_called()
        self.assert_no_action()

    def test_unrelated_payload_is_not_saved_as_memory_or_capture(self):
        private = "data:image/jpeg;base64,private-pixels"
        status, result = self.post({"session_id": SESSION, "kind": "greeting", "attachments": [{"source": "camera", "data_url": private}], "memory": "private personal fact"})
        self.assertEqual(status, 200, result)
        saved = repr(self.append.call_args_list) + repr(self.log.call_args_list)
        self.assertNotIn(private, saved)
        self.assertNotIn("private personal fact", saved)
        self.assertNotIn("attachments", saved)
        self.assert_no_action()

    def test_history_endpoint_preserves_initiator_metadata_for_reload(self):
        saved = {"question": "[SARA check-in]", "answer": "नमस्ते", "provider": "local-check-in", "initiated_by": "sara"}
        self.patched(server, "read_conversations", return_value=[saved])
        handler = self.handler(path="/api/conversations")
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        self.assertEqual(json.loads(handler.wfile.getvalue()), [saved])
        self.append.assert_not_called()
        self.assert_no_action()


if __name__ == "__main__":
    unittest.main()
