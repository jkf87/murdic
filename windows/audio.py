"""Bounded, in-memory microphone capture with no audio files left on disk."""
from io import BytesIO
import wave

import numpy as np
import sounddevice as sd

MAX_SECONDS = 180


def inputs():
    hosts = sd.query_hostapis()
    return [(i, {"name": d["name"], "hostapi": hosts[d["hostapi"]]["name"]})
            for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]


def resolve_device(saved):
    if saved is None:
        return None
    for index, identity in inputs():
        if identity == saved:
            return index
    raise ValueError("저장된 마이크가 없습니다. 시스템 기본값을 선택하거나 앱을 다시 실행하세요.")


class Capture:
    def __init__(self, device=None):
        try:
            info = sd.query_devices(device, "input")
        except sd.PortAudioError as error:
            raise ValueError("입력 마이크가 없습니다. 마이크를 연결하고 목록에서 장치를 선택하세요.") from error
        self.name = info["name"]
        self.rate = int(info["default_samplerate"])
        self.chunks = []
        self.frames = 0
        self.level = 0.0
        self.peak = 0.0
        self.error = None
        self.stream = sd.RawInputStream(device=device, samplerate=self.rate, channels=1,
                                        dtype="int16", callback=self._audio)

    def _audio(self, data, frames, timing, status):
        if status:
            self.error = "마이크 입력이 끊겼습니다: " + str(status)
            raise sd.CallbackAbort
        if self.frames + frames > self.rate * MAX_SECONDS:
            self.error = "녹음은 180초까지 가능합니다. 문장을 나누어 말하세요."
            raise sd.CallbackAbort
        pcm = bytes(data)
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        self.level = float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0
        self.peak = max(self.peak, self.level)
        self.chunks.append(pcm)
        self.frames += frames

    def start(self):
        try:
            self.stream.start()
        except Exception:
            self.stream.close()
            raise

    def stop(self, *, discard=False):
        try:
            self.stream.stop()
        finally:
            self.stream.close()
        chunks, self.chunks = self.chunks, []
        if discard:
            return None
        if self.error:
            raise RuntimeError(self.error)
        pcm = b"".join(chunks)
        if not pcm:
            return np.empty(0, dtype=np.float32)
        if self.rate == 16000:
            return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        from faster_whisper.audio import decode_audio
        data = BytesIO()
        with wave.open(data, "wb") as wav:
            wav.setparams((1, 2, self.rate, 0, "NONE", ""))
            wav.writeframes(pcm)
        data.seek(0)
        return decode_audio(data, sampling_rate=16000)
