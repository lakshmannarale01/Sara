"""Exercise reviewed action conversations without models, apps, sockets or data I/O."""

import io
import json
import unittest
from unittest.mock import Mock, patch

from sara_app import action_state, policy, server


class ActionWorkflowTests(unittest.TestCase):
    SESSION = "dashboard_test_A"
    OTHER_SESSION = "dashboard_test_B"

    def setUp(self):
        self.clock = [100.0]
        self.store = action_state.ActionStore(ttl_seconds=300, clock=lambda: self.clock[0])
        self.enter_patch(action_state, "_store", self.store)
        self.enter_patch(policy, "_stopped", False)
        self.append = self.enter_patch(server, "append_conversation")
        self.enter_patch(server, "log")
        self.memories = self.enter_patch(server, "read_memories", return_value=[])
        for name in ("read_tasks", "read_events", "read_reminders", "read_conversations"):
            self.enter_patch(server, name, return_value=[])
        for name in ("write_memories", "write_tasks", "write_events", "write_reminders"):
            self.enter_patch(server, name, side_effect=AssertionError("Unexpected persisted write: " + name))
        self.ask = self.enter_patch(server, "ask", side_effect=AssertionError("An operation must not reach the model"))
        self.enter_patch(server, "request_performance", return_value={})
        self.executors = {}
        for name in ("create_notepad_note", "open_app", "open_url", "open_browser_url", "open_whatsapp_draft",
                     "open_email_draft", "type_text", "press_hotkey", "click_point", "semantic_open_page",
                     "semantic_click_text", "semantic_fill_text", "whatsapp_send"):
            self.executors[name] = self.enter_patch(server, name, side_effect=AssertionError("Unexpected execution: " + name))
        self.notepad = self.executors["create_notepad_note"]

    def enter_patch(self, target, name, *args, **kwargs):
        patcher = patch.object(target, name, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def post(self, path, data, session=SESSION):
        payload = dict(data)
        if session is not None:
            payload["session_id"] = session
        raw = json.dumps(payload).encode("utf-8")
        handler = object.__new__(server.Handler)
        handler.path = path
        handler.headers = {"Content-Length": str(len(raw)), "Accept": "application/json"}
        handler.rfile = io.BytesIO(raw)
        handler.wfile = io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.trace = Mock()
        handler.do_POST()
        handler.send_response.assert_called_once()
        return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())

    def chat(self, message, session=SESSION):
        status, data = self.post("/api/chat", {"message": message}, session)
        self.assertEqual(status, 200, data)
        return data

    def propose_note(self, message='Notepad mein "Hello from Sara" likho.'):
        data = self.chat(message)
        self.assertTrue(data["requires_confirmation"])
        self.assertEqual(data["action"]["type"], "notepad_write")
        return data

    @staticmethod
    def note_request(proposal, **changes):
        return {"proposal_id": proposal["action"]["proposal_id"], "text": proposal["action"]["text"],
                "confirmed": True, **changes}

    def allow_note(self, result=None):
        self.notepad.side_effect = None
        self.notepad.return_value = result or {
            "ok": True, "file_written": True, "text_verified": True,
            "launch_requested": True, "window_verified": False, "note_id": "a" * 32,
            "result": "The note was saved and verified. Notepad was asked to open it; its window was not verified.",
        }

    def assert_no_execution(self):
        self.ask.assert_not_called()
        for executor in self.executors.values():
            executor.assert_not_called()

    def test_combined_screenshot_command_preserves_write_before_app_open(self):
        data = self.propose_note("notepad open karo aur mere liye kuchh likho.")
        self.assertTrue(data["action"]["text"].strip())
        self.assertEqual(self.store.pending(self.SESSION)["id"], data["proposal_id"])
        self.assert_no_execution()

    def test_typed_open_karo_reopens_same_exact_proposal_without_execution(self):
        first = self.propose_note("notepad open karo aur mere liye kuchh likho.")
        reopened = self.chat("Open Karo.")
        self.assertTrue(reopened["review_pending"])
        self.assertEqual(reopened["action"], first["action"])
        self.assertEqual(reopened["proposal_id"], first["proposal_id"])
        self.assertEqual(self.store.get(self.SESSION, first["proposal_id"])["status"], "pending")
        self.assert_no_execution()

    def test_open_karo_without_pending_never_claims_completion_or_calls_model(self):
        data = self.chat("Open Karo.")
        self.assertEqual(data["provider"], "action-state")
        self.assertNotIn("action", data)
        self.assertIn("koi pending action nahi", data["reply"].lower())
        self.assert_no_execution()

    def test_other_dashboard_cannot_resume_or_execute_this_proposal(self):
        first = self.propose_note()
        data = self.chat("yes", session=self.OTHER_SESSION)
        self.assertNotIn("action", data)
        status, rejection = self.post("/api/actions/notepad-write", self.note_request(first), self.OTHER_SESSION)
        self.assertEqual(status, 409, rejection)
        self.assertEqual(self.store.get(self.SESSION, first["proposal_id"])["status"], "pending")
        self.assert_no_execution()

    def test_profile_screenshot_phrases_use_full_approved_memories_only(self):
        full_fact = ("I prefer detailed project notes. " + "A long approved detail. " * 15).strip()
        self.memories.return_value = [
            {"text": full_fact, "approved": True},
            {"text": "UNAPPROVED_PRIVATE_FACT", "approved": False},
            {"text": "LEGACY_UNAPPROVED_FACT"},
            {"text": "TRUTHY_IS_NOT_APPROVAL", "approved": "true"},
        ]
        phrases = (
            "Notepad Mein mere related Jo bhee hai wo SAB kuchh likho Jo bhee AAP jaante ho.",
            "Kyonki AAP mere related jante ho SAB kuchh likho notepad Mein aur mujhe dikhaao.",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                data = self.propose_note(phrase)
                content = data["action"]["text"]
                self.assertIn(full_fact, content)
                self.assertNotIn("UNAPPROVED", content)
                self.assertNotIn("TRUTHY_IS_NOT_APPROVAL", content)
        self.assert_no_execution()

    def test_empty_profile_explicitly_acknowledges_no_saved_details(self):
        data = self.propose_note("Notepad mein mere baare mein sab kuch likho.")
        self.assertIn("koi approved personal detail", data["action"]["text"])
        self.assertNotIn("personal goals and objectives", data["action"]["text"].lower())
        self.assert_no_execution()

    def test_literal_note_text_is_previewed_exactly(self):
        phrases = (
            ('Write "My project status: ready!" in Notepad.', "My project status: ready!"),
            ("open notepad and write Hello world", "Hello world"),
            ("Notepad mein write: Keep punctuation, names and API values.", "Keep punctuation, names and API values."),
            ("Notepad mein Hello Sara likho.", "Hello Sara"),
        )
        for phrase, expected in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(self.propose_note(phrase)["action"]["text"], expected)
        self.assert_no_execution()

    def test_proposal_requires_explicit_boolean_approval(self):
        proposal = self.propose_note()
        for confirmation in (None, False, "true", 1):
            with self.subTest(confirmed=confirmation):
                request = self.note_request(proposal, confirmed=confirmation)
                status, result = self.post("/api/actions/notepad-write", request)
                self.assertEqual(status, 409, result)
                self.assertTrue(result["requires_confirmation"])
        self.assertEqual(self.store.get(self.SESSION, proposal["proposal_id"])["status"], "pending")
        self.assert_no_execution()

    def test_tampered_review_content_rejected_and_original_stays_pending(self):
        proposal = self.propose_note()
        status, result = self.post("/api/actions/notepad-write", self.note_request(proposal, text="Changed after review"))
        self.assertEqual(status, 409, result)
        self.assertIn("changed", result["error"].lower())
        self.assertEqual(self.store.get(self.SESSION, proposal["proposal_id"])["status"], "pending")
        self.assert_no_execution()

    def test_approved_proposal_executes_once_and_records_real_tool_result(self):
        proposal = self.propose_note()
        self.allow_note()
        request = self.note_request(proposal)
        status, result = self.post("/api/actions/notepad-write", request)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["action_result"]["status"], "completed")
        self.assertFalse(result["window_verified"])
        duplicate_status, rejection = self.post("/api/actions/notepad-write", request)
        self.assertEqual(duplicate_status, 409, rejection)
        self.assertIn("completed", rejection["error"])
        self.notepad.assert_called_once_with(proposal["action"]["text"], confirmed=True)
        evidence = self.store.context(self.SESSION)["recent_outcomes"][-1]
        self.assertEqual(evidence["status"], "completed")
        self.assertEqual(evidence["result"]["result"], result["result"])
        self.assertTrue(any(call.args[0].get("provider") == "tool-result" for call in self.append.call_args_list))
        self.ask.assert_not_called()

    def test_launch_failure_retains_saved_note_evidence_and_failed_status(self):
        proposal = self.propose_note()
        self.allow_note({
            "ok": False, "file_written": True, "text_verified": True, "launch_requested": False,
            "window_verified": False, "note_id": "b" * 32, "file_path": "test-saved-note.txt",
            "result": "The note was saved and verified, but Notepad could not be launched.",
            "error": "Mock launch error", "recovery": "Read the saved note in its preview.",
        })
        status, result = self.post("/api/actions/notepad-write", self.note_request(proposal))
        self.assertEqual(status, 502, result)
        self.assertTrue(result["file_written"])
        self.assertEqual(result["note_id"], "b" * 32)
        self.assertIn("preview", result["recovery"])
        self.assertEqual(result["action_result"]["status"], "failed")
        record = self.store.get(self.SESSION, proposal["proposal_id"])
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["result"]["note_id"], "b" * 32)
        report = self.chat("Did you write it?")
        self.assertIn("failed", report["reply"])
        self.assertIn("could not be launched", report["reply"])
        self.ask.assert_not_called()

    def test_tool_exception_records_failure_and_cannot_be_retried_silently(self):
        proposal = self.propose_note()
        self.notepad.side_effect = OSError("Mock executor failure")
        status, result = self.post("/api/actions/notepad-write", self.note_request(proposal))
        self.assertEqual(status, 500, result)
        self.assertEqual(result["action_result"]["status"], "failed")
        status, _ = self.post("/api/actions/notepad-write", self.note_request(proposal))
        self.assertEqual(status, 409)
        self.notepad.assert_called_once()

    def test_cancelled_proposal_cannot_execute_or_resume(self):
        proposal = self.propose_note()
        status, result = self.post("/api/actions/cancel", {"proposal_id": proposal["proposal_id"]})
        self.assertEqual(status, 200, result)
        self.assertTrue(result["cancelled"])
        status, rejection = self.post("/api/actions/notepad-write", self.note_request(proposal))
        self.assertEqual(status, 409, rejection)
        self.assertIn("cancelled", rejection["error"])
        self.assertNotIn("action", self.chat("Open karo."))
        self.assert_no_execution()

    def test_typed_cancellation_cancels_pending_proposal(self):
        proposal = self.propose_note()
        data = self.chat("Mat karo.")
        self.assertEqual(data["provider"], "action-state")
        self.assertEqual(self.store.get(self.SESSION, proposal["proposal_id"])["status"], "cancelled")
        self.assert_no_execution()

    def test_expired_proposal_cannot_execute(self):
        proposal = self.propose_note()
        self.clock[0] += 301
        status, result = self.post("/api/actions/notepad-write", self.note_request(proposal))
        self.assertEqual(status, 409, result)
        self.assertIn("expired", result["error"])
        self.assertNotIn("action", self.chat("yes"))
        self.assert_no_execution()

    def test_new_request_supersedes_old_proposal_and_yes_uses_new_draft(self):
        old = self.propose_note()
        latest = self.propose_note('Notepad mein "Use the newer draft" likho.')
        status, rejection = self.post("/api/actions/notepad-write", self.note_request(old))
        self.assertEqual(status, 409, rejection)
        self.assertIn("superseded", rejection["error"])
        reopened = self.chat("haan karo")
        self.assertEqual(reopened["action"], latest["action"])
        self.assert_no_execution()

    def test_status_without_execution_rejects_prior_chat_as_proof(self):
        data = self.chat("Did you open it?")
        self.assertEqual(data["provider"], "action-state")
        self.assertIn("koi executed action result nahi", data["reply"])
        self.assert_no_execution()

    def test_status_of_pending_action_does_not_report_it_as_completed(self):
        proposal = self.propose_note()
        data = self.chat("Ho gaya?")
        self.assertEqual(data["provider"], "action-state")
        self.assertTrue(data["requires_confirmation"])
        self.assertEqual(data["action"], proposal["action"])
        self.assertIn("pending approval", data["reply"])
        self.assert_no_execution()

    def test_unsupported_app_operation_returns_grounded_failure_without_model(self):
        data = self.chat("Open unsupported_app please")
        self.assertEqual(data["provider"], "action-unavailable")
        self.assertNotIn("action", data)
        self.assertIn("kuch execute nahi hua", data["reply"])
        self.assert_no_execution()

    def test_explanatory_notepad_question_keeps_normal_chat_available(self):
        self.ask.side_effect = None
        self.ask.return_value = ("Notepad is a text editor.", "ollama")
        data = self.chat("How does Notepad work?")
        self.assertEqual(data["provider"], "ollama")
        self.assertNotIn("action", data)
        self.ask.assert_called_once()
        self.assertEqual(self.ask.call_args.kwargs["tool_context"], {"pending": None, "recent_outcomes": []})
        for executor in self.executors.values():
            executor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
