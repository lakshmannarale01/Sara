"""Trusted chat actions use real proposal outcomes without repeated review UI."""
import io
import json
import unittest
from unittest.mock import Mock, patch

from sara_app import action_state, policy, server


class TrustedWorkflowTests(unittest.TestCase):
    SESSION = "trusted_workflow_test"

    def setUp(self):
        self.store = action_state.ActionStore()
        self.patched(action_state, "_store", self.store)
        self.patched(policy, "_stopped", False)
        self.mode = self.patched(policy, "access_mode", return_value="trusted")
        self.append = self.patched(server, "append_conversation")
        self.patched(server, "log")
        for name in ("read_memories", "read_tasks", "read_events", "read_reminders", "read_conversations"):
            self.patched(server, name, return_value=[])
        self.patched(server, "ask", side_effect=AssertionError("A routine request must not reach the model"))
        self.patched(server, "request_performance", return_value={})
        self.execute = self.patched(server, "execute_routine_action", return_value={"ok": True, "playback_verified": False, "result": "Opened the video. Playback could not be verified."})

    def patched(self, target, name, *args, **kwargs):
        patcher = patch.object(target, name, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def post(self, path, data, session=SESSION):
        payload = dict(data)
        if session is not None:
            payload["session_id"] = session
        raw = json.dumps(payload).encode()
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
        return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())

    def test_trusted_song_request_runs_once_and_keeps_truthful_player_result(self):
        status, result = self.post("/api/chat", {"message": "ek song play karo best on you tube"})
        self.assertEqual(status, 200, result)
        self.assertFalse(result.get("requires_confirmation"), result)
        self.assertIn("Playback could not be verified", result["reply"])
        self.assertEqual(result["action_result"]["type"], "youtube_play")
        self.assertEqual(result["action_result"]["status"], "completed")
        self.execute.assert_called_once()
        self.assertEqual(self.execute.call_args.args[0]["type"], "youtube_play")
        self.assertIsNone(self.store.pending(self.SESSION))
        self.assertTrue(self.append.called)

    def test_review_mode_keeps_song_pending_without_execution(self):
        self.mode.return_value = "review"
        status, result = self.post("/api/chat", {"message": "play Arijit Singh songs on youtube"})
        self.assertEqual(status, 200, result)
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["action"]["type"], "youtube_play")
        self.assertIsNotNone(self.store.pending(self.SESSION))
        self.execute.assert_not_called()

    def test_high_impact_note_remains_reviewed_in_trusted_mode(self):
        status, result = self.post("/api/chat", {"message": 'notepad mein "Hello" likho'})
        self.assertEqual(status, 200, result)
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["action"]["type"], "notepad_write")
        self.execute.assert_not_called()

    def test_stop_and_missing_session_never_execute_automatically(self):
        policy.set_stopped(True)
        self.post("/api/chat", {"message": "play a song on youtube"})
        policy.set_stopped(False)
        self.post("/api/chat", {"message": "play a song on youtube"}, session=None)
        self.execute.assert_not_called()

    def test_tool_exception_records_failure_without_success_claim(self):
        self.execute.side_effect = RuntimeError("browser unavailable")
        status, result = self.post("/api/chat", {"message": "play a song on youtube"})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["action_result"]["status"], "failed")
        self.assertNotIn("Action completed", result["reply"])
        self.assertIsNone(self.store.pending(self.SESSION))
        self.execute.assert_called_once()

    def test_completed_automatic_proposal_cannot_replay_through_review_endpoint(self):
        _, result = self.post("/api/chat", {"message": "play a song on youtube"})
        proposal_id = result["action_result"]["proposal_id"]
        action = self.store.get(self.SESSION, proposal_id)["action"]
        status, rejection = self.post("/api/actions/youtube-play", {"query": action["query"], "confirmed": True, "proposal_id": proposal_id})
        self.assertEqual(status, 409, rejection)
        self.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
