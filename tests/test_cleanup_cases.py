"""mobile/shared의 cleanup 예문 JSON이 Python clean()과 맞는지 확인한다.

JSON은 mobile/scripts/export_cleanup_cases.py가 만들고, mobile/__tests__/cleanup.test.ts(TS 포팅)도 같은 파일을 읽는다.
"""

import json
import unittest
from pathlib import Path

from dictate.cleanup import clean

SHARED_DIR = Path(__file__).resolve().parent.parent / "mobile" / "shared"


def load_cases(name):
    with (SHARED_DIR / name).open(encoding="utf-8") as f:
        return json.load(f)["cases"]


class SharedCleanupCasesTests(unittest.TestCase):
    def check_file(self, name):
        cases = load_cases(name)
        self.assertTrue(cases, f"{name}에 예문이 없음")
        for case in cases:
            with self.subTest(file=name, raw=case["raw"]):
                self.assertEqual(clean(case["raw"]), case["expected"])
                self.assertEqual(clean(case["expected"]), case["expected"])

    def test_cleanup_cases(self):
        self.check_file("cleanup_cases.json")

    def test_extra_cleanup_cases(self):
        self.check_file("cleanup_extra_cases.json")
