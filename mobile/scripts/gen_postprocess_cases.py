#!/usr/bin/env python3
"""Murmur 원본 후처리로 기대값을 만들어 mobile/shared/postprocess_cases.json에 쓴다.

원본(정답)
  - ~/.murmur/core/src/murmur/postprocess.py  is_hallucination, apply_term_corrections
  - ~/.murmur/core/src/murmur/vad.py          VoiceActivityDetector (맥판과 같은 기본 구성)
  - 맥판 main 브랜치 dictate/backend.py       filter_transcript, 0.3초(4800샘플) 말소리 창 계산

실행: /opt/homebrew/bin/python3 mobile/scripts/gen_postprocess_cases.py [--mac-root ~/murmur-dictate]
JS 쪽 mobile/__tests__/postprocess.test.ts가 같은 입력을 넣어 결과가 같은지 본다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "shared" / "postprocess_cases.json"

parser = argparse.ArgumentParser()
parser.add_argument("--mac-root", default=str(Path.home() / "murmur-dictate"),
                    help="main 브랜치가 체크아웃된 맥판 폴더(dictate/backend.py의 filter_transcript)")
args = parser.parse_args()
sys.path.insert(0, args.mac_root)

import murmur.postprocess as pp  # noqa: E402
import murmur.vad as vad_mod  # noqa: E402
from murmur.vad import VoiceActivityDetector  # noqa: E402
from dictate.backend import filter_transcript  # noqa: E402

HALLUCINATION_INPUTS = [
    "", " ", "ㅁ", "a", "네", "네.", "  감사  ",
    "네 네 네", "네 네 네 네", "Hello hello HELLO.", "네, 네! 아니요", "a b c", "하나 둘 하나 둘",
    "안녕하세요 반갑습니다 좋은 아침", "오늘 회의는 세 시에 합니다.",
    "안녕하세요안녕하세요안녕하세요", "abcdeabcdeabcde", "abcdabcdabcd", "가나다라마가나다라마가나다라마끝",
    "좋아요 좋아요 좋아요 정말로요", "x" * 160,
    "감사합니다", "감사합니다.", "감사합니다..", "감사합니다!", "감사합니다 여러분",
    "시청해 주셔서 감사합니다.", "시청해주셔서 감사합니다", "구독과 좋아요", "좋아요와 구독.",
    "도움이 되었습니다", "날씨였습니다.", "오늘 날씨였습니다",
    "... ... ... ... ...", "음... 그... 저... 네... 아...", "음... 그... 저... 네...",
    "Привет мир как дела", "안녕 Привет", "안녕하세요 😀", "😀😀", "안녕하세요 ✅ 확인했습니다 ✅",
    "テストです。ありがとう", "中文测试一下可以吗", "가격은 30% 할인, (약) 5,000원~",
    "「인용」『책』（괄호）、。", "탭\t구분\n줄바꿈", "A·B·C…", "Cost: $5 & tax #1",
    "ﾃｽﾄ半角カナ", "Ｆｕｌｌｗｉｄｔｈ 전각", "à la carte café", "Straße groß",
    # 코드포인트 vs UTF-16 길이에 따라 결과가 갈리는 예(이모지는 UTF-16 2칸)
    "가나다라마😀", "가나다라마바😀", "가나다라마바사😀", "😀가", "가😀가😀가😀가😀가😀가😀",
    "𠀀𠀁𠀂𠀃𠀄𠀀𠀁𠀂𠀃𠀄𠀀𠀁𠀂𠀃𠀄",
]

TERM_INPUTS = [
    "클드", "클로드", "클로드 코드", "클라우드 코드", "클드 코드", "쉬프트 키", "코덱스",
    "코덱스랑 클로드로 작업해요", "클라우드 코드로 쉬프트+엔터", "클로드클로드", "그냥 문장입니다.",
    "클라우드", "클라우드 코드 클드 코드 코덱스", "",
]

FILTER_INPUTS = [
    ("시청해 주셔서 감사합니다.", 1), ("감사합니다", 0), ("감사합니다", 2), ("감사합니다", 3),
    ("감사합니다.", 4), ("감사합니다..", 9), ("시청해주셔서 감사합니다", 3), ("구독과 좋아요", 10),
    ("감사합니다 감사합니다 감사합니다", 10), ("네 네 네 네", 5), ("ㅁ", 5), ("", 5), ("   ", 5), (None, 3),
    ("코덱스랑 클로드로 작업해요", 6), ("  클로드 코드 열어 줘  ", 4), ("😀😀😀 감사합니다", 9),
    ("오늘 회의는 세 시에 합니다.", 0), ("... ... ... ... ...", 20), ("날씨였습니다", 3),
]

# 말소리 창: 정수 PCM을 규칙으로 기술한다(양쪽이 똑같은 샘플을 만든다).
#   {"const": v, "n": 샘플 수}            값 v를 n개
#   {"square": v, "period": p, "n": n}    +v p/2개, -v p/2개 반복(평균 0, RMS = v)
SPEECH_WINDOW_INPUTS = {
    "silence_1s": [{"const": 0, "n": 16000}],
    "loud_1s": [{"square": 3000, "period": 32, "n": 16000}],
    "loud_0_9s_exact": [{"square": 3000, "period": 32, "n": 14400}],
    "loud_0_6s_then_silence": [{"square": 3000, "period": 32, "n": 9600}, {"const": 0, "n": 9600}],
    "quiet_below_threshold": [{"square": 150, "period": 32, "n": 16000}],
    "near_threshold_below": [{"square": 160, "period": 32, "n": 16000}],
    "near_threshold_above": [{"square": 170, "period": 32, "n": 16000}],
    "dc_offset_above": [{"const": 200, "n": 16000}],
    "partial_last_window": [{"const": 0, "n": 4800}, {"square": 3000, "period": 32, "n": 100}],
    "tiny_tail_window": [{"square": 3000, "period": 32, "n": 4801}],
    "burst_inside_window": [{"const": 0, "n": 2000}, {"square": 12000, "period": 32, "n": 400},
                            {"const": 0, "n": 2400}],
    "clip_max": [{"square": 32767, "period": 2, "n": 9600}],
    "clip_min_const": [{"const": -32768, "n": 4800}],
    "empty": [],
}


def build_pcm(spec: list[dict]) -> np.ndarray:
    parts = []
    for seg in spec:
        n = seg["n"]
        if "const" in seg:
            parts.append(np.full(n, seg["const"], dtype=np.int16))
        else:
            half = seg["period"] // 2
            idx = np.arange(n)
            parts.append(np.where((idx // half) % 2 == 0, seg["square"], -seg["square"]).astype(np.int16))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int16)


def speech_windows(pcm: np.ndarray) -> int:
    # 맥판 backend.py와 같은 식: float32 /32768, 4800샘플(0.3초) 창마다 has_speech.
    audio = pcm.astype(np.float32) / 32768
    vad = VoiceActivityDetector()
    return int(sum(vad.has_speech(audio[i:i + 4800]) for i in range(0, len(audio), 4800)))


cases = {
    "_source": {
        "postprocess": "jkf87/murmur core/src/murmur/postprocess.py",
        "vad": "jkf87/murmur core/src/murmur/vad.py",
        "vad_backend": "webrtc" if vad_mod._HAS_WEBRTC else "rms",
        "rms_threshold": vad_mod.DEFAULT_RMS_THRESHOLD,
        "filter_transcript": "jkf87/murdic main dictate/backend.py",
        "term_corrections": pp.TERM_CORRECTIONS,
    },
    "hallucination": [{"input": s, "expected": pp.is_hallucination(s)} for s in HALLUCINATION_INPUTS],
    "terms": [{"input": s, "expected": pp.apply_term_corrections(s)} for s in TERM_INPUTS],
    "filter": [{"input": s, "speechWindows": w, "expected": filter_transcript(s, w)} for s, w in FILTER_INPUTS],
    "speechWindows": [{"name": k, "pcm": v, "expected": speech_windows(build_pcm(v))}
                      for k, v in SPEECH_WINDOW_INPUTS.items()],
}

if cases["_source"]["vad_backend"] != "rms":
    sys.exit("webrtcvad가 설치돼 있다. 맥판 실제 동작(RMS)과 달라지므로 webrtcvad 없는 환경에서 생성할 것.")

OUT.write_text(json.dumps(cases, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"{OUT}: hallucination {len(cases['hallucination'])}, terms {len(cases['terms'])}, "
      f"filter {len(cases['filter'])}, speechWindows {len(cases['speechWindows'])}")
