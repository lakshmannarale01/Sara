"""Explicit manual launch check. Creates one retained neutral verification note."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sara_app.notes import create_notepad_note, read_note


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch", action="store_true", help="Save and open a real verification note in Windows Notepad")
    if not parser.parse_args().launch:
        parser.error("Pass --launch explicitly; this test opens a real application.")
    text = "SARA WORKFLOW VERIFICATION\n\nThis is a neutral test note created by SARA's real Notepad tool.\nThe saved text was read back and verified before launching Notepad.\n\nHindi/Unicode check: नमस्ते! यह एक परीक्षण नोट है।\n"
    result = create_notepad_note(text, confirmed=True)
    assert result.get("ok") and result.get("text_verified"), result
    assert read_note(result["note_id"]) == text
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
