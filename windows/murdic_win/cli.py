"""Command line: tray app (default), WAV transcription, device list, Notepad benchmark."""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from . import paths

STARTED = time.perf_counter()


def setup_logging(directory, console):
    directory.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(directory / "murdic.log", encoding="utf-8")]
    if console and sys.stderr:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log_file = directory / "murdic.log"
    try:  # keep the log small; it is rewritten when it passes 1 MB
        if log_file.stat().st_size > 1_000_000:
            log_file.write_text("", encoding="utf-8")
    except OSError:
        pass


def console_progress(done, total, _last=[None]):
    percent = done * 100 // max(total, 1)
    if sys.stderr and percent != _last[0]:
        _last[0] = percent
        end = "\n" if done >= total else ""
        sys.stderr.write(f"\r모델 내려받는 중… {percent:3d}%  {done >> 20} / {total >> 20} MB{end}")
        sys.stderr.flush()


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="murdic", description="머딕 Windows: 로컬 한국어 받아쓰기")
    parser.add_argument("--config-dir", type=Path, help="설정·힌트 폴더 (기본: %%APPDATA%%\\murdic)")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"],
                        default=os.environ.get("MURDIC_DEVICE", "auto"))
    modes = parser.add_subparsers(dest="mode")
    wav = modes.add_parser("wav", help="WAV 파일을 전사·정리해 출력")
    wav.add_argument("path", type=Path)
    wav.add_argument("--json", action="store_true")
    wav.add_argument("--repeat", type=int, default=1)
    modes.add_parser("devices", help="입력 장치 목록(JSON)")
    mic = modes.add_parser("mic-test", help="장치별로 0.5초 녹음해 성공/실패·레벨·예외 전문 출력")
    mic.add_argument("--device", dest="mic_name", help="이름에 이 문자열이 든 장치만 (예: MV7)")
    mic.add_argument("--seconds", type=float, default=0.5)
    mic.add_argument("--json", action="store_true")
    bench = modes.add_parser("benchmark", help="WAV → 전사 → 메모장 붙여넣기 지연 측정")
    bench.add_argument("path", type=Path)
    bench.add_argument("--runs", type=int, default=5)
    args = parser.parse_args(argv)
    directory = args.config_dir or paths.config_dir()
    setup_logging(directory, console=args.mode not in (None, "mic-test"))
    from .diagnostics import log_environment
    log_environment()

    if args.mode == "mic-test":
        from .diagnostics import environment, mic_test
        info = environment()
        results = mic_test(args.mic_name, args.seconds)
        if args.json:
            print(json.dumps(dict(environment=info, results=results), ensure_ascii=False, indent=2))
        else:
            print(f"murdic {info['murdic']} · Windows build {info['windows_build']} · Python {info['python']}"
                  f" · sounddevice {info.get('sounddevice')} · {info.get('portaudio')}")
            for device in info.get("portaudio_inputs", []):
                print(f"  [{device['hostapi']}] #{device['index']} {device['name']}"
                      f" · {device['default_samplerate']:.0f} Hz · {device['channels']}ch")
            if not results:
                print("녹음할 입력 장치가 없습니다." + (f" (--device {args.mic_name})" if args.mic_name else ""))
            for row in results:
                mark = "성공" if row["ok"] else "실패"
                print(f"\n[{mark}] {row['name']}{' (기본)' if row['default'] else ''}")
                print(f"  백엔드: {row.get('backend')}")
                if row["ok"]:
                    print(f"  {row['seconds']} s, {row['samples']} samples @16 kHz,"
                          f" peak {row['peak']}, max block {row['max_block_dbfs']} dBFS")
                else:
                    print(f"  오류: {row['error']}\n{row['traceback']}")
        return 0 if results and all(r["ok"] for r in results) else 1

    if args.mode == "wav":
        from .engine import Engine, Pipeline
        pipeline = Pipeline(directory, Engine(device=args.device, progress=console_progress))
        warmup = round((time.perf_counter() - STARTED) * 1000, 1)
        for _ in range(args.repeat):
            result = pipeline.run(args.path)
            print(json.dumps(dict(warmup_ms=warmup, **result), ensure_ascii=False)
                  if args.json else result["text"], flush=True)
        return 0
    if args.mode == "devices":
        from .audio import list_microphones
        snapshot = list_microphones()
        print(json.dumps(dict(default=snapshot.default_id, devices=[m._asdict() for m in snapshot.devices]),
                         ensure_ascii=False, indent=2))
        return 0
    if args.mode == "benchmark":
        from .benchmark import run_benchmark
        return run_benchmark(args.path, args.runs, directory, args.device, STARTED)
    from .app import run_app
    return run_app(directory, args.device)
