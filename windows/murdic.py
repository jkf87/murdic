"""Entry point for `python windows\\murdic.py` and the PyInstaller executables."""
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from murdic_win.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
