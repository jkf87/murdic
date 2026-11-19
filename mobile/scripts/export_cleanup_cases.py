#!/usr/bin/env python3
"""모바일 TS 포팅 검증용 cleanup 예문 JSON 생성.

기본: tests/test_cleanup.py의 examples 리스트를 ast로 읽어 mobile/shared/cleanup_cases.json을 만든다.
--extra: 아래 EXTRA_RAW를 dictate/cleanup.py의 clean()에 넣어 expected를 채운
         mobile/shared/cleanup_extra_cases.json을 만든다.

실행 (저장소 루트에서):
  PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3 mobile/scripts/export_cleanup_cases.py
  PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3 mobile/scripts/export_cleanup_cases.py --extra
"""

import argparse
import ast
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
MOBILE_DIR = SCRIPTS_DIR.parent
REPO_DIR = MOBILE_DIR.parent
SHARED_DIR = MOBILE_DIR / "shared"
TEST_FILE = REPO_DIR / "tests" / "test_cleanup.py"
CASES_OUT = SHARED_DIR / "cleanup_cases.json"
EXTRA_OUT = SHARED_DIR / "cleanup_extra_cases.json"

sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO_DIR))
from dictate.cleanup import clean  # noqa: E402

# 필러·반복·"아니" 정정·물음표·영어 섞임·숫자 위주. 정답은 손으로 쓰지 않고 clean() 출력으로 채운다.
EXTRA_RAW = [
    "어 그러니까 음 3시에 만나요",
    "회의록 회의록 정리해서 보내 주세요",
    "이 API 응답 이 API 응답 확인해 줄 수 있어요?",
    "음... 내일 오전 9시, 아니 10시에 봐요",
    "PR 리뷰는 금요일 아니 그게 아니라 목요일에 해요",
    "그 어 음 파일 크기가 3.5GB예요",
    "음,네 맞아요 맞아요",
    "음 2024년 11월 19일 맞아요?",
    "Docker 컨테이너 컨테이너 재시작 어 해 주실래요",
    "정말요?진짜 진짜 좋아요",
]


def load_examples(path: Path) -> list[dict[str, str]]:
    """test_examples 안의 examples = [(raw, expected), ...]를 AST로 읽는다 (테스트 파일은 실행하지 않음)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assigns = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "examples" for t in node.targets)
    ]
    if len(assigns) != 1:
        raise SystemExit(f"examples 할당이 {len(assigns)}개임 (1개여야 함)")
    cases = []
    for pair in ast.literal_eval(assigns[0].value):
        if not (isinstance(pair, tuple) and len(pair) == 2 and all(isinstance(s, str) for s in pair)):
            raise SystemExit(f"(raw, expected) 문자열 쌍이 아님: {pair!r}")
        cases.append({"raw": pair[0], "expected": pair[1]})
    return cases


def check_pairs(cases: list[dict[str, str]]) -> None:
    """clean(raw) == expected 이고 clean(expected) == expected 인지 확인 (아니면 JSON을 만들지 않음)."""
    for case in cases:
        raw, expected = case["raw"], case["expected"]
        if clean(raw) != expected or clean(expected) != expected:
            raise SystemExit(f"Python clean()과 맞지 않음: raw={raw!r} expected={expected!r}")


def write_json(path: Path, source: str, cases: list[dict[str, str]]) -> None:
    payload = {"source": source, "cases": cases}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(cases)}쌍 -> {path.relative_to(REPO_DIR)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="모바일 TS 포팅용 cleanup 예문 JSON 생성")
    parser.add_argument(
        "--extra",
        action="store_true",
        help="EXTRA_RAW를 clean()으로 돌려 cleanup_extra_cases.json 생성",
    )
    args = parser.parse_args()
    SHARED_DIR.mkdir(parents=True, exist_ok=True)

    if args.extra:
        cases = [{"raw": raw, "expected": clean(raw)} for raw in EXTRA_RAW]
        check_pairs(cases)
        write_json(
            EXTRA_OUT,
            "dictate/cleanup.py clean() 출력 (export_cleanup_cases.py --extra)",
            cases,
        )
    else:
        cases = load_examples(TEST_FILE)
        check_pairs(cases)
        write_json(CASES_OUT, "tests/test_cleanup.py", cases)


if __name__ == "__main__":
    main()
