# PyInstaller spec: onedir build with two executables sharing one runtime.
#   murdic.exe      tray app (no console)
#   murdic-cli.exe  console: `wav`, `devices`, `benchmark`
# Run through windows\build.ps1, which prepares build\murdic.ico and the model folder.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

windows = Path(SPECPATH)
repo = windows.parent
model = repo / "build" / "models" / "faster-whisper-small"
if not (model / "model.bin").exists():
    raise SystemExit(f"Model not prepared: {model} (run windows\\build.ps1)")

datas = (collect_data_files("faster_whisper") + collect_data_files("soundcard")
         + [(str(repo / "mac" / "assets" / "murdic.png"), "assets"),
            (str(model), "models/faster-whisper-small"),
            (str(repo / "LICENSE"), ".")])
binaries = collect_dynamic_libs("ctranslate2")

a = Analysis(
    [str(windows / "murdic.py")],
    pathex=[str(windows), str(repo)],
    binaries=binaries,
    datas=datas,
    hiddenimports=["dictate.cleanup", "pystray._win32", "PIL._tkinter_finder"],
    excludes=["torch", "tensorflow", "matplotlib", "scipy", "pandas", "IPython", "pytest",
              "dictate.backend", "murmur", "nvidia"],
    noarchive=False,
)
pyz = PYZ(a.pure)
icon = str(repo / "build" / "murdic.ico")
common = dict(debug=False, bootloader_ignore_signals=False, strip=False, upx=False, icon=icon)
app = EXE(pyz, a.scripts, [], exclude_binaries=True, name="murdic", console=False, **common)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="murdic-cli", console=True, **common)
COLLECT(app, cli, a.binaries, a.datas, strip=False, upx=False, name="murdic")
