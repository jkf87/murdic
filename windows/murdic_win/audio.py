"""Microphones over WASAPI (SoundCard): list, select with fallback, watch, record.

Selection mirrors the macOS app: a pinned endpoint that disappears is cleared
once (also across restarts) and the system default is used from then on, so a
flaky USB microphone that reconnects does not take over again.
"""
import ctypes
import logging
import os
import threading
import time
import traceback
from typing import NamedTuple, Optional, Tuple

import numpy as np
# Import once at module load, before any thread calls CoInitializeEx: SoundCard
# initialises COM on import and fails if that thread already did (S_FALSE).
import soundcard as sc

from .engine import SAMPLE_RATE, level_db, to_mono_16k
from .errors import describe

log = logging.getLogger("murdic.audio")
BLOCK = 800            # 50 ms at 16 kHz
LEVEL_INTERVAL = 0.075  # same meter rate as the macOS overlay


class Microphone(NamedTuple):
    id: str
    name: str


class InputDevices(NamedTuple):
    devices: Tuple[Microphone, ...] = ()
    default_id: Optional[str] = None

    @property
    def system_default(self):
        return next((m for m in self.devices if m.id == self.default_id), None)


class AudioError(RuntimeError):
    user_facing = True


def loopback_enabled():
    """MURDIC_LOOPBACK=1 lists speaker loopbacks as inputs (automated tests on PCs without a mic)."""
    return os.environ.get("MURDIC_LOOPBACK") == "1"


def ensure_com():
    # SoundCard initialises COM only in the importing thread.
    ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED; S_FALSE if already done


# HRESULTs as SoundCard (hex) and PortAudio's WASAPI host errors (signed decimal) print them.
_KNOWN = [
    (("0x80070005", "-2147024891", "access is denied", "액세스가 거부"),
     "마이크 접근이 막혀 있습니다. Windows 설정 › 개인 정보 › 마이크에서 데스크톱 앱 접근을 허용하세요."),
    (("0x88890004", "-2004287484", "0x80070490", "-2147023728"), "마이크 연결이 끊겼습니다."),
    (("0x8889000a", "-2004287478", "-9985", "device unavailable"),
     "다른 앱이 마이크를 독점 모드로 사용 중이거나 장치를 쓸 수 없습니다."),
]


def explain(error):
    """Korean hint plus the original error and its type; never an empty message."""
    detail = describe(error)
    lowered = detail.lower()
    for needles, hint in _KNOWN:
        if any(needle in lowered for needle in needles):
            return f"{hint} [{detail}]"
    return f"마이크 오류: {detail}"


def list_microphones():
    ensure_com()
    loop = loopback_enabled()
    found = sc.all_microphones(include_loopback=loop)
    devices = tuple(sorted({Microphone(m.id, m.name) for m in found}, key=lambda m: (m.name.casefold(), m.id)))
    default_id = None
    try:
        default_id = sc.default_microphone().id
    except Exception:  # 0x80070490: no capture endpoint
        if loop:
            try:
                default_id = sc.default_speaker().id
            except Exception:
                pass
    return InputDevices(devices, default_id)


class MicrophoneSelection:
    def __init__(self, settings):
        self.settings = settings
        self.inputs = InputDevices()
        self.pinned_id = settings.get("microphone_id")

    @property
    def active(self):
        if self.pinned_id:
            return next((m for m in self.inputs.devices if m.id == self.pinned_id), None)
        return self.inputs.system_default

    @property
    def default_title(self):
        current = self.inputs.system_default
        return f"시스템 기본값 (현재: {current.name if current else '없음'})"

    def select(self, mic):
        self.pinned_id = mic.id if mic else None
        self.settings.update(microphone_id=mic.id if mic else None, microphone_name=mic.name if mic else None)

    def update(self, snapshot):
        """Apply a device snapshot; return the lost microphone's name if the pinned one vanished."""
        self.inputs = snapshot
        if not self.pinned_id or any(m.id == self.pinned_id for m in snapshot.devices):
            return None
        lost = self.settings.get("microphone_name") or "선택한 마이크"
        self.select(None)
        return lost


class DeviceWatcher(threading.Thread):
    """Polls the endpoint list (cheap) and reports changes, including the default device."""

    def __init__(self, changed, interval=1.5, lister=list_microphones):
        super().__init__(name="murdic-devices", daemon=True)
        self.changed, self.interval, self.lister = changed, interval, lister
        self._halt = threading.Event()
        self.last = None

    def run(self):
        ensure_com()
        while not self._halt.is_set():
            try:
                snapshot = self.lister()
                if snapshot != self.last:
                    self.last = snapshot
                    self.changed(snapshot)
            except Exception as error:
                log.warning("Device enumeration failed: %s", describe(error), exc_info=True)
            self._halt.wait(self.interval)

    def stop(self):
        self._halt.set()


# --- PortAudio (sounddevice) capture ------------------------------------------------
# SoundCard's recorder asserts that the WASAPI shared mix format is
# WAVE_FORMAT_EXTENSIBLE, which some USB microphones (e.g. Shure MV7+) do not use.
# PortAudio's WASAPI host handles plain WAVEFORMATEX, so real microphones are
# recorded through it: shared mode at the device's mix rate and channel count,
# then mixed to mono and resampled to 16 kHz by murdic (engine.to_mono_16k).
_PA_LOCK = threading.Lock()
_PA_OPEN = 0          # streams currently open; PortAudio must not be re-initialised under them
NO_DATA_SECONDS = 1.0  # no audio callback for this long -> treat the device as gone


def portaudio_inputs(refresh=False, hostapi="Windows WASAPI"):
    """Input devices of one PortAudio host API: [(index, info), ...].

    `refresh` re-initialises PortAudio (about 25 ms) so hot-plugged devices appear;
    it is skipped while a stream is open."""
    import sounddevice as sd
    with _PA_LOCK:
        if refresh and _PA_OPEN == 0:
            sd._terminate()
            sd._initialize()
        hostapis = sd.query_hostapis()
        api = next((i for i, h in enumerate(hostapis) if h["name"] == hostapi), None)
        if api is None:
            return []
        return [(i, d) for i, d in enumerate(sd.query_devices())
                if d["hostapi"] == api and d["max_input_channels"] > 0]


def match_portaudio(mic, inputs, same_name_rank=0):
    """Pick the PortAudio WASAPI device for a Core Audio endpoint.

    Both expose the endpoint's friendly name; when several endpoints share a name,
    the n-th one (in Core Audio order) maps to the n-th PortAudio device."""
    exact = [(i, d) for i, d in inputs if d["name"] == mic.name]
    if not exact:
        exact = [(i, d) for i, d in inputs if mic.name in d["name"] or d["name"] in mic.name]
    if not exact:
        return None
    return exact[min(same_name_rank, len(exact) - 1)]


def is_loopback(mic):
    if not loopback_enabled():
        return False
    return any(s.id == mic.id for s in sc.all_speakers())


class Capture:
    """Records one take from a microphone into memory (no temporary file).

    Callbacks run on the capture thread; the app forwards them to the UI thread."""

    def __init__(self, microphone, test=False, on_level=None, on_failure=None):
        self.microphone, self.test = microphone, test
        self.on_level, self.on_failure = on_level, on_failure
        self.max_db = -160.0
        self.failure = None
        self.traceback = None
        self.rate = SAMPLE_RATE
        self.backend = None
        self.started = threading.Event()
        self._stop = threading.Event()
        self._chunks = []
        self._last_meter = 0.0
        self._thread = threading.Thread(target=self._run, name="murdic-capture", daemon=True)

    def start(self):
        self._thread.start()
        return self

    def _block(self, mono):
        if not self.test:
            self._chunks.append(mono)
        db = level_db(mono)
        self.max_db = max(self.max_db, db)
        now = time.monotonic()
        if self.on_level and now - self._last_meter >= LEVEL_INTERVAL:
            self._last_meter = now
            self.on_level(db)

    def _run(self):
        try:
            ensure_com()
            if is_loopback(self.microphone):
                self._run_loopback()
            else:
                self._run_portaudio()
        except Exception as error:
            self.failure = error if isinstance(error, AudioError) else AudioError(explain(error))
            self.traceback = traceback.format_exc()
            log.warning("Capture failed on %s (%s): %s", self.microphone.name, self.backend, describe(error),
                        exc_info=True)
            self.started.set()
            if self.on_failure and not self._stop.is_set():
                self.on_failure(self.failure)

    def _run_portaudio(self):
        global _PA_OPEN
        import queue

        import sounddevice as sd
        if not any(m.id == self.microphone.id for m in sc.all_microphones()):
            raise AudioError("마이크 연결이 끊겼습니다.")
        rank = [m.id for m in sc.all_microphones() if m.name == self.microphone.name].index(self.microphone.id)
        blocks = queue.Queue()
        stream, errors = None, []
        # WASAPI shared mode only accepts the device's mix rate (16 kHz fails with -9997):
        # open at the default rate and resample. If WASAPI fails, MME opens at 16 kHz directly.
        for hostapi, refresh in (("Windows WASAPI", True), ("MME", False)):
            found = match_portaudio(self.microphone, portaudio_inputs(refresh, hostapi), rank)
            if found is None:
                errors.append(f"{hostapi}: 장치 없음")
                continue
            index, info = found
            rate = int(info["default_samplerate"]) if hostapi == "Windows WASAPI" else SAMPLE_RATE
            channels = max(1, min(2, int(info["max_input_channels"])))
            try:
                with _PA_LOCK:
                    stream = sd.InputStream(device=index, samplerate=rate, channels=channels, dtype="float32",
                                            blocksize=rate // 20,
                                            callback=lambda data, frames, when, status: blocks.put(data.copy()))
                    _PA_OPEN += 1
                try:
                    stream.start()
                except Exception:
                    with _PA_LOCK:
                        _PA_OPEN -= 1
                        stream.close()
                    stream = None
                    raise
                self.rate = rate
                self.backend = f"PortAudio {hostapi} #{index} '{info['name']}' {rate} Hz {channels}ch"
                break
            except Exception as error:
                stream = None
                errors.append(describe(error, hostapi))
                log.warning("Could not open %s on %s", self.microphone.name, hostapi, exc_info=True)
        if stream is None:
            raise AudioError(f"녹음 장치를 열 수 없습니다: {self.microphone.name} — " + "; ".join(errors))
        try:
            self.started.set()
            log.info("Recording %s via %s", self.microphone.name, self.backend)
            while not self._stop.is_set():
                try:
                    data = blocks.get(timeout=NO_DATA_SECONDS)
                except queue.Empty:
                    raise AudioError("마이크에서 소리가 들어오지 않습니다. 연결을 확인하세요.") from None
                self._block(data.mean(axis=1) if data.shape[1] > 1 else data[:, 0])
            while not blocks.empty():   # keep the tail recorded before the key was released
                data = blocks.get_nowait()
                self._block(data.mean(axis=1) if data.shape[1] > 1 else data[:, 0])
        finally:
            with _PA_LOCK:
                try:
                    stream.stop()
                    stream.close()
                finally:
                    _PA_OPEN -= 1

    def _run_loopback(self):
        """Test mode only: speaker loopback through SoundCard (speaker mix formats are extensible)."""
        device = next((m for m in sc.all_microphones(include_loopback=True) if m.id == self.microphone.id), None)
        if device is None:
            raise AudioError("마이크 연결이 끊겼습니다.")
        self.backend = "SoundCard loopback 16000 Hz 1ch"
        with device.recorder(samplerate=SAMPLE_RATE, channels=1, blocksize=BLOCK) as recorder:
            self.started.set()
            while not self._stop.is_set():
                self._block(recorder.record(numframes=BLOCK)[:, 0].astype(np.float32))

    def stop(self, timeout=2.0):
        """Stop and return (16 kHz mono samples, max_db). Raises the capture failure if any."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout)
        if self.failure:
            raise self.failure
        audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
        return to_mono_16k(audio, self.rate), self.max_db
