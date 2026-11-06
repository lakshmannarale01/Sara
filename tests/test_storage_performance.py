import io
import json
import unittest
from unittest.mock import Mock, patch

from sara_app import storage


class TrackingReader(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.bytes_read = 0
        self.read_sizes = []

    def read(self, size=-1):
        if size < 0:
            raise AssertionError("Activity reader must always bound its reads")
        self.read_sizes.append(size)
        result = super().read(size)
        self.bytes_read += len(result)
        return result


class RecentActivityTests(unittest.TestCase):
    def read_records(self, payload, limit=30):
        reader = TrackingReader(payload)
        log_path = Mock()
        log_path.open.return_value = reader
        with patch.object(storage, "LOG_FILE", log_path):
            records = storage.read_recent_activity(limit)
        log_path.open.assert_called_once_with("rb")
        return records, reader

    def test_returns_limited_records_newest_first_without_final_newline(self):
        payload = b'\n'.join(json.dumps({"id": i}).encode() for i in range(10))
        records, _ = self.read_records(payload, 3)
        self.assertEqual([record["id"] for record in records], [9, 8, 7])

    def test_utf8_record_survives_chunk_boundaries(self):
        text = "Namaste, \u0938\u093e\u0930\u093e! \U0001f44b " * 2000
        payload = (json.dumps({"id": 1, "text": text}, ensure_ascii=False) + "\n").encode("utf-8")
        records, reader = self.read_records(payload, 1)
        self.assertGreater(reader.bytes_read, storage._ACTIVITY_CHUNK_BYTES)
        self.assertEqual(records, [{"id": 1, "text": text}])

    def test_skips_malformed_or_partial_records_and_keeps_valid_ones(self):
        payload = b'{"id":1}\nnot-json\n[1,2]\n{"id":2}\n{"unfinished":'
        records, _ = self.read_records(payload)
        self.assertEqual(records, [{"id": 2}, {"id": 1}])

    def test_large_earlier_log_is_not_scanned_for_recent_records(self):
        payload = b'{"old":true}\n' * 300000
        payload += b''.join(json.dumps({"id": i}).encode() + b'\n' for i in range(30))
        records, reader = self.read_records(payload)
        self.assertEqual([record["id"] for record in records], list(reversed(range(30))))
        self.assertLessEqual(reader.bytes_read, storage._ACTIVITY_CHUNK_BYTES)

    def test_tail_byte_limit_skips_cut_leading_record(self):
        payload = b'{"id":1}\n' + b'x' * (storage._ACTIVITY_TAIL_BYTES + 10) + b'\n{"id":2}\n'
        records, reader = self.read_records(payload)
        self.assertEqual(records, [{"id": 2}])
        self.assertLessEqual(reader.bytes_read, storage._ACTIVITY_TAIL_BYTES)

    def test_empty_missing_and_invalid_limit_are_safe(self):
        self.assertEqual(self.read_records(b'')[0], [])
        missing = Mock()
        missing.open.side_effect = OSError("missing")
        with patch.object(storage, "LOG_FILE", missing):
            self.assertEqual(storage.read_recent_activity(), [])
            self.assertEqual(storage.read_recent_activity("bad"), [])
            self.assertEqual(storage.read_recent_activity(0), [])


if __name__ == "__main__":
    unittest.main()
