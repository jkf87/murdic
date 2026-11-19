"""Windows CPU transcription; no Murmur/MLX dependency on this platform."""
import os
import time
from types import SimpleNamespace


class WindowsSTT:
    def __init__(self):
        from faster_whisper import WhisperModel
        self.model = WhisperModel(os.environ.get("MURDIC_WHISPER_MODEL", "small"),
                                  device="cpu", compute_type="int8")

    def transcribe(self, audio, *, language="ko", domain_hints=None):
        started = time.perf_counter()
        segments, info = self.model.transcribe(
            audio, language=language, initial_prompt=domain_hints,
            condition_on_previous_text=False, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        # The iterator does the actual inference; errors must reach the caller.
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return SimpleNamespace(text=text, language=info.language,
                               inference_ms=(time.perf_counter() - started) * 1000)
