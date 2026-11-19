"""Filesystem locations for source checkouts and the installed (frozen) app."""
import glob
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
WINDOWS_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = WINDOWS_DIR.parent
MODEL_NAME = "faster-whisper-small"


def config_dir():
    """Per-user settings, hints and log: %APPDATA%\\murdic."""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "murdic"


def app_dir():
    """Folder holding murdic.exe (frozen) or windows/ (source)."""
    return Path(sys.executable).resolve().parent if FROZEN else WINDOWS_DIR


def resource_dir():
    """Bundled read-only data (PyInstaller's _internal folder when frozen)."""
    return Path(getattr(sys, "_MEIPASS", WINDOWS_DIR))


def bundled_model():
    """A complete model next to the app (custom builds) or downloaded on first run."""
    from .download import model_dir, model_ready
    for path in (resource_dir() / "models" / MODEL_NAME, model_dir()):
        if model_ready(path):
            return path
    return None


def icon_png():
    for path in (resource_dir() / "assets" / "murdic.png", REPO_DIR / "mac" / "assets" / "murdic.png"):
        if path.exists():
            return path
    return None


def cuda_dirs():
    """Folders that may hold cuBLAS DLLs: downloaded on first run
    (%LOCALAPPDATA%\\murdic\\cuda), next to the app, or a development venv's NVIDIA wheels."""
    from .download import cuda_dir
    found = [cuda_dir(), app_dir() / "cuda"]
    if not FROZEN:
        pattern = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "*", "bin")
        found += [Path(p) for p in sorted(glob.glob(pattern))]
    return [p for p in found if p.is_dir()]
