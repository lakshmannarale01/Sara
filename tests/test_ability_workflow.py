"""Named media/routine workflows with in-memory HTTP and disposable local data."""
import io
import json
from pathlib import Path
import tempfile
from threading import Lock
import unittest
from unittest.mock import Mock, patch

from sara_app import action_state, config, policy, routines, server, system_controls, tools
from sara_app.intents import action_payload


class AbilityWorkflowTests(unittest.TestCase):
    SESSION = "ability-workflow-session"

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="sara-ability-workflow-")
        self.addCleanup(folder.cleanup)
        self.patched(config, "DATA_DIR", Path(folder.name))
        self.store = action_state.ActionStore()
        self.patched(action_state, "_store", self.store)
        self.patched(policy, "_stopped", False)
        self.mode = self.patched(policy, "access_mode", return_value="trusted")
        self.patched(routines, "_run_lock", Lock())
        self.patched(routines, "log")
        self.patched(system_controls, "log")
        self.append = self.patched(server, "append_conversation")
        self.patched(server, "log")
        self.patched(server, "request_performance", return_value={})
        for name in ("read_memories", "read_tasks", "read_events", "read_reminders", "read_conversations"):
            self.patched(server, name, return_value=[])
        self.ask = self.patched(server, "ask", side_effect=AssertionError("A bounded ability must not reach a model"))
        self.automatic = self.patched(server, "execute_routine_action", return_value={"ok": True, "volume": 30, "muted": False, "readback_verified": True, "result": "Windows output is 30%, unmuted. Readback verified."})
        self.media = self.patched(server, "execute_media_control", wraps=system_controls.execute_media_control)
        self.audio_process = self.patched(system_controls, "_request", return_value={"available": True, "volume": 30, "muted": False, "readback_verified": True, "changed": True})
        self.save = self.patched(server, "save_routine", wraps=routines.save_routine)
        self.delete = self.patched(server, "delete_routine", wraps=routines.delete_routine)
        self.run = self.patched(server, "execute_saved_routine", wraps=routines.execute_saved_routine)
        self.step = self.patched(routines, "_execute_step", return_value={"ok": True, "result": "Mock step completed."})

    def patched(self, target, name, *args, **kwargs):
        patcher = patch.object(target, name, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def request(self, path, data=None, session=SESSION, method="POST"):
        handler = object.__new__(server.Handler)
        handler.path = path
        payload = dict(data or {})
        if session is not None:
            payload["session_id"] = session
        raw = json.dumps(payload).encode("utf-8")
        handler.headers = {"Content-Length": str(len(raw)), "Accept": "application/json"}
        handler.rfile, handler.wfile = io.BytesIO(raw), io.BytesIO()
        handler.send_response, handler.send_header, handler.end_headers, handler.trace = Mock(), Mock(), Mock(), Mock()
        if method == "GET": handler.do_GET()
        else: handler.do_POST()
        handler.send_response.assert_called_once()
        return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())

    def chat(self, message, session=SESSION):
        status, result = self.request("/api/chat", {"message": message}, session=session)
        self.assertEqual(status, 200, result)
        return result

    def saved(self, name="work mode", steps=None):
        return routines.save_routine(name, steps or [{"type": "open_app", "app": "notepad"}, {"type": "media_control", "command": "set_volume", "level": 30}], confirmed=True)["routine"]

    @staticmethod
    def approval(proposal, **changes):
        return {**action_payload(proposal["action"]), "confirmed": True, "proposal_id": proposal["proposal_id"], **changes}

    def test_trusted_media_chat_executes_once_and_reports_real_evidence(self):
        result = self.chat("volume 30 percent karo")
        self.assertFalse(result["requires_confirmation"])
        self.assertIn("Readback verified", result["reply"])
        self.assertEqual(result["action_result"]["type"], "media_control")
        self.assertEqual(result["action_result"]["status"], "completed")
        self.automatic.assert_called_once()
        self.assertEqual(action_payload(self.automatic.call_args.args[0]), {"command": "set_volume", "level": 30})
        self.assertIsNone(self.store.pending(self.SESSION))
        self.assertEqual(self.append.call_args.args[0]["action_result"], result["action_result"])
        self.audio_process.assert_not_called()
        self.ask.assert_not_called()

    def test_review_mode_media_proposal_executes_only_after_exact_approval(self):
        self.mode.return_value = "review"
        proposal = self.chat("volume 30 percent karo")
        self.assertTrue(proposal["requires_confirmation"])
        self.automatic.assert_not_called()
        self.audio_process.assert_not_called()
        status, result = self.request("/api/actions/media-control", self.approval(proposal))
        self.assertEqual(status, 200, result)
        self.assertTrue(result["readback_verified"])
        self.audio_process.assert_called_once_with({"command": "set_volume", "level": 30})
        self.assertEqual(result["action_result"]["status"], "completed")
        replay_status, _ = self.request("/api/actions/media-control", self.approval(proposal))
        self.assertEqual(replay_status, 409)
        self.assertEqual(self.audio_process.call_count, 1)

    def test_changed_media_content_and_cross_session_proposal_are_rejected(self):
        self.mode.return_value = "review"
        proposal = self.chat("volume 30 percent karo")
        for body, session in ((self.approval(proposal, level=90), self.SESSION), (self.approval(proposal), "other-ability-session")):
            status, result = self.request("/api/actions/media-control", body, session=session)
            self.assertEqual(status, 409, result)
        self.audio_process.assert_not_called()

    def test_stop_or_missing_session_never_mutates_media_or_routines(self):
        policy.set_stopped(True)
        stopped = self.chat("mute karo")
        self.assertTrue(stopped["requires_confirmation"])
        status, _ = self.request("/api/actions/media-control", {"command": "mute", "confirmed": True})
        self.assertEqual(status, 409)
        policy.set_stopped(False)
        anonymous = self.chat("mute karo", session=None)
        self.assertTrue(anonymous["requires_confirmation"])
        for path, body in (("/api/actions/media-control", {"command": "mute"}), ("/api/routines", {"name": "test", "steps": []})):
            status, _ = self.request(path, {**body, "confirmed": True}, session=None)
            self.assertEqual(status, 400)
        self.automatic.assert_not_called()
        self.media.assert_not_called()
        self.save.assert_not_called()
        self.audio_process.assert_not_called()

    def test_invalid_media_inputs_are_400_before_any_os_effect(self):
        for payload in ({"command": "set_volume", "level": True}, {"command": "set_volume", "level": 101},
                        {"command": "set_volume", "level": "30"}, {"command": []}, {"command": "shell"},
                        {"command": "mute", "level": None}, {"command": "mute", "keys": ["win", "r"]}):
            for confirmed in (False, True):
                with self.subTest(payload=payload, confirmed=confirmed):
                    status, result = self.request("/api/actions/media-control", {**payload, "confirmed": confirmed})
                    self.assertEqual(status, 400, result)
        self.audio_process.assert_not_called()

    def test_audio_status_remains_readonly_while_actions_are_paused(self):
        policy.set_stopped(True)
        status, result = self.request("/api/audio/status", method="GET")
        self.assertEqual(status, 200, result)
        self.assertTrue(result["available"])
        self.assertEqual(result["volume"], 30)
        self.audio_process.assert_called_once_with({"command": "read"})
        self.media.assert_not_called()
        self.automatic.assert_not_called()
        self.append.assert_not_called()

    def test_create_routine_chat_reviews_all_steps_without_saving_or_running(self):
        result = self.chat("create routine work mode: open notepad; volume 30 percent karo")
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["action"]["type"], "save_routine")
        self.assertEqual(result["action"]["steps"], [{"type": "open_app", "app": "notepad"}, {"type": "media_control", "command": "set_volume", "level": 30}])
        self.assertEqual(routines.list_routines(), [])
        self.save.assert_not_called()
        self.step.assert_not_called()
        self.automatic.assert_not_called()
        status, saved = self.request("/api/routines", self.approval(result))
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved["routine"]["name"], "work mode")
        self.assertEqual(len(routines.list_routines()), 1)
        self.step.assert_not_called()
        replay, _ = self.request("/api/routines", self.approval(result))
        self.assertEqual(replay, 409)
        self.assertEqual(self.save.call_count, 1)

    def test_unsupported_step_rejects_entire_routine_draft(self):
        result = self.chat("create routine work mode: open notepad; delete secret.txt")
        self.assertNotIn("action", result)
        self.assertEqual(result["clarification"]["kind"], "routine")
        self.assertEqual(routines.list_routines(), [])
        self.save.assert_not_called()
        self.step.assert_not_called()
        self.automatic.assert_not_called()

    def test_trusted_run_uses_current_frozen_revision_and_real_step_results(self):
        record = self.saved()
        self.automatic.side_effect = tools.execute_routine_action
        result = self.chat("run routine work mode")
        self.assertFalse(result["requires_confirmation"])
        self.assertEqual(result["action_result"]["type"], "run_routine")
        self.assertEqual(result["action_result"]["status"], "completed")
        self.assertEqual(result["tool_result"]["completed_steps"], 2)
        self.assertEqual(self.step.call_count, 2)
        action = self.automatic.call_args.args[0]
        self.assertEqual(action["id"], record["id"])
        self.assertEqual(action["revision"], record["revision"])
        self.assertEqual(action["steps"], record["steps"])
        self.assertIsNone(self.store.pending(self.SESSION))
        saved = self.append.call_args.args[0]
        self.assertEqual(saved["step_results"], result["tool_result"]["step_results"])
        self.assertEqual(saved["total_steps"], 2)

    def test_reviewed_run_rejects_mutated_steps_before_executor(self):
        self.saved()
        self.mode.return_value = "review"
        proposal = self.chat("run routine work mode")
        body = self.approval(proposal)
        body["steps"] = [{"type": "media_control", "command": "set_volume", "level": 100}]
        status, result = self.request("/api/routines/" + body["id"] + "/run", body)
        self.assertEqual(status, 409, result)
        self.run.assert_not_called()
        self.step.assert_not_called()

    def test_reviewed_run_cannot_execute_a_changed_saved_revision(self):
        record = self.saved()
        self.mode.return_value = "review"
        proposal = self.chat("run routine work mode")
        routines.save_routine("work mode", [{"type": "open_app", "app": "calculator"}], confirmed=True, id=record["id"], revision=record["revision"])
        status, result = self.request("/api/routines/" + record["id"] + "/run", self.approval(proposal))
        self.assertEqual(status, 400, result)
        self.assertIn("changed", result["error"])
        self.step.assert_not_called()

    def test_reviewed_run_is_once_only_and_records_each_step_result(self):
        record = self.saved()
        self.mode.return_value = "review"
        proposal = self.chat("run routine work mode")
        path = "/api/routines/" + record["id"] + "/run"
        status, result = self.request(path, self.approval(proposal))
        self.assertEqual(status, 200, result)
        self.assertEqual(result["completed_steps"], 2)
        self.assertEqual(result["action_result"]["status"], "completed")
        self.assertEqual(self.step.call_count, 2)
        saved = self.append.call_args.args[0]
        self.assertEqual(saved["step_results"], result["step_results"])
        self.assertEqual(saved["total_steps"], 2)
        status, _ = self.request(path, self.approval(proposal))
        self.assertEqual(status, 409)
        self.assertEqual(self.step.call_count, 2)

    def test_reviewed_save_update_accepts_body_id_and_rejects_stale_revision(self):
        record = self.saved()
        action = {"type": "save_routine", "name": "work mode", "steps": [{"type": "open_app", "app": "calculator"}], "id": record["id"], "revision": record["revision"]}
        proposal = self.store.propose(self.SESSION, action)
        status, result = self.request("/api/routines", {**action_payload(action), "confirmed": True, "proposal_id": proposal["id"]})
        self.assertEqual(status, 200, result)
        self.assertNotEqual(result["routine"]["revision"], record["revision"])
        status, stale = self.request("/api/routines", {**action_payload(action), "confirmed": True})
        self.assertEqual(status, 400, stale)
        self.step.assert_not_called()

    def test_reviewed_delete_is_once_only_and_path_id_must_match(self):
        record = self.saved()
        action = {"type": "delete_routine", "id": record["id"], "revision": record["revision"]}
        proposal = self.store.propose(self.SESSION, action)
        body = {**action_payload(action), "confirmed": True, "proposal_id": proposal["id"]}
        wrong, _ = self.request("/api/routines/" + "f" * 32 + "/delete", body)
        self.assertEqual(wrong, 409)
        status, result = self.request("/api/routines/" + record["id"] + "/delete", body)
        self.assertEqual(status, 200, result)
        self.assertEqual(routines.list_routines(), [])
        replay, _ = self.request("/api/routines/" + record["id"] + "/delete", body)
        self.assertEqual(replay, 409)
        self.assertEqual(self.delete.call_count, 1)
        self.step.assert_not_called()


if __name__ == "__main__":
    unittest.main()
