#!/usr/bin/env python3
"""Build build/release/murdic-<version>-arm64.dmg (and murdic-arm64.dmg, the same file without the version).

The app carries its own arm64 Python (python-build-standalone) with the packages pinned in
scripts/release-requirements.txt, so a user only drags murdic.app to Applications. The Whisper model
is not included; the app downloads it on first run. Run from the repository root: make dmg
"""
from __future__ import annotations

import hashlib
import os
import plistlib
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "build/release"
CACHE = ROOT / "build/cache"
WORK = RELEASE / "work"
APP = WORK / "murdic.app"
RUNTIME = APP / "Contents/Resources/python"
# Read only: its designated requirement is the signer that an update must keep (see scripts/sign-local).
INSTALLED = Path.home() / "Applications/murdic.app"

# python-build-standalone 3.14.10 (release 20261110), aarch64-apple-darwin, install_only.
# The checksum is copied from that release's SHA256SUMS file.
PBS_NAME = "cpython-3.14.10+20261110-aarch64-apple-darwin-install_only.tar.gz"
PBS_URL = ("https://github.com/astral-sh/python-build-standalone/releases/download/20261110/"
           "cpython-3.14.10%2B20261110-aarch64-apple-darwin-install_only.tar.gz")
PBS_SHA256 = "42031ed5f0d38777335252c8c77d64708c8010dd67c128246bdec25000672666"
# Installed with --no-deps: mlx-whisper declares torch, but murdic never imports torch_whisper.
MLX_WHISPER = "mlx-whisper==0.4.3"
# Murmur core at the commit the README links for its license note.
MURMUR = ("murmur @ git+https://github.com/jkf87/murmur.git@0c0c409de45504686ad080bf3c576816444b4fa4"
          "#subdirectory=core")
# mlx's arm64 wheels start at macOS 14.0.
MIN_MACOS = "14.0"
TOOL_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
RUNTIME_BIN_KEEP = {"python3", "python3.14"}
MACHO_MAGIC = {b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
SYSTEM_PREFIXES = ("/usr/lib", "/System/")
LAYOUT = """
tell application "Finder"
  tell disk "murdic"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set bounds of container window to {120, 120, 760, 520}
    set viewOptions to icon view options of container window
    set arrangement of viewOptions to not arranged
    set icon size of viewOptions to 128
    set background picture of viewOptions to file ".background:background.png"
    set position of item "murdic.app" of container window to {160, 190}
    set position of item "Applications" of container window to {480, 190}
    update without registering applications
    delay 2
    close
  end tell
end tell
"""


def run(*command, env: dict | None = None) -> None:
    print("+", " ".join(str(part) for part in command), flush=True)
    subprocess.run([str(part) for part in command], check=True, env=env)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_runtime() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / PBS_NAME
    if not archive.exists() or sha256(archive) != PBS_SHA256:
        partial = archive.with_name(archive.name + ".part")
        print("downloading", PBS_NAME, flush=True)
        with urllib.request.urlopen(PBS_URL, timeout=300) as response, partial.open("wb") as target:
            shutil.copyfileobj(response, target)
        partial.replace(archive)
    if sha256(archive) != PBS_SHA256:
        archive.unlink()
        raise SystemExit(f"checksum mismatch for {PBS_NAME}; the download was removed")
    return archive


def build_bundle(archive: Path) -> None:
    if WORK.exists():
        shutil.rmtree(WORK)  # build output only
    contents = APP / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir()
    shutil.copytree(ROOT / "dictate", contents / "Resources/dictate",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(ROOT / "build/murdic.icns", contents / "Resources/murdic.icns")
    info = plistlib.loads((ROOT / "mac/Info.plist").read_bytes())
    # Relative to the app bundle, so the same bundle works from /Applications or anywhere else.
    info["DictatePython"] = "Contents/Resources/python/bin/python3"
    info["LSMinimumSystemVersion"] = MIN_MACOS
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    sources = sorted(str(path) for path in (ROOT / "mac").glob("*.swift"))
    run("xcrun", "swiftc", "-O", "-target", f"arm64-apple-macos{MIN_MACOS}", *sources,
        "-o", contents / "MacOS" / info["CFBundleExecutable"])
    run("/usr/bin/tar", "-xzf", archive, "-C", contents / "Resources")


def install_packages() -> None:
    python = RUNTIME / "bin/python3"
    # Clean environment: nothing from the builder's shell or user site-packages may leak into the runtime.
    env = {"PATH": TOOL_PATH, "HOME": os.environ["HOME"], "LANG": "en_US.UTF-8",
           "PIP_CONFIG_FILE": os.devnull, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    pip = [python, "-s", "-m", "pip", "install", "--no-deps", "--no-compile",
           "--disable-pip-version-check", "--no-warn-script-location"]
    run(*pip, "-r", ROOT / "scripts/release-requirements.txt", env=env)
    run(*pip, MLX_WHISPER, env=env)
    run(*pip, MURMUR, env=env)


def remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def prune() -> None:
    # Only what murdic never loads: bytecode (the engine runs with PYTHONDONTWRITEBYTECODE), tests, Tk, pip,
    # headers, and the bin scripts. Packages stay complete; verify-release.py checks that the engine still imports.
    lib = RUNTIME / "lib"
    stdlib = lib / "python3.14"
    site = stdlib / "site-packages"
    doomed = [RUNTIME / "include", RUNTIME / "share", lib / "pkgconfig", lib / "libpython3.14.dylib",
              *lib.glob("lib*tcl*"), *lib.glob("tcl*"), *lib.glob("tk*"), *lib.glob("itcl*"), *lib.glob("thread*"),
              *stdlib.glob("config-*"), stdlib / "test", stdlib / "idlelib", stdlib / "tkinter",
              stdlib / "turtledemo", stdlib / "ensurepip", site / "pip", site / "README.txt",
              *site.glob("pip-*.dist-info"), *(stdlib / "lib-dynload").glob("_tkinter*.so")]
    doomed += [path for path in (RUNTIME / "bin").iterdir() if path.name not in RUNTIME_BIN_KEEP]
    doomed += [path for path in site.rglob("*") if path.is_dir() and path.name in {"tests", "test"}]
    for path in doomed:
        remove(path)
    for path in list(RUNTIME.rglob("__pycache__")):
        remove(path)
    for path in list(RUNTIME.rglob("*.pyc")):
        remove(path)


def macho_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as handle:
                if handle.read(4) in MACHO_MAGIC:
                    yield path


def output_lines(*command) -> list[str]:
    return subprocess.run([str(part) for part in command], capture_output=True, text=True, check=True).stdout.splitlines()


def scrub_load_paths() -> None:
    """Keep every load path inside the bundle or in system libraries.

    Some wheels carry placeholder install names (scipy's bundled dylibs use /DLC/...), and scipy's _fblas
    lists Homebrew gcc directories in its rpath. Both are rewritten here. Every touched file is then signed
    ad hoc, because editing a Mach-O invalidates its signature; the bundle is signed afterwards.
    """
    for path in macho_files(APP):
        edits = []
        identity = [line.strip() for line in output_lines("/usr/bin/otool", "-D", path)[1:]
                    if line.strip() and not line.rstrip().endswith(":")]
        if identity and identity[0].startswith("/") and not identity[0].startswith(SYSTEM_PREFIXES):
            edits += ["-id", f"@loader_path/{path.name}"]
        load = output_lines("/usr/bin/otool", "-l", path)
        for index, line in enumerate(load):
            if "cmd LC_RPATH" in line:
                rpath = load[index + 2].split("path ", 1)[1].split(" (offset")[0]
                if rpath.startswith("/") and not rpath.startswith(SYSTEM_PREFIXES):
                    edits += ["-delete_rpath", rpath]
        if edits:
            print("rewrite load paths in", path.relative_to(APP), edits, flush=True)
            run("/usr/bin/install_name_tool", *edits, path)
            run("/usr/bin/codesign", "--force", "--sign", "-", path)


def sign() -> None:
    run("/usr/bin/xattr", "-cr", APP)
    # Same identity and designated requirement as the development build (scripts/sign-local).
    run(ROOT / "scripts/sign-local", APP, INSTALLED)
    run("/usr/bin/codesign", "--verify", "--deep", "--strict", APP)


def layout_window(volume: Path) -> None:
    background = volume / ".background/background.png"
    if not background.exists():
        raise SystemExit("background image is missing from the disk image")
    run("/usr/bin/osascript", "-e", LAYOUT)


def make_dmg(version: str) -> Path:
    stage = RELEASE / "dmg"
    shutil.rmtree(stage, ignore_errors=True)  # build output only
    (stage / ".background").mkdir(parents=True)
    run("/usr/bin/ditto", APP, stage / "murdic.app")
    (stage / "Applications").symlink_to("/Applications")
    tool = RELEASE / "dmg-background"
    run("xcrun", "swiftc", "-O", ROOT / "scripts/dmg-background.swift", "-o", tool)
    run(tool, stage / ".background/background.png")

    used_mb = sum(path.stat().st_size for path in stage.rglob("*") if path.is_file()) / 1e6
    raw = RELEASE / "murdic-rw.dmg"
    raw.unlink(missing_ok=True)
    run("/usr/bin/hdiutil", "create", "-quiet", "-srcfolder", stage, "-volname", "murdic", "-fs", "HFS+",
        "-format", "UDRW", "-size", f"{int(used_mb * 1.15) + 40}m", raw)
    volume = Path("/Volumes/murdic")
    if volume.exists():
        raise SystemExit("/Volumes/murdic is already mounted; eject it and run make dmg again")
    run("/usr/bin/hdiutil", "attach", raw, "-readwrite", "-noverify", "-noautoopen", "-quiet")
    try:
        layout_window(volume)
    finally:
        try:
            run("/usr/bin/hdiutil", "detach", volume, "-quiet")
        except subprocess.CalledProcessError:
            run("/usr/bin/hdiutil", "detach", volume, "-force", "-quiet")

    final = RELEASE / f"murdic-{version}-arm64.dmg"
    final.unlink(missing_ok=True)
    run("/usr/bin/hdiutil", "convert", raw, "-quiet", "-format", "UDZO", "-imagekey", "zlib-level=9", "-o", final)
    raw.unlink()
    shutil.rmtree(stage)
    # The version-less name is what the README and site link to; an APFS clone costs no extra space.
    alias = RELEASE / "murdic-arm64.dmg"
    alias.unlink(missing_ok=True)
    run("/bin/cp", "-c", final, alias)
    return final


def main() -> None:
    version = plistlib.loads((ROOT / "mac/Info.plist").read_bytes())["CFBundleShortVersionString"]
    archive = fetch_runtime()
    build_bundle(archive)
    install_packages()
    prune()
    scrub_load_paths()
    sign()
    dmg = make_dmg(version)
    print(f"bundle {sum(p.stat().st_size for p in APP.rglob('*') if p.is_file()) / 1e6:.1f} MB (unpacked)")
    print(f"DMG {dmg} {dmg.stat().st_size / 1e6:.1f} MB sha256={sha256(dmg)}")


if __name__ == "__main__":
    main()
