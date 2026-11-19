"""Murmur's transcription tuning, ported 1:1 for the faster-whisper path.

Source: jkf87/murmur core/src/murmur/postprocess.py (is_hallucination,
TERM_CORRECTIONS, apply_term_corrections), core/src/murmur/vad.py
(VoiceActivityDetector) and app/Murmur/Views/SettingsView.swift (hint presets).
The speech-window exception for "감사합니다" follows murdic main's
dictate/backend.py `filter_transcript`. See docs/STT_TUNING.md.
Tests compare this port with outputs of the original code
(windows/tests/fixtures/murmur_postprocess.json).
"""
from __future__ import annotations

import re

import numpy as np

# --- murmur/postprocess.py ----------------------------------------------------
TERM_CORRECTIONS = {
    "클드": "Claude", "클로드": "Claude",
    "클라우드 코드": "Claude Code", "클드 코드": "Claude Code",
    "쉬프트": "시프트", "코덱스": "Codex",
}

_HALLUCINATION_PHRASES = [
    "도움이 되었습니다", "감사합니다", "구독과 좋아요",
    "날씨였습니다", "시청해 주셔서 감사합니다",
    "시청해주셔서 감사합니다", "좋아요와 구독",
]


def is_hallucination(text: str) -> bool:
    """Detect Whisper hallucination patterns."""
    if not text:
        return True
    stripped = text.strip()
    if len(stripped) < 2:
        return True
    words = stripped.split()
    if not words:
        return True

    # Pattern 1: single word/token repeated
    if len(words) >= 3:
        unique = set(w.lower().strip(".,!?") for w in words)
        if len(unique) <= 2:
            return True

    # Pattern 2: substring repeating 3+ times
    for chunk_len in range(5, min(len(stripped) // 3, 50)):
        for start in range(len(stripped) - chunk_len * 3 + 1):
            chunk = stripped[start:start + chunk_len]
            if (chunk == stripped[start + chunk_len:start + chunk_len * 2]
                    == stripped[start + chunk_len * 2:start + chunk_len * 3]):
                return True

    # Pattern 3: non-recognized script garbage
    # Allow: Korean, Japanese (hiragana, katakana, kanji), Chinese, English, digits, basic punct
    clean_chars = re.sub(r'[가-힣぀-ゟ゠-ヿ一-鿿㐀-䶿a-zA-Z0-9\s.,!?…·\-\(\)\"\'%:;~、。「」『』（）]', '', stripped)
    if len(clean_chars) > len(stripped) * 0.15:
        return True

    # Pattern 4: known hallucination phrases
    clean = stripped.rstrip(".")
    if clean in _HALLUCINATION_PHRASES:
        return True

    # Pattern 5: too many "..."
    if stripped.count("...") >= 5:
        return True

    return False


def apply_term_corrections(text: str, extra=()) -> str:
    """Apply term corrections for common Whisper misidentifications.

    `extra` holds the user's own (wrong, right) pairs from terms.txt; they run
    after Murmur's built-in list."""
    for wrong, correct in TERM_CORRECTIONS.items():
        text = text.replace(wrong, correct)
    for wrong, correct in extra:
        text = text.replace(wrong, correct)
    return text


# --- murdic main: dictate/backend.py filter_transcript ---------------------------
# Murmur's hallucination list includes phrases people really dictate ("감사합니다").
# Trust them when the VAD heard at least ~0.9 s of speech (three 0.3 s windows).
REAL_SPEECH_WINDOWS = 3
_PHRASES = {"도움이 되었습니다", "감사합니다", "구독과 좋아요", "날씨였습니다",
            "시청해 주셔서 감사합니다", "시청해주셔서 감사합니다", "좋아요와 구독"}


def filter_transcript(raw, speech_windows, extra_terms=()):
    """Murmur post-processing: drop Whisper hallucinations, then fix known terms."""
    text = (raw or "").strip()
    if not text:
        return ""
    if is_hallucination(text):
        phrase_only = text.rstrip(".") in _PHRASES and speech_windows >= REAL_SPEECH_WINDOWS
        if not phrase_only:
            return ""
    return apply_term_corrections(text, extra_terms)


# --- murmur/vad.py ------------------------------------------------------------
DEFAULT_AGGRESSIVENESS = 2
DEFAULT_FRAME_MS = 30
DEFAULT_SPEECH_RATIO = 0.3
DEFAULT_RMS_THRESHOLD = 0.005
WINDOW = 4800  # murdic checks 0.3 s windows


class VoiceActivityDetector:
    """WebRTC VAD when `webrtcvad` is installed, otherwise the RMS fallback.

    murdic's macOS setup installs Murmur core without the `vad` extra, so it runs
    the RMS fallback; the Windows build does the same (webrtcvad is not bundled)."""

    def __init__(self, sample_rate=16000, use_webrtc=True, aggressiveness=DEFAULT_AGGRESSIVENESS,
                 frame_ms=DEFAULT_FRAME_MS, speech_ratio=DEFAULT_SPEECH_RATIO,
                 rms_threshold=DEFAULT_RMS_THRESHOLD):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.speech_ratio = speech_ratio
        self.rms_threshold = rms_threshold
        self._vad = None
        if use_webrtc:
            try:
                import webrtcvad
                self._vad = webrtcvad.Vad(aggressiveness)
            except ImportError:
                pass

    def has_speech(self, audio: np.ndarray) -> bool:
        if self._vad is not None:
            return self._webrtc_check(audio)
        return self._rms_check(audio)

    def _rms_check(self, audio: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean(audio ** 2)))
        return rms >= self.rms_threshold

    def _webrtc_check(self, audio: np.ndarray) -> bool:
        pcm_bytes = (audio * 32767).astype(np.int16).tobytes()
        frame_bytes = int(self.sample_rate * self.frame_ms / 1000) * 2
        total_frames = len(pcm_bytes) // frame_bytes
        if total_frames == 0:
            return False
        voiced = 0
        for i in range(total_frames):
            try:
                if self._vad.is_speech(pcm_bytes[i * frame_bytes:(i + 1) * frame_bytes], self.sample_rate):
                    voiced += 1
            except Exception:
                continue
        return (voiced / total_frames) >= self.speech_ratio


def speech_windows(audio, vad=None):
    """Number of 0.3 s windows with speech (dictate/backend.py counts the same way)."""
    vad = vad or VoiceActivityDetector()
    return sum(vad.has_speech(audio[i:i + WINDOW]) for i in range(0, len(audio), WINDOW))


# --- Murmur SettingsView.swift: domain hint presets (initial_prompt) ------------------
HINT_PRESETS = {
    "none": ("(없음)", ""),
    "news": ("뉴스·시사", "트럼프, 나토, NATO, 관세, 대통령"),
    "space": ("우주·NASA", "아르테미스, NASA, SLS, 스타십, 오리온"),
    "it": ("IT·개발", "Claude Code, HWPX, GitHub, API, SDK"),
    "medical": ("의학·건강", "혈압, 당뇨, MRI, CT, 항생제"),
    "finance": ("경제·금융", "GDP, 금리, 인플레이션, 연준, 코스피"),
    "sports": ("스포츠", "손흥민, 토트넘, 프리미어리그, FIFA"),
}


def build_prompt(preset, user_terms):
    """Preset hints, then the user's proper nouns (hints.txt), comma-separated."""
    parts = [HINT_PRESETS.get(preset, HINT_PRESETS["none"])[1]] + [t for t in user_terms if t]
    return ", ".join(p for p in parts if p) or None


def parse_terms(text):
    """terms.txt: one `잘못 들린 말 => 바른 표기` per line; # starts a comment."""
    pairs = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if "=>" in line:
            wrong, right = (part.strip() for part in line.split("=>", 1))
            if wrong:
                pairs.append((wrong, right))
    return pairs
