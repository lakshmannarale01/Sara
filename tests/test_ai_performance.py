"""Offline regressions for response budgets, provider streaming and recovery."""

from collections import deque
import json
import os
import threading
import unittest
from unittest.mock import Mock, patch

from sara_app import ai


class JsonLineResponse:
    """Small Ollama response stand-in; it never opens a socket."""

    def __init__(self, events, failure=None):
        self.events = events
        self.failure = failure

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __iter__(self):
        for event in self.events:
            yield (json.dumps(event) + "\n").encode()
        if self.failure:
            raise self.failure


class AiPerformanceTests(unittest.TestCase):
    def setUp(self):
        # Every storage/provider boundary is mocked, including for a test that
        # accidentally takes a different provider branch.
        patches = {
            "log": patch.object(ai, "log"),
            "console": patch.object(ai, "console_trace"),
            "conversations": patch.object(ai, "read_conversations", return_value=[]),
            "memories": patch.object(ai, "read_memories", return_value=[]),
            "capabilities": patch.object(ai, "capability_snapshot", return_value={
                "chat": {"status": "available", "risk": "low"},
                "email": {"status": "partial", "scope": "Reviewable drafts only; never sends mail"},
                "screen_vision": {"status": "planned", "scope": "Not implemented"},
            }),
            "urlopen": patch.object(ai.urllib.request, "urlopen", side_effect=AssertionError("Unexpected provider access")),
        }
        for name, patcher in patches.items():
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        for patcher in (
            patch.dict(os.environ, {}, clear=True),
            patch.object(ai, "CONVERSATION_HISTORY", []),
            patch.object(ai, "_ollama_retry_at", 0.0),
            patch.object(ai, "_metrics", deque(maxlen=20)),
            patch.object(ai, "_request_state", threading.local()),
            patch.object(ai, "_ask_lock", threading.Lock()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def use_response(self, response):
        self.urlopen.side_effect = None
        self.urlopen.return_value = response

    def test_oversized_conversation_is_bounded_and_keeps_newest_turn(self):
        self.conversations.return_value = [
            {"question": "old turn " + "x" * 20000, "answer": "y" * 20000},
            {"question": "latest turn " + "q" * 20000, "answer": "a" * 20000},
        ]
        with patch.dict(os.environ, {"SARA_HISTORY_CHARS": "180"}):
            context = ai.conversation_context()
        self.assertLessEqual(len(context), 180)
        self.assertIn("latest turn", context)
        self.assertNotIn("old turn", context)
        with patch.dict(os.environ, {"SARA_HISTORY_CHARS": "0"}):
            self.assertEqual(ai.conversation_context(), "")

    def test_in_memory_history_also_respects_budget(self):
        ai.CONVERSATION_HISTORY.extend([
            ("user", "Earlier " + "x" * 10000), ("assistant", "y" * 10000),
            ("user", "Newest request"), ("assistant", "Latest response"),
        ])
        with patch.dict(os.environ, {"SARA_HISTORY_CHARS": "80"}):
            context = ai.conversation_context()
        self.assertLessEqual(len(context), 80)
        self.assertIn("Newest request", context)
        self.assertIn("Latest response", context)
        self.assertNotIn("Earlier", context)

    def test_compact_prompt_preserves_partial_and_unavailable_constraints(self):
        self.memories.return_value = [{"text": "long preference " + "x" * 2000} for _ in range(20)]
        instructions = ai.build_instructions("email")
        capability_text = instructions.split("\nCapabilities: ", 1)[1].split("\nApproved memories: ", 1)[0]
        capabilities = json.loads(capability_text)
        self.assertEqual(capabilities["ready"], ["chat"])
        self.assertEqual(capabilities["limited"]["email"], "Reviewable drafts only; never sends mail")
        self.assertEqual(capabilities["unavailable"], ["screen_vision"])
        memories = json.loads(instructions.split("\nApproved memories: ", 1)[1])
        self.assertLessEqual(len(memories), 6)
        self.assertTrue(all(len(memory) <= 180 for memory in memories))
        self.assertLess(len(instructions), 3000)

    def test_routine_and_detailed_output_have_different_bounded_limits(self):
        routine = ai.output_limit("Suggest a short title")
        detailed = ai.output_limit("Explain fully, step by step")
        self.assertGreater(detailed, routine)
        self.assertLessEqual(routine, 256)
        self.assertLessEqual(detailed, 1024)
        with patch.dict(os.environ, {"SARA_MAX_TOKENS": "99999", "SARA_DETAILED_TOKENS": "-5"}):
            self.assertEqual(ai.output_limit("A short title"), 2048)
            self.assertEqual(ai.output_limit("Explain fully"), 64)
        with patch.dict(os.environ, {"SARA_MAX_TOKENS": "invalid"}):
            self.assertEqual(ai.output_limit("A short title"), routine)

    def test_greeting_is_immediate_and_bypasses_both_models(self):
        chunks = []
        with patch.object(ai, "ask_ollama") as ollama, patch.object(ai, "ask_openai") as cloud:
            reply, provider = ai.ask("Hello SARA!", chunks.append)
        self.assertEqual(provider, "instant-local")
        self.assertEqual("".join(chunks), reply)
        ollama.assert_not_called()
        cloud.assert_not_called()
        self.urlopen.assert_not_called()
        self.assertEqual(ai.request_performance()["first_token_ms"], 0)

    def test_ollama_stream_delivers_deltas_and_combines_the_final_answer(self):
        self.use_response(JsonLineResponse([
            {"response": "Hello "},
            {"response": "world!"},
            {"done": True, "eval_count": 2, "eval_duration": 1000000000, "prompt_eval_count": 10},
        ]))
        chunks = []
        reply = ai.ask_ollama("Suggest a title", chunks.append)
        self.assertEqual(chunks, ["Hello ", "world!"])
        self.assertEqual(reply, "Hello world!")
        request = self.urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertIs(payload["stream"], True)
        self.assertGreater(payload["options"]["num_predict"], 0)
        self.assertIn("keep_alive", payload)
        self.assertEqual(ai.request_performance()["output_tokens"], 2)
        self.assertIs(ai.request_performance()["incomplete"], False)

    def test_failure_cooldown_skips_repeated_unavailable_provider_calls(self):
        self.urlopen.side_effect = TimeoutError("local provider unavailable")
        with patch.object(ai.time, "monotonic", return_value=100):
            self.assertIsNone(ai.ask_ollama("First request"))
        with patch.object(ai.time, "monotonic", return_value=104):
            self.assertIsNone(ai.ask_ollama("Second request"))
        self.assertEqual(self.urlopen.call_count, 1)
        with patch.object(ai.time, "monotonic", return_value=116):
            self.assertIsNone(ai.ask_ollama("Third request"))
        self.assertEqual(self.urlopen.call_count, 2)

    def test_partial_stream_failure_keeps_partial_without_mixing_cloud_reply(self):
        self.use_response(JsonLineResponse([
            {"response": "Partial "}, {"response": "answer"},
        ], failure=TimeoutError("upstream stopped responding")))
        chunks = []
        with patch.object(ai, "ask_openai") as cloud:
            reply, provider = ai.ask("Describe the situation", chunks.append)
        self.assertEqual((reply, provider), ("Partial answer", "ollama"))
        self.assertEqual(chunks, ["Partial ", "answer"])
        cloud.assert_not_called()
        self.assertTrue(ai.request_performance()["incomplete"])

    def test_upstream_connection_reset_preserves_partial_instead_of_client_abort(self):
        self.use_response(JsonLineResponse([
            {"response": "Already delivered text"},
        ], failure=ConnectionResetError("provider reset its connection")))
        chunks = []
        with patch.object(ai, "ask_openai") as cloud:
            reply, provider = ai.ask("Describe the situation", chunks.append)
        self.assertEqual((reply, provider), ("Already delivered text", "ollama"))
        self.assertEqual(chunks, [reply])
        self.assertTrue(ai.request_performance()["incomplete"])
        cloud.assert_not_called()
        self.assertFalse(ai._ask_lock.locked())

    def test_stream_eof_without_done_event_is_marked_incomplete(self):
        self.use_response(JsonLineResponse([{"response": "Unfinished sentence"}]))
        chunks = []
        with patch.object(ai, "ask_openai") as cloud:
            reply, provider = ai.ask("Describe the situation", chunks.append)
        self.assertEqual((reply, provider), ("Unfinished sentence", "ollama"))
        self.assertEqual(chunks, [reply])
        self.assertTrue(ai.request_performance()["incomplete"])
        cloud.assert_not_called()

    def test_callback_disconnection_propagates_and_releases_generation_lock(self):
        for disconnected in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            with self.subTest(exception=disconnected.__name__):
                self.use_response(JsonLineResponse([{"response": "First word"}]))
                callback = Mock(side_effect=disconnected("dashboard closed"))
                with patch.object(ai, "ask_openai") as cloud:
                    with self.assertRaises(ai.ClientDisconnected) as raised:
                        ai.ask("Describe the situation", callback)
                self.assertIsInstance(raised.exception.__cause__, disconnected)
                cloud.assert_not_called()
                self.assertFalse(ai._ask_lock.locked())


if __name__ == "__main__":
    unittest.main()
