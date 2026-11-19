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
from typing import NamedTuple, Optional, Tuple

import numpy as np
# Import once at module load, before any thread calls CoInitializeEx: SoundCard
# initialises COM on import and fails if that thread already did (S_FALSE).
import soundcard as sc

from .engine import SAMPLE_RATE, level_db

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
    pass


def loopback_enabled():
    """MURDIC_LOOPBACK=1 lists speaker loopbacks as inputs (automated tests on PCs without a mic)."""
    return os.environ.get("MURDIC_LOOPBACK") == "1"


def ensure_com():
    # SoundCard initialises COM only in the importing thread.
    ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED; S_FALSE if already done


def explain(error):
    text = str(error)
    if "0x80070005" in text:
        return "마이크 접근이 막혀 있습니다. Windows 설정 › 개인 정보 › 마이크에서 데스크톱 앱 접근을 허용하세요."
    if "0x88890004" in text or "0x80070490" in text:
        return "마이크 연결이 끊겼습니다."
    if "0x8889000a" in text:
        return "다른 앱이 마이크를 독점 모드로 사용 중입니다."
    return f"마이크 오류: {text}"


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
                log.warning("Device enumeration failed: %s", error)
            self._halt.wait(self.interval)

    def stop(self):
        self._halt.set()


class Capture:
    """Records one take from a microphone into memory (no temporary file).

    Callbacks run on the capture thread; the app forwards them to the UI thread."""

    def __init__(self, microphone, test=False, on_level=None, on_failure=None):
        self.microphone, self.test = microphone, test
        self.on_level, self.on_failure = on_level, on_failure
        self.max_db = -160.0
        self.failure = None
        self.started = threading.Event()
        self._stop = threading.Event()
        self._chunks = []
        self._thread = threading.Thread(target=self._run, name="murdic-capture", daemon=True)

    def start(self):
        self._thread.start()
        return self

    def _open(self):
        for mic in sc.all_microphones(include_loopback=loopback_enabled()):
            if mic.id == self.microphone.id:
                return mic
        raise AudioError("마이크 연결이 끊겼습니다.")

    def _run(self):
        try:
            ensure_com()
            device = self._open()
            last_meter = 0.0
            with device.recorder(samplerate=SAMPLE_RATE, channels=1, blocksize=BLOCK) as recorder:
                self.started.set()
                while not self._stop.is_set():
                    block = recorder.record(numframes=BLOCK)[:, 0].astype(np.float32)
                    if not self.test:
                        self._chunks.append(block)
                    db = level_db(block)
                    self.max_db = max(self.max_db, db)
                    now = time.monotonic()
                    if self.on_level and now - last_meter >= LEVEL_INTERVAL:
                        last_meter = now
                        self.on_level(db)
        except Exception as error:
            self.failure = error if isinstance(error, AudioError) else AudioError(explain(error))
            log.warning("Capture failed on %s: %s", self.microphone.name, error)
            self.started.set()
            if self.on_failure and not self._stop.is_set():
                self.on_failure(self.failure)

    def stop(self, timeout=2.0):
        """Stop and return (samples, max_db). Raises the capture failure if any."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout)
        if self.failure:
            raise self.failure
        audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
        return audio, self.max_db
