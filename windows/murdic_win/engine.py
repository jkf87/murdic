"""Local Korean transcription with faster-whisper (CTranslate2) and shared cleanup.

Whisper encodes a fixed 30 s window, so a 5 s utterance pays for 25 s of padding.
CTranslate2 accepts a shorter mel window. On CPU, the short path sizes the window
to the speech (at least 15 s), which roughly halves the full-window time
(see docs/windows-engine.md). Low-confidence or repetitive results and long
recordings use faster-whisper's standard 30 s transcription instead.
"""
import logging
import math
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

from dictate.cleanup import clean

from . import paths
from .errors import describe
from .postprocess import build_prompt, filter_transcript, parse_terms, speech_windows

# Murmur's decoding settings (core/src/murmur/stt.py, docs/STT_TUNING.md §1).
# mlx_whisper decodes greedily at temperature 0, so beam_size is 1 here too.
DECODE = dict(beam_size=1, best_of=1, temperature=0.0, condition_on_previous_text=False,
              no_speech_threshold=0.6, compression_ratio_threshold=1.8, log_prob_threshold=-1.0)

SAMPLE_RATE = 16000
HOP = 160                 # mel frames are 10 ms apart
MIN_FRAMES = 1500         # 15 s; 10 s windows sometimes dropped a sentence period
MARGIN_FRAMES = 300       # at least 3 s of trailing padding after the speech
MAX_SHORT_SECONDS = 25.0
QUIET_DB = -65.0          # same quiet-input threshold as the macOS app
log = logging.getLogger("murdic.engine")


class EngineError(RuntimeError):
    user_facing = True


def add_cuda_dll_dirs():
    added = []
    for folder in paths.cuda_dirs():
        try:
            os.add_dll_directory(str(folder))
        except OSError:
            continue
        os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
        added.append(folder)
    return added


def cuda_ready():
    """True when an NVIDIA GPU and loadable cuBLAS DLLs are present.

    CTranslate2 loads cuBLAS lazily, so probe it here rather than failing in
    the middle of the first dictation."""
    import ctranslate2
    try:
        if ctranslate2.get_cuda_device_count() < 1:
            return False
    except Exception:
        return False
    import ctypes
    try:
        for name in ("cublasLt64_12.dll", "cublas64_12.dll"):
            ctypes.WinDLL(name)
    except OSError:
        return False
    return True


def physical_cores():
    # Hyper-threads did not help int8 decoding here (6 threads beat 12 on a Ryzen 5 3600).
    return max(2, min(8, (os.cpu_count() or 4) // 2))


def resolve_model(progress=None):
    found = paths.bundled_model()
    if found:
        return str(found)
    if paths.FROZEN:   # installed app: pinned, checksummed download to %LOCALAPPDATA%
        from .download import download_model as fetch_model
        log.info("Downloading Whisper small (about 486 MB)")
        return str(fetch_model(progress))
    from faster_whisper.utils import download_model
    try:
        return download_model("small", local_files_only=True)
    except Exception:
        log.info("Downloading faster-whisper small (about 480 MB)")
        return download_model("small")


def to_mono_16k(samples, rate, channels=1):
    """Mix interleaved float samples to mono and resample to 16 kHz."""
    audio = np.asarray(samples, np.float32).reshape(-1, channels).mean(axis=1)
    if rate == SAMPLE_RATE or len(audio) == 0:
        return audio.astype(np.float32)
    if rate % SAMPLE_RATE == 0:  # 32/48/96 kHz: average each group (a simple low-pass)
        step = rate // SAMPLE_RATE
        return audio[:len(audio) // step * step].reshape(-1, step).mean(axis=1).astype(np.float32)
    count = int(round(len(audio) * SAMPLE_RATE / rate))
    return np.interp(np.arange(count) * rate / SAMPLE_RATE, np.arange(len(audio)), audio).astype(np.float32)


def read_wav(path):
    """Return float32 mono 16 kHz samples from a PCM WAV file."""
    if not Path(path).exists():
        raise FileNotFoundError(f"오디오 파일이 없습니다: {path}")
    with wave.open(str(path), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if len(frames) % (channels * width):
        raise ValueError("Incomplete WAV data")
    if width == 2:
        samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768
    elif width == 1:
        samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128) / 128
    elif width == 3:
        raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        value = raw[:, 0] | (raw[:, 1] << 8) | (raw[:, 2] << 16)
        samples = np.where(value >= 1 << 23, value - (1 << 24), value).astype(np.float32) / (1 << 23)
    elif width == 4:
        samples = np.frombuffer(frames, dtype="<i4").astype(np.float32) / (1 << 31)
    else:
        raise ValueError(f"지원하지 않는 WAV 형식입니다 ({width * 8}-bit)")
    return to_mono_16k(samples, rate, channels)


def level_db(samples):
    if len(samples) == 0:
        return -160.0
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    return 20 * math.log10(max(rms, 1e-8))


class Engine:
    """Loads Whisper once; `transcribe` is called from one worker thread at a time."""

    def __init__(self, device="auto", model_path=None, cpu_threads=None, progress=None):
        add_cuda_dll_dirs()
        from faster_whisper import WhisperModel
        from faster_whisper.tokenizer import Tokenizer
        from faster_whisper.transcribe import get_suppressed_tokens

        path = model_path or resolve_model(progress)
        candidates = []
        if device in ("auto", "cuda") and cuda_ready():
            candidates.append(("cuda", "float16"))
        elif device == "cuda":
            log.warning("CUDA requested but no GPU/cuBLAS available; using CPU")
        if device in ("auto", "cpu", "cuda"):
            candidates.append(("cpu", "int8"))
        errors = []
        self.beam_size = DECODE["beam_size"]
        self.threads = cpu_threads or physical_cores()
        for dev, compute in candidates:
            try:
                started = time.perf_counter()
                self.model = WhisperModel(path, device=dev, compute_type=compute,
                                          cpu_threads=self.threads)
                self.device, self.compute_type = dev, compute
                self.tokenizer = Tokenizer(self.model.hf_tokenizer, True, task="transcribe", language="ko")
                self.suppress = list(get_suppressed_tokens(self.tokenizer, [-1]))
                self._decode(np.zeros(SAMPLE_RATE, np.float32), None)  # loads GPU kernels/cuBLAS now
                self.load_ms = round((time.perf_counter() - started) * 1000)
                log.info("Whisper small ready on %s/%s in %d ms", dev, compute, self.load_ms)
                return
            except Exception as error:  # e.g. cuBLAS present but the driver is too old
                errors.append(describe(error, dev))
                log.warning("Could not use %s: %s", dev, describe(error), exc_info=True)
        raise EngineError("Whisper 모델을 불러올 수 없습니다. " + "; ".join(errors))

    @property
    def label(self):
        return "GPU (CUDA)" if self.device == "cuda" else f"CPU ({self.threads}스레드)"

    def transcribe(self, audio, hints=None, windows=None):
        """Return (raw text, decoding path) for one utterance.

        Like dictate/backend.py, nothing is transcribed unless Murmur's VAD finds
        speech in at least one 0.3 s window."""
        if windows is None:
            windows = speech_windows(audio)
        if not windows:
            return "", "silent"
        if len(audio) / SAMPLE_RATE <= MAX_SHORT_SECONDS:
            text, trusted = self._decode(audio, hints)
            if trusted:
                return text, "short" if self.device == "cpu" else "direct"
        return self._long(audio, hints), "full"

    def _decode(self, clip, hints):
        from faster_whisper.transcribe import get_compression_ratio
        needed = math.ceil(len(clip) / HOP)
        if self.device == "cuda":
            frames = 3000   # the full window costs little on a GPU
        else:
            frames = min(3000, max(MIN_FRAMES, math.ceil((needed + MARGIN_FRAMES) / 100) * 100))
        padded = np.zeros(frames * HOP, np.float32)
        padded[:len(clip)] = clip[:frames * HOP]
        features = self.model.feature_extractor(padded, padding=0)[:, :frames]
        encoded = self.model.encode(features)
        previous = self.tokenizer.encode(" " + hints.strip()) if hints else []
        prompt = self.model.get_prompt(self.tokenizer, previous, without_timestamps=True)
        result = self.model.model.generate(
            encoded, [prompt], beam_size=self.beam_size, patience=1, length_penalty=1,
            max_length=self.model.max_length, return_scores=True, return_no_speech_prob=True,
            suppress_blank=True, suppress_tokens=self.suppress)[0]
        tokens = [t for t in result.sequences_ids[0] if t < self.tokenizer.eot]
        text = self.tokenizer.decode(tokens).strip()
        avg_logprob = result.scores[0] * len(tokens) / (len(tokens) + 1)
        # Whisper's silence rule with Murmur's thresholds.
        if (result.no_speech_prob > DECODE["no_speech_threshold"]
                and avg_logprob < DECODE["log_prob_threshold"]):
            return "", True
        # Anything Murmur's thresholds would flag is decoded again exactly as Murmur
        # does (30 s window), so only clean short-window results differ in path.
        trusted = (bool(text) and avg_logprob >= DECODE["log_prob_threshold"]
                   and get_compression_ratio(text) <= DECODE["compression_ratio_threshold"])
        if not trusted:
            log.info("Short decode flagged (logprob %.2f): using the 30 s window", avg_logprob)
        return text, trusted

    def _long(self, audio, hints):
        """faster-whisper's standard transcription with Murmur's decoding settings."""
        segments, _ = self.model.transcribe(audio, language="ko", initial_prompt=hints or None,
                                            vad_filter=False, **DECODE)
        return "".join(segment.text for segment in segments).strip()


def find_hook(directory):
    for name in ("llm-cleanup.exe", "llm-cleanup.cmd", "llm-cleanup.bat", "llm-cleanup.ps1"):
        hook = Path(directory) / name
        if hook.is_file():
            return hook
    return None


def optional_hook(text, directory):
    """Windows counterpart of dictate.backend.optional_hook (same opt-in and fallback)."""
    hook = find_hook(directory)
    if not text or not os.environ.get("MURMUR_LLM_KEY") or hook is None:
        return text
    command = ([ "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(hook)]
               if hook.suffix == ".ps1" else [str(hook)])
    try:
        result = subprocess.run(command, input=text, capture_output=True, text=True, encoding="utf-8",
                                check=True, timeout=4, creationflags=subprocess.CREATE_NO_WINDOW)
        return result.stdout.strip() or text
    except (OSError, ValueError, subprocess.SubprocessError):
        log.warning("LLM hook unavailable; using local text", exc_info=True)
        return text


class Pipeline:
    """Samples -> Murmur VAD gate -> Whisper (Murmur settings + hint preset + hints.txt)
    -> hallucination filter -> term corrections -> dictate.cleanup.clean -> optional hook."""

    def __init__(self, directory=None, engine=None, device="auto", preset=None):
        self.directory = Path(directory) if directory else paths.config_dir()
        if preset is None:
            from .settings import Settings
            preset = Settings(self.directory).get("hint_preset", "none")
        self.preset = preset
        self.engine = engine or Engine(device=device)

    def _lines(self, name):
        file = self.directory / name
        return file.read_text(encoding="utf-8-sig") if file.exists() else ""

    def hints(self):
        return build_prompt(self.preset, [line.strip() for line in self._lines("hints.txt").splitlines()])

    def run_audio(self, audio):
        started = time.perf_counter()
        windows = speech_windows(audio)
        raw, route = self.engine.transcribe(audio, self.hints(), windows)
        text = filter_transcript(raw, windows, parse_terms(self._lines("terms.txt")))
        text = optional_hook(clean(text), self.directory) if text else ""
        return dict(text=text, raw=raw, audio_s=round(len(audio) / SAMPLE_RATE, 3),
                    processing_ms=round((time.perf_counter() - started) * 1000, 1),
                    device=self.engine.device, route=route, speech_windows=windows)

    def run(self, path):
        return self.run_audio(read_wav(path))
