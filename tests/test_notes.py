from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from sara_app import notes


class NotepadNoteTests(unittest.TestCase):
    def setUp(self):
        # Windows Python 3.14's private TemporaryDirectory ACL excludes sandbox users.
        # A normal workspace directory inherits the project's usable permissions.
        test_root = Path(__file__).resolve().parent
        self.temporary = test_root / f"notes-test-{uuid.uuid4().hex}"
        self.temporary.mkdir()
        self.addCleanup(shutil.rmtree, self.temporary)
        self.directory = self.temporary / "notes"
        self.patch_directory = patch.object(notes, "NOTES_DIR", self.directory)
        self.patch_directory.start()
        self.addCleanup(self.patch_directory.stop)
        self.patch_launch = patch.object(notes.subprocess, "Popen")
        self.launch = self.patch_launch.start()
        self.addCleanup(self.patch_launch.stop)

    def test_utf8_text_is_verified_and_exact_file_is_launched(self):
        text = "Namaste! नमस्ते दोस्त 👋\r\nMera naam SARA hai.\n"
        result = notes.create_notepad_note(text, confirmed=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["file_written"])
        self.assertTrue(result["text_verified"])
        self.assertTrue(result["launch_requested"])
        self.assertFalse(result["window_verified"])
        self.assertEqual(notes.read_note(result["note_id"]), text)
        self.assertEqual(Path(result["file_path"]).read_bytes(), text.encode("utf-8"))
        self.launch.assert_called_once_with(["notepad.exe", result["file_path"]], shell=False)

    def test_confirmation_is_required_before_any_file_or_launch(self):
        for confirmation in (False, None, "yes", 1):
            with self.subTest(confirmation=confirmation):
                result = notes.create_notepad_note("Draft", confirmed=confirmation)
                self.assertTrue(result["requires_confirmation"])
                self.assertFalse(result["file_written"])
                self.assertFalse(result["launch_requested"])
        self.assertFalse(self.directory.exists())
        self.launch.assert_not_called()

    def test_unique_files_preserve_previous_notes(self):
        first = notes.create_notepad_note("First", confirmed=True)
        second = notes.create_notepad_note("Second", confirmed=True)

        self.assertNotEqual(first["note_id"], second["note_id"])
        self.assertEqual(notes.read_note(first["note_id"]), "First")
        self.assertEqual(notes.read_note(second["note_id"]), "Second")

    def test_filename_collision_does_not_overwrite_existing_file(self):
        first_id, second_id = "a" * 32, "b" * 32
        self.directory.mkdir()
        existing = self.directory / f"{first_id}.txt"
        existing.write_text("Keep me", encoding="utf-8")
        with patch.object(notes.uuid, "uuid4", side_effect=[
            SimpleNamespace(hex=first_id), SimpleNamespace(hex=second_id)
        ]):
            result = notes.create_notepad_note("New text", confirmed=True)

        self.assertEqual(existing.read_text(encoding="utf-8"), "Keep me")
        self.assertEqual(result["note_id"], second_id)
        self.assertEqual(notes.read_note(second_id), "New text")

    def test_launch_failure_preserves_verified_note_and_reports_partial_result(self):
        self.launch.side_effect = FileNotFoundError("Notepad unavailable")
        result = notes.create_notepad_note("Saved despite launch failure", confirmed=True)

        self.assertFalse(result["ok"])
        self.assertTrue(result["file_written"])
        self.assertTrue(result["text_verified"])
        self.assertFalse(result["launch_requested"])
        self.assertFalse(result["window_verified"])
        self.assertIn("recovery", result)
        self.assertEqual(notes.read_note(result["note_id"]), "Saved despite launch failure")

    def test_failed_readback_never_launches_notepad(self):
        with patch.object(notes, "read_note", return_value="Different text"):
            result = notes.create_notepad_note("Draft", confirmed=True)
        self.assertFalse(result["ok"])
        self.assertTrue(result["file_written"])
        self.assertFalse(result["text_verified"])
        self.launch.assert_not_called()

    def test_invalid_drafts_are_rejected_without_io(self):
        for text in ("", " \n\t", None, "x" * (notes.MAX_NOTE_CHARS + 1)):
            with self.subTest(text_type=type(text).__name__):
                with self.assertRaises(ValueError):
                    notes.create_notepad_note(text, confirmed=True)
        self.assertFalse(self.directory.exists())
        self.launch.assert_not_called()

    def test_read_helper_rejects_paths_and_traversal(self):
        for note_id in ("../private", "..\\private", "C:\\private.txt", "a" * 32 + ".txt", "a" * 31, None):
            with self.subTest(note_id=note_id):
                with self.assertRaises(ValueError):
                    notes.read_note(note_id)
        self.assertFalse(self.directory.exists())

    def test_missing_note_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            notes.read_note("a" * 32)


if __name__ == "__main__":
    unittest.main()
