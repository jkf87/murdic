"""Shared WAV-to-text path for the menu app and CLI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import wave

import numpy as np
from huggingface_hub import snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError
from murmur.audio import SAMPLE_RATE
from murmur.stt import DEFAULT_MODEL, WhisperSTT
from murmur.vad import VoiceActivityDetector

from .cleanup import clean

CONFIG_DIR = Path.home() / "Library/Application Support/murdic"


def read_pcm(path):
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, SAMPLE_RATE):
            raise wave.Error("conversion needed")
        frames = wav.readframes(wav.getnframes())
        if len(frames) != 2 * wav.getnframes():
            raise ValueError("Incomplete WAV data")
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768


def read_wav(path):
    try:
        return read_pcm(path)
    except wave.Error:
        with tempfile.TemporaryDirectory() as folder:
            converted = Path(folder) / "mono.wav"
            subprocess.run(["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1",
                            str(path), str(converted)], check=True)
            return read_pcm(converted)


def optional_hook(text, directory):
    # The executable receives only the locally edited transcript on stdin.
    hook = directory / "llm-cleanup"
    if not text or not os.environ.get("MURMUR_LLM_KEY") or not os.access(hook, os.X_OK):
        return text
    try:
        result = subprocess.run([str(hook)], input=text, capture_output=True,
                                text=True, check=True, timeout=4)
        return result.stdout.strip() or text
    except (OSError, ValueError, subprocess.SubprocessError):
        print("LLM hook unavailable; using local text", file=sys.stderr)
        return text


class Pipeline:
    def __init__(self, directory=CONFIG_DIR):
        self.directory = directory
        try:
            model = snapshot_download(DEFAULT_MODEL, local_files_only=True)
        except LocalEntryNotFoundError:
            model = DEFAULT_MODEL
        self.stt = WhisperSTT(model)
        if not self.stt.preload():
            raise RuntimeError("Murmur 모델을 불러올 수 없습니다. 모델 캐시와 MLX 설치를 확인하세요.")

    def run(self, path):
        started = time.perf_counter()
        audio = read_wav(path)
        raw = ""
        vad = VoiceActivityDetector()
        # A short phrase surrounded by silence should survive the voice gate.
        if any(vad.has_speech(audio[i:i + 4800]) for i in range(0, len(audio), 4800)):
            hints = self.directory / "hints.txt"
            prompt = ", ".join(line.strip() for line in hints.read_text().splitlines()
                               if line.strip()) if hints.exists() else None
            result = self.stt.transcribe(audio, language="ko", domain_hints=prompt)
            if not result.language and not result.inference_ms:
                raise RuntimeError("Murmur 전사 오류. 메뉴에서 엔진을 다시 시작하세요.")
            raw = result.text
        text = optional_hook(clean(raw), self.directory)
        return dict(text=text, raw=raw, audio_s=len(audio) / SAMPLE_RATE,
                    processing_ms=round((time.perf_counter() - started) * 1000, 1))


def serve(pipeline, output):
    def emit(payload):
        print(json.dumps(payload, ensure_ascii=False), file=output, flush=True)
    emit({"event": "ready"})
    for line in sys.stdin:
        try:
            path = Path(json.loads(line)["wav"])
            emit({"event": "result", **pipeline.run(path)})
        except Exception as error:
            emit({"event": "error", "message": str(error)})
