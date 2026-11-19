"""Full-app end-to-end check on a real desktop (no microphone needed).

    python windows\\tools\\desktop_e2e.py --exe dist\\murdic\\murdic.exe --wav build\\sample.wav

Runs murdic.exe with MURDIC_LOOPBACK=1 (the default speaker's loopback is the
"microphone") and MURDIC_ACCEPT_INJECTED=1, opens Notepad, then per run:
right Alt down (SendInput) -> plays the WAV through the speakers -> right Alt
up -> waits for the text in Notepad. Reports key-release -> text-visible time,
the app's own release -> Ctrl+V time, and whether the clipboard was restored.
Must run in an interactive desktop session; it plays audio out loud.
"""
import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "windows"))

import numpy as np  # noqa: E402
import soundcard as sc  # noqa: E402

from murdic_win import paste  # noqa: E402
from murdic_win.hotkey import INPUT, INPUT_KEYBOARD, KEYBDINPUT, KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, VK_RMENU, user32  # noqa: E402
from murdic_win.notepad import Notepad  # noqa: E402

PROBE = "murdic e2e 원래 클립보드"


def right_alt(down):
    """Inject right Alt like a keyboard would (dwExtraInfo 0, extended key)."""
    event = INPUT(type=INPUT_KEYBOARD)
    event.u.ki = KEYBDINPUT(VK_RMENU, 0x38, KEYEVENTF_EXTENDEDKEY | (0 if down else KEYEVENTF_KEYUP), 0, 0)
    if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
        raise OSError("SendInput blocked")


def wait_log(log, pattern, start_size, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log.exists():
            with open(log, encoding="utf-8", errors="replace") as handle:
                handle.seek(start_size)
                match = re.search(pattern, handle.read())
                if match:
                    return match
        time.sleep(0.02)
    return None


def run_device(exe, wav_path, device, runs, out):
    appdata = out / f"appdata-{device}"
    log = appdata / "murdic" / "murdic.log"
    if log.exists():
        log.unlink()
    env = dict(os.environ, APPDATA=str(appdata), MURDIC_LOOPBACK="1", MURDIC_ACCEPT_INJECTED="1",
               MURDIC_DEVICE=device, LOCALAPPDATA=str(out.parent / "smoke-local"))
    app = subprocess.Popen([str(exe)], env=env)
    rows = []
    pad = None
    try:
        ready = wait_log(log, r"Status: 오른쪽 Alt 키를 누른 채 말하세요", 0, 180)
        if not ready:
            raise RuntimeError("app did not become ready")
        engine = wait_log(log, r"Whisper small ready on (\S+)", 0, 1)
        speaker = sc.default_speaker()
        with wave.open(str(wav_path)) as source:
            audio = np.frombuffer(source.readframes(source.getnframes()), "<i2").astype(np.float32) / 32768
        pad = Notepad()
        for index in range(runs):
            if not pad.focus():
                raise RuntimeError("could not focus Notepad")
            pad.clear()
            paste.write_text(PROBE)
            mark = log.stat().st_size
            right_alt(True)
            if not wait_log(log, r"Status: 녹음 중", mark, 5):
                right_alt(False)
                raise RuntimeError("recording did not start")
            time.sleep(0.4)                       # WASAPI stream start
            speaker.play(audio, samplerate=16000)  # blocks while playing (~5 s)
            time.sleep(0.25)
            released = time.perf_counter()
            right_alt(False)
            deadline = released + 15
            text = ""
            while time.perf_counter() < deadline:
                text = pad.text().strip()
                if text:
                    break
                time.sleep(0.005)
            visible = round((time.perf_counter() - released) * 1000) if text else None
            sent = wait_log(log, r"Ctrl\+V sent (\d+) ms after key release", mark, 5)
            done = wait_log(log, r"Transcribed ([\d.]+) s in (\d+) ms on (\w+) \((\w+)\)", mark, 1)
            time.sleep(0.7)
            rows.append(dict(device=device, run=index + 1, text=text, release_to_visible_ms=visible,
                             release_to_ctrl_v_ms=int(sent[1]) if sent else None,
                             transcribe_ms=int(done[2]) if done else None,
                             engine=done[3] if done else None, route=done[4] if done else None,
                             clipboard_restored=paste.read_text() == PROBE))
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
            time.sleep(0.5)
        return dict(engine=engine[1] if engine else None, rows=rows)
    finally:
        if pad:
            pad.close()
        app.terminate()
        app.wait(10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=ROOT / "dist" / "murdic" / "murdic.exe")
    parser.add_argument("--wav", type=Path, default=ROOT / "build" / "sample.wav")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--devices", default="cpu,auto")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "desktop-e2e")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    original = paste.read_text()
    results = {}
    try:
        for device in args.devices.split(","):
            try:
                results[device] = run_device(args.exe.resolve(), args.wav.resolve(), device, args.runs, args.out)
            except Exception as error:
                results[device] = dict(error=repr(error))
                print(device, "failed:", error, flush=True)
    finally:
        if original is not None:
            paste.write_text(original)
    (args.out / "result.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
