"""Compare local Whisper engines on Korean TTS sentences (Windows).

    .venv\\Scripts\\python windows\\tools\\engine_compare.py [--whisper-cpp DIR --ggml MODEL]

For each sentence it reports warm latency (median of 3) for faster-whisper on CPU
(murdic's short window and the standard 30 s window) and on CUDA when available,
plus whisper.cpp's `whisper-cli` when its folder is given. whisper-cli reloads the
model per call, so its load time is reported separately and excluded.
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from murdic_win import engine as E  # noqa: E402

SENTENCES = [
    "네, 알겠습니다.",
    "내일 세 시, 아니 네 시에 만나요.",
    "어 그러니까 이번 주 금요일까지 보고서 초안을 보내 주세요.",
    "오늘 오후 세 시에 회의실에서 만나요. 준비한 자료도 가져오세요.",
    "회의 결과를 정리하면 다음과 같습니다. 첫째, 신규 기능은 다음 달 첫째 주에 배포합니다. "
    "둘째, 고객 문의가 많은 결제 화면을 먼저 개선합니다. 셋째, 다음 회의는 목요일 오전 열 시에 진행합니다.",
]


def speak(text, out):
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ko-KR' } | Select-Object -First 1;"
        "$s.SelectVoice($v.VoiceInfo.Name); $s.Rate = 1;"
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono);"
        "$s.SetOutputToWaveFile($env:OUT, $f); $s.Speak($env:TEXT); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True,
                   env=dict(os.environ, OUT=str(out), TEXT=text))


def timed(fn, runs=3):
    fn()  # warm-up
    results, times = None, []
    for _ in range(runs):
        started = time.perf_counter()
        results = fn()
        times.append((time.perf_counter() - started) * 1000)
    return round(statistics.median(times)), results


def whisper_cpp(folder, model, wav, threads, audio_s):
    exe = Path(folder) / "whisper-cli.exe"
    # Same window rule as murdic's short path: >= 15 s and >= speech + 3 s.
    # (`-ac` counts encoder positions, two mel frames each.) A fixed -ac shorter
    # than the speech made whisper.cpp loop on the 17 s sentence.
    frames = min(3000, max(E.MIN_FRAMES, int(audio_s * 100) + E.MARGIN_FRAMES))
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "out"
        run = subprocess.run([str(exe), "-m", model, "-f", str(wav), "-l", "ko", "-t", str(threads), "-nt",
                              "-ac", str(frames // 2), "-otxt", "-of", str(base)],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        text = (base.with_suffix(".txt")).read_text(encoding="utf-8").strip()
    timings = dict(re.findall(r"whisper_print_timings:\s+(\w+) time =\s+([\d.]+) ms", run.stderr))
    return round(float(timings["total"]) - float(timings["load"])), round(float(timings["load"])), text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--whisper-cpp", help="folder with whisper-cli.exe")
    parser.add_argument("--whisper-cpp-cuda", help="folder with the CUDA build of whisper-cli.exe")
    parser.add_argument("--ggml", help="ggml model path for whisper.cpp")
    args = parser.parse_args()
    rows = []
    engines = {"cpu": E.Engine(device="cpu")}
    if E.cuda_ready():
        engines["cuda"] = E.Engine(device="cuda")
    with tempfile.TemporaryDirectory() as tmp:
        for index, sentence in enumerate(SENTENCES):
            wav = Path(tmp) / f"s{index}.wav"
            speak(sentence, wav)
            audio = E.read_wav(wav)
            row = dict(sentence=sentence, audio_s=round(len(audio) / E.SAMPLE_RATE, 2))
            cpu = engines["cpu"]
            row["cpu_short_ms"], (row["cpu_short"], row["route"]) = timed(lambda: cpu.transcribe(audio))
            row["cpu_full_ms"], row["cpu_full"] = timed(lambda: cpu._long(audio, None))
            if "cuda" in engines:
                gpu = engines["cuda"]
                row["cuda_ms"], (row["cuda"], _) = timed(lambda: gpu.transcribe(audio))
            if args.whisper_cpp:
                row["wcpp_ms"], row["wcpp_load_ms"], row["wcpp"] = whisper_cpp(
                    args.whisper_cpp, args.ggml, wav, cpu.threads, row["audio_s"])
            if args.whisper_cpp_cuda:
                row["wcpp_cuda_ms"], row["wcpp_cuda_load_ms"], row["wcpp_cuda"] = whisper_cpp(
                    args.whisper_cpp_cuda, args.ggml, wav, cpu.threads, 30)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
