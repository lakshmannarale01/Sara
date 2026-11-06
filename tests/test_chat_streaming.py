"""Exercise chat response framing without sockets, models, or persisted data."""

import io
import json
import unittest
from unittest.mock import Mock, patch

from sara_app import server


class DisconnectingWriter(io.BytesIO):
    def __init__(self, allowed_writes):
        super().__init__()
        self.allowed_writes = allowed_writes
        self.write_count = 0

    def write(self, value):
        self.write_count += 1
        if self.write_count > self.allowed_writes:
            raise BrokenPipeError("client closed response")
        return super().write(value)


class ChatStreamingTests(unittest.TestCase):
    def setUp(self):
        # These are the only persistence paths used by /api/chat replies.
        self.append = self.enter_patch("append_conversation")
        self.activity = self.enter_patch("log")
        self.timing = self.enter_patch("request_performance", return_value={"first_token_ms": 12, "output_tokens": 7})
        self.ask = self.enter_patch("ask")

    def enter_patch(self, name, **kwargs):
        patcher = patch.object(server, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def handler(self, message="Explain photosynthesis in two sentences.", accept="application/x-ndjson", writer=None):
        handler = object.__new__(server.Handler)
        body = json.dumps({"message": message}).encode()
        handler.path = "/api/chat"
        handler.headers = {"Content-Length": str(len(body)), "Accept": accept}
        handler.rfile = io.BytesIO(body)
        handler.wfile = writer if writer is not None else io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.trace = Mock()
        return handler

    @staticmethod
    def streaming_answer(message, on_token):
        if on_token:
            on_token("Plants use ")
            on_token("sunlight.")
        return "Plants use sunlight.", "ollama"

    def test_ndjson_chat_has_start_delta_done_and_final_timing(self):
        self.ask.side_effect = self.streaming_answer
        handler = self.handler()

        handler.do_POST()

        events = [json.loads(line) for line in handler.wfile.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["start", "delta", "delta", "done"])
        self.assertEqual("".join(event["text"] for event in events if event["type"] == "delta"), events[-1]["reply"])
        self.assertEqual(events[-1]["provider"], "ollama")
        self.assertEqual(events[-1]["timing"]["first_token_ms"], 12)
        self.assertEqual(events[-1]["timing"]["output_tokens"], 7)
        self.assertGreaterEqual(events[-1]["timing"]["total_ms"], 0)
        handler.send_response.assert_called_once_with(200)
        handler.send_header.assert_any_call("Content-Type", "application/x-ndjson; charset=utf-8")
        handler.end_headers.assert_called_once()
        self.assertTrue(handler.close_connection)
        self.append.assert_called_once()
        self.activity.assert_called_once()

    def test_json_clients_receive_one_json_object_without_stream_callback(self):
        self.ask.side_effect = self.streaming_answer
        handler = self.handler(accept="application/json")

        handler.do_POST()

        result = json.loads(handler.wfile.getvalue())
        self.assertEqual(result["reply"], "Plants use sunlight.")
        self.assertNotIn("type", result)
        self.ask.assert_called_once_with("Explain photosynthesis in two sentences.", None)
        handler.send_response.assert_called_once_with(200)
        handler.send_header.assert_any_call("Content-Type", "application/json; charset=utf-8")
        self.assertIn("timing", result)

    def test_deterministic_task_query_stays_json_and_does_not_call_model(self):
        self.enter_patch("read_tasks", return_value=[{"id": "1", "text": "Finish draft", "status": "pending"}])
        handler = self.handler(message="tasks dikhao")

        handler.do_POST()

        result = json.loads(handler.wfile.getvalue())
        self.assertEqual(result["provider"], "task-list")
        self.assertIn("Finish draft", result["reply"])
        self.assertNotIn("type", result)
        self.ask.assert_not_called()
        self.timing.assert_not_called()
        handler.send_header.assert_any_call("Content-Type", "application/json; charset=utf-8")

    def test_disconnect_during_delta_stops_callback_and_does_not_send_second_response(self):
        continued = []

        def answer(message, on_token):
            on_token("first")
            on_token("second")
            continued.append(True)
            return "firstsecond", "ollama"

        self.ask.side_effect = answer
        writer = DisconnectingWriter(allowed_writes=2)  # start + first delta
        handler = self.handler(writer=writer)

        handler.do_POST()

        events = [json.loads(line) for line in writer.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["start", "delta"])
        self.assertEqual(continued, [])
        handler.send_response.assert_called_once_with(200)
        self.append.assert_not_called()
        self.activity.assert_not_called()
        handler.trace.assert_called_once_with("Client disconnected; stopped delivering this generation")

    def test_model_error_after_stream_start_is_error_event_with_one_response(self):
        def answer(message, on_token):
            on_token("partial")
            raise ValueError("generation unavailable")

        self.ask.side_effect = answer
        handler = self.handler()

        handler.do_POST()

        events = [json.loads(line) for line in handler.wfile.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["start", "delta", "error"])
        self.assertEqual(events[-1]["error"], "generation unavailable")
        handler.send_response.assert_called_once_with(200)
        self.append.assert_not_called()
        self.activity.assert_not_called()


if __name__ == "__main__":
    unittest.main()
