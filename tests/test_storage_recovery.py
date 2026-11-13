"""Recover local list data without overwriting its original malformed bytes."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sara_app import storage


class StorageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="sara-storage-recovery-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "conversations.json"
        self.enter_patch(storage, "CONVERSATION_FILE", self.path)
        self.enter_patch(storage, "console_trace")

    def enter_patch(self, target, name, *args, **kwargs):
        patcher = patch.object(target, name, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def backups(self):
        return list(self.path.parent.glob(self.path.name + ".recovery-*.bak"))

    def assert_recovered(self, original, expected):
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), expected)
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_valid_conversation_list_round_trips_without_a_backup(self):
        first = {"question": "नमस्ते", "answer": "मैं सारा हूँ।"}
        self.path.write_text(json.dumps([first], ensure_ascii=False), encoding="utf-8")
        second = {"question": "Next question", "answer": "Next answer"}

        storage.append_conversation(second)

        self.assertEqual(storage.read_conversations(), [first, second])
        self.assertEqual(self.backups(), [])

    def test_partial_json_is_preserved_before_appending_a_new_turn(self):
        original = b'[{"question":"recoverable conversation"}, {"unfinished":'
        self.path.write_bytes(original)
        new_turn = {"question": "New question", "answer": "New answer"}

        self.assertEqual(storage.read_conversations(), [])
        storage.append_conversation(new_turn)

        self.assert_recovered(original, [new_turn])

    def test_non_utf8_bytes_are_read_safely_and_preserved_on_write(self):
        original = b'[{"question":"legacy \xff text"}]'
        self.path.write_bytes(original)
        new_turn = {"question": "New question", "answer": "New answer"}

        self.assertEqual(storage.read_conversations(), [])
        storage.append_conversation(new_turn)

        self.assert_recovered(original, [new_turn])

    def test_wrong_top_level_shape_is_preserved_before_replacement(self):
        original = b'{"important_legacy_data":"keep all of these bytes"}'
        self.path.write_bytes(original)
        new_turn = {"question": "New", "answer": "Reply"}

        storage.append_conversation(new_turn)

        self.assert_recovered(original, [new_turn])

    def test_malformed_rows_are_preserved_while_valid_rows_survive_repair(self):
        first = {"question": "Existing", "answer": "Kept"}
        original = json.dumps([first, "legacy record", None, 42]).encode("utf-8")
        self.path.write_bytes(original)
        new_turn = {"question": "New", "answer": "Reply"}

        self.assertEqual(storage.read_conversations(), [first])
        storage.append_conversation(new_turn)

        self.assert_recovered(original, [first, new_turn])

    def test_backup_publication_failure_leaves_original_untouched(self):
        original = b'{"unreadable_shape":"must survive"}'
        self.path.write_bytes(original)
        with patch.object(storage.os, "replace", side_effect=PermissionError("backup denied")):
            with self.assertRaises(PermissionError):
                storage.append_conversation({"question": "New"})

        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.backups(), [])
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_source_read_failure_aborts_replacement(self):
        original = b'[{"question":"still here"}]'
        self.path.write_bytes(original)
        with patch.object(Path, "read_bytes", side_effect=PermissionError("source denied")):
            with self.assertRaises(PermissionError):
                storage._write_json_atomic(self.path, [{"question": "Replacement"}])

        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.backups(), [])
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_replacement_failure_keeps_original_and_the_completed_backup(self):
        original = b'[{"unfinished":'
        self.path.write_bytes(original)
        replace = storage.os.replace

        def fail_source_replace(source, target):
            if Path(target) == self.path:
                raise PermissionError("replacement denied")
            return replace(source, target)

        with patch.object(storage.os, "replace", side_effect=fail_source_replace):
            with self.assertRaises(PermissionError):
                storage.append_conversation({"question": "New"})

        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual([backup.read_bytes() for backup in self.backups()], [original])
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_separate_recovery_episodes_never_overwrite_a_previous_backup(self):
        originals = [b'{"first":"legacy"}', b'{"second":"different legacy"}']
        for original in originals:
            self.path.write_bytes(original)
            storage.append_conversation({"question": "New"})

        self.assertCountEqual([backup.read_bytes() for backup in self.backups()], originals)
        self.assertEqual(len({backup.name for backup in self.backups()}), 2)

    def test_missing_file_can_be_created_without_a_recovery_backup(self):
        new_turn = {"question": "First question", "answer": "First answer"}

        storage.append_conversation(new_turn)

        self.assertEqual(storage.read_conversations(), [new_turn])
        self.assertEqual(self.backups(), [])


if __name__ == "__main__":
    unittest.main()
