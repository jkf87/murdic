"""Regenerate windows/tests/fixtures/murmur_postprocess.json from Murmur's original code.

    curl -o postprocess.py https://raw.githubusercontent.com/jkf87/murmur/master/core/src/murmur/postprocess.py
    python -I windows\\tools\\murmur_fixture.py postprocess.py

The fixture stores the original `is_hallucination` and `apply_term_corrections`
results for a corpus; windows/tests/test_postprocess_windows.py checks the port.
"""
import importlib.util
import json
import sys
from pathlib import Path

CORPUS = [
    "", " ", "a", "가", "네", "네.", "감사합니다", "감사합니다.", "감사합니다..", "감사합니다!",
    "시청해 주셔서 감사합니다.", "시청해주셔서 감사합니다", "구독과 좋아요", "좋아요와 구독.",
    "도움이 되었습니다", "날씨였습니다.", "오늘 회의 정말 감사합니다.",
    "네 네 네 네", "네 네 네", "좋아요 좋아요 좋아요 좋아요", "아니 네 아니 네", "Yes, yes, yes.",
    "가나다라마가나다라마가나다라마", "회의실 회의실 회의실 회의실", "abcdeabcdeabcde",
    "오늘 오후 3시에 회의실에서 만나요. 준비한 자료도 가져오세요.",
    "음... 음... 음... 음... 음...", "그러니까... 음... 네...", "ㅁ", "ㅋㅋㅋㅋㅋ", "ㅋㅋ 진짜요",
    "Привет как дела", "مرحبا كيف حالك", "♪♪♪ 음악 ♪♪♪", "100% 확실해요!", "(웃음) 그렇죠~",
    "東京に行きます。", "我们明天见。", "「인용」입니다",
    "코덱스랑 클로드로 작업해요", "클로드 코드로 만들어요", "클라우드 코드 설치", "클드 코드 켜 줘",
    "쉬프트 키를 누르세요", "클드에게 물어봐요", "Claude Code는 이미 영어예요",
    "내일 세 시, 아니 네 시에 만나요.", "API API 응답을 볼까요?",
]


def main():
    spec = importlib.util.spec_from_file_location("murmur_postprocess", sys.argv[1])
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    rows = [dict(text=text, is_hallucination=original.is_hallucination(text),
                 corrected=original.apply_term_corrections(text)) for text in CORPUS]
    out = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "murmur_postprocess.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(dict(source="jkf87/murmur core/src/murmur/postprocess.py (master)",
                                   term_corrections=original.TERM_CORRECTIONS, cases=rows),
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(rows)} cases -> {out}")


if __name__ == "__main__":
    main()
