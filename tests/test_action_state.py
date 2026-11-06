import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from sara_app.action_state import ActionStore


class ActionStateTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.store = ActionStore(clock=lambda: self.now)
        self.action = {"action": "open_app", "app": "notepad"}

    def test_sessions_are_isolated_and_tokens_are_uuid(self):
        proposal = self.store.propose("one", self.action)
        self.assertEqual(str(UUID(proposal["id"])), proposal["id"])
        self.assertIsNone(self.store.pending("two"))
        self.assertIsNone(self.store.get("two", proposal["id"]))
        with self.assertRaises(ValueError):
            self.store.begin("two", proposal["id"])
        self.assertEqual(self.store.pending("one")["id"], proposal["id"])

    def test_new_proposal_supersedes_previous_and_representing_does_not(self):
        first = self.store.propose("one", self.action)
        repeated = self.store.propose("one", dict(self.action, proposal_id=first["id"]))
        self.assertEqual(first, repeated)
        second = self.store.propose("one", {"action": "type_text", "text": "hello"})
        self.assertEqual(self.store.get("one", first["id"])["status"], "superseded")
        self.assertEqual(self.store.pending("one")["id"], second["id"])
        with self.assertRaises(ValueError):
            self.store.begin("one", first["id"])
        with self.assertRaises(ValueError):
            self.store.propose("one", dict(self.action, app="calculator", proposal_id=first["id"]))

    def test_pending_expires_at_ttl_and_cannot_restart(self):
        proposal = self.store.propose("one", self.action)
        self.now += 299
        self.assertIsNotNone(self.store.pending("one"))
        self.now += 1
        self.assertIsNone(self.store.pending("one"))
        self.assertEqual(self.store.get("one", proposal["id"])["status"], "expired")
        with self.assertRaises(ValueError):
            self.store.begin("one", proposal["id"])

    def test_begin_is_atomic_and_completed_cannot_execute_again(self):
        proposal = self.store.propose("one", self.action)

        def attempt(_):
            try:
                return self.store.begin("one", proposal["id"])["status"]
            except ValueError:
                return "rejected"

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(16)))
        self.assertEqual(results.count("executing"), 1)
        self.store.finish("one", proposal["id"], "completed", {"ok": True})
        with self.assertRaises(ValueError):
            self.store.begin("one", proposal["id"])
        with self.assertRaises(ValueError):
            self.store.finish("one", proposal["id"], "completed", {})

    def test_cancel_only_pending_and_does_not_cancel_other_sessions(self):
        proposal = self.store.propose("one", self.action)
        self.assertIsNone(self.store.cancel("two", proposal["id"]))
        self.assertEqual(self.store.cancel("one")["status"], "cancelled")
        self.assertIsNone(self.store.cancel("one", proposal["id"]))
        with self.assertRaises(ValueError):
            self.store.begin("one", proposal["id"])
        next_proposal = self.store.propose("one", self.action)
        self.store.begin("one", next_proposal["id"])
        self.assertIsNone(self.store.cancel("one", next_proposal["id"]))

    def test_failed_outcome_and_pending_are_authoritative_context(self):
        proposal = self.store.propose("one", self.action)
        with self.assertRaises(ValueError):
            self.store.finish("one", proposal["id"], "completed", {})
        self.store.begin("one", proposal["id"])
        self.now += 500
        # An in-flight action is not changed into a new executable proposal by TTL.
        self.assertEqual(self.store.get("one", proposal["id"])["status"], "executing")
        self.store.finish("one", proposal["id"], "failed", {"error": "Notepad could not start"})
        next_proposal = self.store.propose("one", {"action": "open_app", "app": "calculator"})
        context = self.store.context("one")
        self.assertEqual(context["pending"]["id"], next_proposal["id"])
        self.assertEqual(context["recent_outcomes"][0]["status"], "failed")
        self.assertEqual(context["recent_outcomes"][0]["result"]["error"], "Notepad could not start")

    def test_input_and_all_responses_are_detached_copies(self):
        action = {"action": "write_note", "details": {"lines": ["original"]}}
        proposal = self.store.propose("one", action)
        action["details"]["lines"].append("input mutation")
        proposal["action"]["details"]["lines"].append("output mutation")
        pending = self.store.pending("one")
        self.assertEqual(pending["action"]["details"]["lines"], ["original"])
        pending["action"]["details"]["lines"].append("pending mutation")
        self.store.begin("one", proposal["id"])
        result = {"written": ["original"]}
        finished = self.store.finish("one", proposal["id"], "completed", result)
        result["written"].append("input mutation")
        finished["result"]["written"].append("output mutation")
        context = self.store.context("one")
        context["recent_outcomes"][0]["result"]["written"].append("context mutation")
        stored = self.store.get("one", proposal["id"])
        self.assertEqual(stored["result"]["written"], ["original"])
        self.assertEqual(stored["action"]["details"]["lines"], ["original"])

    def test_session_and_record_bounds_and_lru(self):
        store = ActionStore(max_sessions=2, max_records=2)
        first = store.propose("one", self.action)
        store.propose("one", self.action)
        latest = store.propose("one", self.action)
        self.assertIsNone(store.get("one", first["id"]))
        store.propose("two", self.action)
        self.assertEqual(store.pending("one")["id"], latest["id"])
        store.propose("three", self.action)
        self.assertIsNone(store.pending("two"))
        self.assertIsNotNone(store.pending("one"))
        self.assertEqual(len(store._sessions), 2)
        self.assertTrue(all(len(records) <= 2 for records in store._sessions.values()))

    def test_json_values_and_invalid_tokens_are_rejected(self):
        for session_id in ["", None, "x" * 257]:
            with self.assertRaises(ValueError):
                self.store.propose(session_id, self.action)
        for action in [{}, [], {"value": object()}, {"value": float("nan")}]:
            with self.assertRaises(ValueError):
                self.store.propose("one", action)
        with self.assertRaises(ValueError):
            self.store.propose("one", dict(self.action, proposal_id="unknown"))

    def test_context_limits_recent_results_and_long_text(self):
        for _ in range(5):
            proposal = self.store.propose("one", self.action)
            self.store.begin("one", proposal["id"])
            self.store.finish("one", proposal["id"], "completed", {"text": "x" * 5000})
            self.now += 1
        context = self.store.context("one")
        self.assertEqual(len(context["recent_outcomes"]), 3)
        self.assertLess(len(context["recent_outcomes"][0]["result"]["text"]), 1700)


if __name__ == "__main__":
    unittest.main()
