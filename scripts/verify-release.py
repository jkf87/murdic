#!/usr/bin/env python3
"""Check a release murdic.app for references outside the bundle, then run the engine the way the menu app does.

Usage: verify-release.py <murdic.app> <sample.wav> [--fresh-home]
  1. otool: every linked library and LC_RPATH is under /usr/lib, /System, or relative to the bundle.
  2. strings: no build-machine or development paths in Mach-O files or text files.
  3. sys.path and loaded module files are inside the bundle (python -s, env -i PATH=/usr/bin:/bin).
  4. Engine: `serve` with the menu app's JSON-lines protocol transcribes the WAV under env -i PATH=/usr/bin:/bin.
     --fresh-home gives the engine an empty HOME and HF_HOME, so the model is downloaded from scratch.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MACHO_MAGIC = {b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
TEXT_SUFFIXES = {".py", ".txt", ".plist", ".json", ".cfg", ".pth", ".toml", ".md", ".sh", ".pyi", ".ini"}
ALLOWED_LINK_PREFIXES = ("/usr/lib", "/System/Library/", "@rpath/", "@loader_path/", "@executable_path/")
# Failing patterns: Homebrew, the developer's home and checkout, Murmur's home checkout, the user's site-packages.
FORBIDDEN = [b"/opt/homebrew", b"/Users/conanssam-m4", b"/.murmur/", b"Library/Python/3", b"murmur-dictate"]
# Generic constants that ship inside CPython, numba, or CI debug strings. Counted for the report, not failing.
ADVISORY = [b"/usr/local/", b"/tmp/", b"/private/tmp", b"/Users/runner"]
# Matches of a FORBIDDEN pattern that are comments or docstrings, never opened (bundle-relative path -> patterns).
ALLOWED_STRINGS: dict[str, set[bytes]] = {
    # huggingface_hub explains its Homebrew detection in comments; the code only inspects sys.prefix.
    "Contents/Resources/python/lib/python3.14/site-packages/huggingface_hub/utils/_runtime.py": {b"/opt/homebrew"},
}
# The menu app's Engine.swift sets PYTHONDONTWRITEBYTECODE=1 too; without it the checks would write
# __pycache__ into the bundle they are checking.
TOOL_ENV = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
PROBE = """
import json, sys
import dictate.backend
files = sorted({getattr(module, "__file__", None) or "" for module in list(sys.modules.values())})
print(json.dumps({"sys_path": sys.path, "prefix": sys.prefix, "files": files}))
"""


def macho_files(app: Path):
    for path in sorted(app.rglob("*")):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as handle:
                if handle.read(4) in MACHO_MAGIC:
                    yield path


def check_linkage(app: Path) -> dict:
    count, links, flagged = 0, set(), []
    for path in macho_files(app):
        count += 1
        out = subprocess.run(["/usr/bin/otool", "-L", str(path)], capture_output=True, text=True, check=True).stdout
        for line in out.splitlines()[1:]:
            if not line.startswith("\t"):  # per-architecture headers of universal binaries
                continue
            name = line.strip().split(" (")[0]
            links.add(name)
            if not name.startswith(ALLOWED_LINK_PREFIXES):
                flagged.append(f"{path.relative_to(app)} -> {name}")
        load = subprocess.run(["/usr/bin/otool", "-l", str(path)], capture_output=True, text=True, check=True).stdout
        lines = load.splitlines()
        for index, line in enumerate(lines):
            if "cmd LC_RPATH" in line and index + 2 < len(lines):
                rpath = lines[index + 2].split("path ", 1)[-1].split(" (offset")[0].strip()
                if rpath.startswith("/") and not rpath.startswith("/usr/lib") and not rpath.startswith("/System"):
                    flagged.append(f"{path.relative_to(app)} LC_RPATH {rpath}")
    external = sorted(name for name in links if not name.startswith(("@", "/usr/lib/", "/System/")))
    return {"macho_files": count, "flagged": flagged, "non_system_names": external}


def check_strings(app: Path) -> dict:
    # `strings -a` over every regular file (binaries, Python sources, metadata), once per file.
    hits, advisory, scanned = [], {}, 0
    for path in sorted(app.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        scanned += 1
        content = subprocess.run(["/usr/bin/strings", "-a", str(path)], capture_output=True, check=False).stdout
        name = str(path.relative_to(app))
        for pattern in FORBIDDEN:
            if pattern in content and pattern not in ALLOWED_STRINGS.get(name, set()):
                hits.append(f"{name}: {pattern.decode()}")
        for pattern in ADVISORY:
            if pattern in content:
                advisory[pattern.decode()] = advisory.get(pattern.decode(), 0) + 1
    return {"files_scanned": scanned, "hits": hits, "advisory_files": advisory}


def check_runtime(app: Path, resources: Path, python: Path) -> dict:
    run = subprocess.run([str(python), "-s", "-c", PROBE], cwd=resources, env=TOOL_ENV, capture_output=True,
                         text=True, check=True)
    report = json.loads(run.stdout)
    bundle = str(app)
    outside_path = [entry for entry in report["sys_path"] if entry and not entry.startswith(bundle)]
    outside_files = [name for name in report["files"] if name and not name.startswith(bundle)]
    return {"sys_path": report["sys_path"], "prefix": report["prefix"], "outside_sys_path": outside_path,
            "outside_module_files": outside_files, "module_count": len(report["files"])}


def run_engine(app: Path, resources: Path, python: Path, wav: Path, fresh_home: bool) -> dict:
    with tempfile.TemporaryDirectory() as scratch:
        env = dict(TOOL_ENV)
        if fresh_home:
            env["HOME"] = str(Path(scratch) / "home")
            env["HF_HOME"] = str(Path(scratch) / "hf")
            Path(env["HOME"]).mkdir()
        config = Path(scratch) / "config"
        config.mkdir()
        command = [str(python), "-s", "-m", "dictate", "--config-dir", str(config), "serve"]
        with (ROOT / "build/release/verify-engine.stderr.log").open("w") as log:
            process = subprocess.Popen(command, cwd=resources, env=env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=log, text=True)
            events, result = [], None
            for line in process.stdout:
                event = json.loads(line)
                events.append(event)
                if event["event"] == "ready":
                    process.stdin.write(json.dumps({"wav": str(wav)}) + "\n")
                    process.stdin.flush()
                elif event["event"] in {"result", "model_error", "error"}:
                    result = event
                    break
            process.stdin.close()
            process.wait(timeout=60)
    progress = [event["fraction"] for event in events if event["event"] == "progress"]
    return {"events": [event["event"] for event in events if event["event"] != "progress"],
            "progress_events": len(progress), "last_progress": progress[-1] if progress else None,
            "result": result}


def main() -> int:
    app = Path(sys.argv[1]).resolve()
    wav = Path(sys.argv[2]).resolve()
    fresh_home = "--fresh-home" in sys.argv[3:]
    resources = app / "Contents/Resources"
    python = resources / "python/bin/python3"
    linkage = check_linkage(app)
    strings = check_strings(app)
    runtime = check_runtime(app, resources, python)
    engine = run_engine(app, resources, python, wav, fresh_home)
    summary = {"linkage": linkage, "strings": strings, "runtime": runtime, "engine": engine}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    ok = (not linkage["flagged"] and not strings["hits"] and not runtime["outside_sys_path"]
          and not runtime["outside_module_files"] and engine["result"] and engine["result"]["event"] == "result")
    print("VERIFY", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
