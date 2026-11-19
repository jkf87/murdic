"""The faster-whisper path reproduces Murmur's tuning (docs/STT_TUNING.md)."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from murdic_win import engine, postprocess  # noqa: E402
from murdic_win.postprocess import (HINT_PRESETS, apply_term_corrections, build_prompt,  # noqa: E402
                                    filter_transcript, is_hallucination, parse_terms, speech_windows)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "murmur_postprocess.json").read_text(encoding="utf-8"))


class MatchesMurmurOriginal(unittest.TestCase):
    def test_term_table(self):
        self.assertEqual(postprocess.TERM_CORRECTIONS, FIXTURE["term_corrections"])
        self.assertEqual(list(postprocess.TERM_CORRECTIONS), list(FIXTURE["term_corrections"]))

    def test_cases_from_original_code(self):
        for case in FIXTURE["cases"]:
            with self.subTest(text=case["text"]):
                self.assertEqual(is_hallucination(case["text"]), case["is_hallucination"])
                self.assertEqual(apply_term_corrections(case["text"]), case["corrected"])


class FilterTranscript(unittest.TestCase):
    """Same cases as murdic main's tests/test_postprocess.py (macOS backend)."""

    def test_drops_whisper_hallucinations_on_little_speech(self):
        self.assertEqual(filter_transcript("시청해 주셔서 감사합니다.", 1), "")
        self.assertEqual(filter_transcript("감사합니다", 0), "")
        self.assertEqual(filter_transcript("네 네 네 네", 5), "")
        self.assertEqual(filter_transcript("ㅁ", 5), "")

    def test_keeps_real_thanks_when_speech_was_heard(self):
        self.assertEqual(filter_transcript("감사합니다.", 4), "감사합니다.")

    def test_applies_murmur_term_corrections(self):
        self.assertEqual(filter_transcript("코덱스랑 클로드로 작업해요", 6), "Codex랑 Claude로 작업해요")

    def test_exception_only_skips_the_phrase_rule(self):
        self.assertEqual(filter_transcript("감사합니다.", 2), "")            # below three windows
        self.assertEqual(filter_transcript("시청해 주셔서 감사합니다", 3), "시청해 주셔서 감사합니다")
        self.assertEqual(filter_transcript("감사합니다 감사합니다 감사합니다", 9), "")  # repetition rule stays

    def test_user_terms_run_after_builtin(self):
        terms = parse_terms("# 주석\n머딕 => murdic\n허드 코어=>herdr-core\n잘못된 줄\n")
        self.assertEqual(terms, [("머딕", "murdic"), ("허드 코어", "herdr-core")])
        self.assertEqual(filter_transcript("머딕과 클로드", 5, terms), "murdic과 Claude")


class SpeechWindows(unittest.TestCase):
    def test_rms_windows_like_murmur_fallback(self):
        vad = postprocess.VoiceActivityDetector(use_webrtc=False)
        loud = np.full(4800, 0.01, np.float32)
        quiet = np.full(4800, 0.004, np.float32)
        audio = np.concatenate([quiet, loud, loud, quiet, loud[:100]])
        self.assertEqual(speech_windows(audio, vad), 3)   # the trailing partial window counts too
        self.assertEqual(speech_windows(np.zeros(16000, np.float32), vad), 0)


class Prompts(unittest.TestCase):
    def test_presets_match_murmur_settings(self):
        self.assertEqual([hints for _, hints in HINT_PRESETS.values()], [
            "", "트럼프, 나토, NATO, 관세, 대통령", "아르테미스, NASA, SLS, 스타십, 오리온",
            "Claude Code, HWPX, GitHub, API, SDK", "혈압, 당뇨, MRI, CT, 항생제",
            "GDP, 금리, 인플레이션, 연준, 코스피", "손흥민, 토트넘, 프리미어리그, FIFA"])

    def test_user_nouns_follow_preset(self):
        self.assertEqual(build_prompt("it", ["머딕", "", "허드"]), "Claude Code, HWPX, GitHub, API, SDK, 머딕, 허드")
        self.assertEqual(build_prompt("none", ["머딕"]), "머딕")
        self.assertIsNone(build_prompt("none", []))
        self.assertIsNone(build_prompt("unknown", [""]))

    def test_pipeline_reads_preset_and_hints(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "hints.txt").write_text("﻿머딕\n", encoding="utf-8")
            pipeline = engine.Pipeline(folder, engine=object(), preset="news")
            self.assertEqual(pipeline.hints(), "트럼프, 나토, NATO, 관세, 대통령, 머딕")


class DecodingSettings(unittest.TestCase):
    def test_murmur_decode_options(self):
        self.assertEqual(engine.DECODE, dict(
            beam_size=1, best_of=1, temperature=0.0, condition_on_previous_text=False,
            no_speech_threshold=0.6, compression_ratio_threshold=1.8, log_prob_threshold=-1.0))


if __name__ == "__main__":
    unittest.main()
