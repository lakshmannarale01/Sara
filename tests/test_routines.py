"""Saved routines are bounded data, reviewed snapshots and real tool outcomes."""
import json
from pathlib import Path
import tempfile
from threading import Lock
import unittest
from unittest.mock import patch

from sara_app import browser_control, config, policy, routines, tools, system_controls


class RoutineTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="sara-routines-")
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        self.patched(config, "DATA_DIR", self.directory)
        self.patched(policy, "_stopped", False)
        self.mode = self.patched(policy, "access_mode", return_value="review")
        self.patched(routines, "_run_lock", Lock())
        self.events = self.patched(routines, "log")
        self.steps = [{"type": "open_app", "app": "notepad"}, {"type": "youtube_play", "query": "focus music"}]

    def patched(self, target, name, *args, **kwargs):
        patcher = patch.object(target, name, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def save(self, name="work mode", steps=None, **kwargs):
        return routines.save_routine(name, self.steps if steps is None else steps, confirmed=True, **kwargs)["routine"]

    def execute(self, record, **kwargs):
        return routines.execute_saved_routine(record["id"], record["revision"], record["steps"], **kwargs)

    def test_round_trip_detached_records_and_immutable_content_revision(self):
        record = self.save()
        self.assertRegex(record["id"], r"^[a-f0-9]{32}$")
        self.assertRegex(record["revision"], r"^[a-f0-9]{64}$")
        self.assertEqual(routines.list_routines(), [record])
        loaded = routines.list_routines()
        loaded[0]["steps"][0]["app"] = "calculator"
        self.assertEqual(routines.list_routines()[0]["steps"], self.steps)
        saved = self.save("work mode", [{"type": "open_app", "app": "calculator"}], id=record["id"], revision=record["revision"])
        self.assertEqual(saved["id"], record["id"])
        self.assertEqual(saved["created"], record["created"])
        self.assertNotEqual(saved["revision"], record["revision"])
        with self.assertRaisesRegex(ValueError, "changed"):
            self.save("old edit", id=record["id"], revision=record["revision"])

    def test_casefolded_names_prevent_ambiguous_lookup_or_duplicate_save(self):
        record = self.save("Work Mode")
        self.assertEqual(routines.routine_action_for_name(" work   MODE ")["id"], record["id"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.save("work mode")
        with self.assertRaisesRegex(ValueError, "No saved"):
            routines.routine_action_for_name("not saved")

    def test_invalid_name_id_revision_and_update_shape_do_not_write(self):
        for name in (None, True, {}, "", "  ", "x" * 61, "bad\nname", "bad\x7fname"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.save(name)
        with self.assertRaises(ValueError):
            self.save(id="a" * 32)
        with self.assertRaises(ValueError):
            routines.delete_routine("../other", "a" * 64, confirmed=True)
        with self.assertRaises(ValueError):
            routines.delete_routine("a" * 32, [], confirmed=True)
        self.assertFalse((self.directory / "routines.json").exists())

    def test_steps_are_strict_and_bounded_before_any_execution(self):
        bad = [None, {}, [], self.steps * 5,
               [{"type": "run_routine", "id": "x"}], [{"type": "shell", "command": "whoami"}],
               [{"type": "write_file", "path": "x", "content": "y"}],
               [{"type": "whatsapp_send", "phone": "123", "text": "hi"}],
               [{"type": "open_app", "app": "notepad", "executable": "notepad.exe"}],
               [{"type": "open_app", "app": "unregistered"}],
               [{"type": "open_app", "app": {}}],
               [{"type": "open_browser_url", "url": "file:///C:/private"}],
               [{"type": "browser_open", "url": "https://example.com"}],
               [{"type": "youtube_play", "query": "play\ncommand"}],
               [{"type": "media_control", "command": "set_volume", "level": True}],
               [{"type": "media_control", "command": "set_volume", "level": 101}],
               [{"type": "media_control", "command": "mute", "level": 10}],
               [{"type": "media_control", "command": "hotkey", "keys": ["win", "r"]}]]
        for steps in bad:
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                routines.normalize_steps(steps)
        self.assertFalse((self.directory / "routines.json").exists())

    def test_supported_step_types_normalize_without_requiring_trusted_mode(self):
        self.assertEqual(self.mode.return_value, "review")
        steps = routines.normalize_steps([
            {"type": "open_app", "app": " Notepad "},
            {"type": "open_browser_url", "url": "https://www.google.com/search?q=Python"},
            {"type": "browser_open", "url": "https://en.wikipedia.org/wiki/Python"},
            {"type": "youtube_play", "query": " focus music "},
            {"type": "media_control", "command": "set_volume", "level": 30},
        ])
        self.assertEqual(steps[0]["app"], "notepad")
        self.assertEqual(steps[3]["query"], "focus music")
        self.assertEqual(steps[4], {"type": "media_control", "command": "set_volume", "level": 30})

    def test_confirmation_and_stop_apply_to_saving_deleting_and_running(self):
        preview = routines.save_routine("work mode", self.steps)
        self.assertTrue(preview["requires_confirmation"])
        self.assertFalse((self.directory / "routines.json").exists())
        record = self.save()
        with patch.object(routines, "_execute_step") as execute:
            self.assertTrue(self.execute(record)["requires_confirmation"])
            self.assertTrue(routines.delete_routine(record["id"], record["revision"])["requires_confirmation"])
            policy.set_stopped(True)
            self.assertTrue(self.execute(record, confirmed=True)["stopped"])
            self.assertTrue(self.execute(record, automatic=True)["stopped"])
            self.assertTrue(routines.save_routine("other", self.steps, confirmed=True)["stopped"])
            self.assertTrue(routines.delete_routine(record["id"], record["revision"], confirmed=True)["stopped"])
            execute.assert_not_called()
        self.assertEqual(routines.list_routines(), [record])

    def test_run_snapshot_must_match_current_id_name_revision_and_steps(self):
        record = self.save()
        plan = routines.routine_action_for_name("work mode")
        payload = {key: plan[key] for key in ("id", "name", "revision", "steps")}
        self.assertEqual(routines.validate_run_payload(payload), payload)
        changes = [{"id": "b" * 32}, {"name": "other"}, {"revision": "b" * 64},
                   {"steps": [{"type": "open_app", "app": "calculator"}]}, {"extra": "not reviewed"}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                routines.validate_run_payload({**payload, **change})
        self.save("work mode", [{"type": "open_app", "app": "calculator"}], id=record["id"], revision=record["revision"])
        with patch.object(routines, "_execute_step") as execute, self.assertRaisesRegex(ValueError, "changed"):
            self.execute(record, confirmed=True)
        execute.assert_not_called()

    def test_exact_review_runs_once_without_trusted_mode_and_keeps_tool_evidence(self):
        record = self.save()
        results = [{"ok": True, "launch_requested": True, "window_verified": False, "result": "Launch requested."},
                   {"ok": True, "video_opened": True, "playback_verified": False, "result": "Video opened; playback unverified."}]
        with patch.object(routines, "_execute_step", side_effect=results) as execute:
            result = self.execute(record, confirmed=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["completed_steps"], 2)
        self.assertEqual(result["attempted_steps"], 2)
        self.assertFalse(result["step_results"][1]["result"]["playback_verified"])
        self.assertEqual(execute.call_count, 2)

    def test_stop_between_steps_preserves_prior_result_without_requesting_next(self):
        record = self.save()
        def first(*_):
            policy.set_stopped(True)
            return {"ok": True, "result": "First request complete."}
        with patch.object(routines, "_execute_step", side_effect=first) as execute:
            result = self.execute(record, confirmed=True)
        self.assertFalse(result["ok"])
        self.assertTrue(result["partial"])
        self.assertTrue(result["stopped"])
        self.assertEqual(result["completed_steps"], 1)
        execute.assert_called_once()

    def test_trust_revocation_between_automatic_steps_stops_further_requests(self):
        record = self.save()
        self.mode.return_value = "trusted"
        def first(*_):
            self.mode.return_value = "review"
            return {"ok": True, "result": "First request complete."}
        with patch.object(routines, "_execute_step", side_effect=first) as execute:
            result = self.execute(record, automatic=True)
        self.assertTrue(result["permission_revoked"])
        self.assertEqual(result["completed_steps"], 1)
        execute.assert_called_once()

    def test_automatic_run_cannot_bypass_current_review_mode(self):
        record = self.save()
        with patch.object(routines, "_execute_step") as execute:
            result = self.execute(record, automatic=True)
        self.assertFalse(result["ok"])
        self.assertTrue(result["permission_revoked"])
        self.assertEqual(result["attempted_steps"], 0)
        execute.assert_not_called()

    def test_changed_or_deleted_routine_between_steps_stops_stale_snapshot(self):
        record = self.save()
        def first(*_):
            routines.delete_routine(record["id"], record["revision"], confirmed=True)
            return {"ok": True, "result": "First request complete."}
        with patch.object(routines, "_execute_step", side_effect=first) as execute:
            result = self.execute(record, confirmed=True)
        self.assertTrue(result["stale"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["attempted_steps"], 1)
        execute.assert_called_once()

    def test_failure_preserves_details_and_never_requests_following_step(self):
        record = self.save(steps=self.steps + [{"type": "open_app", "app": "calculator"}])
        with patch.object(routines, "_execute_step", side_effect=[{"ok": True, "result": "Launch requested."}, {"ok": False, "result": "Autoplay was blocked.", "playback_verified": False}]) as execute:
            result = self.execute(record, confirmed=True)
        self.assertFalse(result["ok"])
        self.assertEqual((result["completed_steps"], result["attempted_steps"]), (1, 2))
        self.assertIn("Autoplay was blocked", result["result"])
        self.assertEqual(execute.call_count, 2)
        with patch.object(routines, "_execute_step", side_effect=RuntimeError("native device unavailable")):
            failed = self.execute(record, confirmed=True)
        self.assertFalse(failed["ok"])
        self.assertIn("native device unavailable", failed["result"])

    def test_concurrent_run_is_rejected_without_double_dispatch(self):
        record = self.save()
        routines._run_lock.acquire()
        self.addCleanup(routines._run_lock.release)
        with patch.object(routines, "_execute_step") as execute:
            result = self.execute(record, confirmed=True)
        self.assertTrue(result["running"])
        execute.assert_not_called()

    def test_explicit_review_dispatch_has_only_the_bounded_named_tools(self):
        steps = [{"type": "open_app", "app": "notepad"},
                 {"type": "open_browser_url", "url": "https://www.youtube.com"},
                 {"type": "browser_open", "url": "https://www.youtube.com"},
                 {"type": "youtube_play", "query": "focus music"},
                 {"type": "media_control", "command": "set_volume", "level": 30}]
        record = self.save(steps=steps)
        with patch.object(tools, "open_app", return_value={"ok": True}) as app, \
             patch.object(tools, "open_browser_url", return_value={"ok": True}) as url, \
             patch.object(browser_control, "open_page", return_value={"ok": True}) as controlled, \
             patch.object(browser_control, "play_youtube", return_value={"ok": True}) as youtube, \
             patch.object(system_controls, "execute_media_control", return_value={"ok": True}) as media:
            self.assertTrue(self.execute(record, confirmed=True)["ok"])
        app.assert_called_once_with("notepad", confirmed=True)
        url.assert_called_once_with("https://www.youtube.com", confirmed=True)
        controlled.assert_called_once_with("https://www.youtube.com", confirmed=True)
        youtube.assert_called_once_with("focus music", confirmed=True)
        media.assert_called_once_with("set_volume", level=30, confirmed=True)

    def test_automatic_steps_use_fresh_routine_dispatcher(self):
        record = self.save()
        self.mode.return_value = "trusted"
        with patch.object(tools, "execute_routine_action", return_value={"ok": True}) as dispatch:
            self.assertTrue(self.execute(record, automatic=True)["ok"])
        self.assertEqual([call.args[0] for call in dispatch.call_args_list], self.steps)

    def test_corrupt_json_bytes_are_preserved_before_first_confirmed_save(self):
        path = self.directory / "routines.json"
        original = b"\xffbroken JSON"
        path.write_bytes(original)
        self.save()
        backups = list(self.directory.glob("routines.json.recovery-*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)

    def test_invalid_record_content_is_not_silently_dropped_on_mutation(self):
        path = self.directory / "routines.json"
        original = json.dumps([{"id": "legacy", "steps": "not a list"}]).encode()
        path.write_bytes(original)
        self.assertEqual(routines.list_routines(), [])
        with self.assertRaisesRegex(ValueError, "invalid"):
            self.save()
        self.assertEqual(path.read_bytes(), original)

    def test_delete_requires_exact_current_revision(self):
        record = self.save()
        with self.assertRaisesRegex(ValueError, "changed"):
            routines.delete_routine(record["id"], "b" * 64, confirmed=True)
        result = routines.delete_routine(record["id"], record["revision"], confirmed=True)
        self.assertTrue(result["ok"])
        self.assertEqual(routines.list_routines(), [])

    def test_routine_limit_does_not_silently_discard_oldest_records(self):
        for index in range(routines.MAX_ROUTINES):
            self.save("routine " + str(index), self.steps[:1])
        with self.assertRaisesRegex(ValueError, "At most"):
            self.save("one too many", self.steps[:1])
        self.assertEqual(len(routines.list_routines()), routines.MAX_ROUTINES)
        self.assertEqual(routines.list_routines()[0]["name"], "routine 0")


if __name__ == "__main__":
    unittest.main()
