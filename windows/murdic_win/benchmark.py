"""`murdic benchmark WAV`: WAV -> transcription -> cleanup -> Ctrl+V into a real Notepad.

Measures, per run, from the moment the samples are handed to the engine:
processing (Whisper + cleanup), Ctrl+V sent, and text visible in Notepad
(polled with WM_GETTEXT). The user's clipboard is saved first and restored at
the end; every run also checks that murdic's own restore worked.
Run it in an interactive desktop session; it refuses to paste when Notepad
is not the foreground window.
"""
import json
import statistics
import time

from . import paste
from .engine import Pipeline, read_wav
from .notepad import Notepad

PROBE = "murdic 벤치마크 원래 클립보드"


def run_benchmark(path, runs, directory, device, started):
    pipeline = Pipeline(directory, device=device)
    ready_ms = round((time.perf_counter() - started) * 1000)
    audio = read_wav(path)
    pipeline.run_audio(audio)   # warm-up, as the app does after loading
    with paste._Open():
        user_clipboard = paste.snapshot()
    rows = []
    pad = Notepad()
    try:
        paste.write_text(PROBE)
        for index in range(runs):
            if not pad.focus():
                raise RuntimeError("메모장을 앞으로 가져오지 못했습니다(대화형 데스크톱에서 실행하세요).")
            pad.clear()
            begin = time.perf_counter()
            result = pipeline.run_audio(audio)
            processed = time.perf_counter()
            if not pad.is_front():
                raise RuntimeError("메모장이 앞에 있지 않아 붙여넣기를 중단했습니다.")
            transaction = paste.PasteTransaction(result["text"])
            paste.send_paste()
            sent = time.perf_counter()
            visible = pad.wait_for(result["text"], begin)
            time.sleep(max(0.0, paste.RESTORE_DELAY - (time.perf_counter() - sent)))
            restored = transaction.restore() and paste.read_text() == PROBE
            rows.append(dict(run=index + 1, text=result["text"], device=result["device"], route=result["route"],
                             processing_ms=round((processed - begin) * 1000),
                             ctrl_v_ms=round((sent - begin) * 1000),
                             visible_ms=visible,
                             paste_to_visible_ms=None if visible is None else visible - round((sent - begin) * 1000),
                             clipboard_restored=restored))
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
            time.sleep(0.3)
    finally:
        pad.close()
        with paste._Open():
            paste.user32.EmptyClipboard()
            for fmt, data in user_clipboard:
                paste._set(fmt, data)
    visible = [r["visible_ms"] for r in rows if r["visible_ms"] is not None]
    summary = dict(summary=True, startup_to_model_ready_ms=ready_ms, runs=len(rows),
                   device=pipeline.engine.device,
                   visible_ms=visible, median_visible_ms=statistics.median(visible) if visible else None,
                   max_visible_ms=max(visible) if visible else None,
                   all_text_ok=all(r["visible_ms"] is not None for r in rows),
                   all_clipboard_restored=all(r["clipboard_restored"] for r in rows))
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["all_text_ok"] and summary["all_clipboard_restored"] else 1
