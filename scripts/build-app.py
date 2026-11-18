"""Build out of sight, verify, then atomically publish the single installed app."""
import ctypes
import fcntl
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
dest = Path(sys.argv[1]).absolute()
dest.parent.mkdir(parents=True, exist_ok=True)
# Serialize identity provisioning and replacement across concurrent make calls.
lock = (root / "build/install.lock").open("a")
fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

with (root / "mac/Info.plist").open("rb") as source:
    info = plistlib.load(source)
info["DictatePython"] = sys.argv[2]
if dest.exists():
    with (dest / "Contents/Info.plist").open("rb") as old:
        if plistlib.load(old).get("CFBundleIdentifier") != info["CFBundleIdentifier"]:
            sys.exit(f"Another app already uses {dest}")

with tempfile.TemporaryDirectory(prefix=".murdic-", suffix=".noindex", dir=dest.parent) as work:
    app = Path(work) / dest.name
    contents = app / "Contents"
    resources = contents / "Resources"
    binaries = contents / "MacOS"
    binaries.mkdir(parents=True)
    shutil.copytree(root / "dictate", resources / "dictate", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(root / "build/murdic.icns", resources / "murdic.icns")
    with (contents / "Info.plist").open("wb") as output:
        plistlib.dump(info, output)
    subprocess.run(["xcrun", "swiftc", "-O", *sorted((root / "mac").glob("*.swift")),
                    "-o", binaries / info["CFBundleExecutable"]], check=True)
    subprocess.run([root / "scripts/sign-local", app, dest], check=True)
    if dest.exists():
        # Darwin RENAME_SWAP keeps the previous installation intact until signing succeeds.
        rename = ctypes.CDLL(None, use_errno=True).renamex_np
        if rename(os.fsencode(app), os.fsencode(dest), 2) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
    else:
        app.rename(dest)
