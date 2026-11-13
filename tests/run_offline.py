r"""Run offline regressions with all local SARA data redirected to temporary files.

Usage: .venv\Scripts\python.exe tests\run_offline.py
Live Notepad/browser-device smoke scripts and latency benchmarks are excluded.
"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True


def main():
    # Configure paths before importing storage, which initializes missing files.
    from sara_app import config
    with tempfile.TemporaryDirectory(prefix=".sara-offline-", dir=ROOT) as folder:
        isolated = Path(folder).resolve()
        if not isolated.is_relative_to(ROOT):
            raise RuntimeError("Test data must remain inside the project temporary folder.")
        previous_temp = tempfile.tempdir
        tempfile.tempdir = str(isolated)
        try:
            config.DATA_DIR = isolated
            for name, value in vars(config).copy().items():
                if name.endswith("_FILE") and isinstance(value, Path):
                    setattr(config, name, isolated / value.name)
            suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
            result = unittest.TextTestRunner(verbosity=1).run(suite)
            return 0 if result.wasSuccessful() else 1
        finally:
            tempfile.tempdir = previous_temp


if __name__ == "__main__":
    raise SystemExit(main())
