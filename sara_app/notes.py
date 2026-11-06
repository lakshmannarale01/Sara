"""Save verified UTF-8 notes and request that Windows opens them in Notepad."""

from pathlib import Path
import re
import subprocess
import uuid

from .config import DATA_DIR


NOTES_DIR = DATA_DIR / "notes"
MAX_NOTE_CHARS = 6000
_NOTE_ID = re.compile(r"[0-9a-f]{32}\Z")


def _note_path(note_id: str) -> Path:
    if not isinstance(note_id, str) or not _NOTE_ID.fullmatch(note_id):
        raise ValueError("Invalid note ID.")
    directory = NOTES_DIR.resolve()
    path = directory / f"{note_id}.txt"
    # An existing link must not turn this read-only helper into arbitrary file access.
    if path.resolve().parent != directory:
        raise ValueError("Note path is outside the notes directory.")
    return path


def read_note(note_id: str) -> str:
    """Read one saved note by its opaque ID, never by a caller-supplied path."""
    with _note_path(note_id).open("r", encoding="utf-8", newline="") as note:
        return note.read()


def create_notepad_note(text: str, confirmed: bool = False) -> dict:
    """Create a new note, verify its contents, and request Notepad to open it.

    A successful process launch establishes only that Windows accepted the launch
    request. It does not establish that a visible Notepad window is present.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Note text cannot be blank.")
    if len(text) > MAX_NOTE_CHARS:
        raise ValueError(f"Note text must be at most {MAX_NOTE_CHARS} characters.")

    result = {
        "ok": False,
        "file_written": False,
        "text_verified": False,
        "launch_requested": False,
        "window_verified": False,
        "note_id": None,
    }
    if confirmed is not True:
        return {
            **result,
            "requires_confirmation": True,
            "risk": "This saves a new text file and opens it in Windows Notepad.",
            "result": "The note is ready for review; it has not been saved or opened.",
        }

    try:
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        # Exclusive creation keeps every existing note intact, including on collision.
        for _ in range(5):
            note_id = uuid.uuid4().hex
            path = _note_path(note_id)
            try:
                with path.open("x", encoding="utf-8", newline="") as note:
                    result.update(note_id=note_id, file_path=str(path))
                    note.write(text)
                break
            except FileExistsError:
                continue
        else:
            raise OSError("Could not allocate a unique note filename.")
        result["file_written"] = True
        if read_note(note_id) != text:
            result["result"] = "The saved note did not match its draft. Notepad was not opened."
            result["recovery"] = "Review the saved file before opening it."
            return result
        result["text_verified"] = True
    except (OSError, UnicodeError) as exc:
        result["result"] = "The note could not be saved and verified. Notepad was not opened."
        result["error"] = str(exc)
        return result

    try:
        subprocess.Popen(["notepad.exe", str(path)], shell=False)
    except (OSError, subprocess.SubprocessError) as exc:
        result["result"] = "The note was saved and verified, but Notepad could not be launched."
        result["error"] = str(exc)
        result["recovery"] = "Read the saved note in its preview or open the file_path manually."
        return result

    result.update(
        ok=True,
        launch_requested=True,
        result="The note was saved and verified, and Notepad was asked to open it. "
        "The visible window has not been verified.",
    )
    return result
