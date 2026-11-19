"""WAV -> faster-whisper -> dictate.cleanup end-to-end tests (Windows).

Run from the repository root:  .venv\\Scripts\\python -m unittest discover -s windows\\tests -v
The Korean fixture build\\sample.wav is generated with Windows TTS when missing.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "windows"))

from murdic_win import engine  # noqa: E402

SAMPLE = ROOT / "build" / "sample.wav"
LAUNCHER = ROOT / "windows" / "murdic.py"


def setUpModule():
    if not SAMPLE.exists():
        subprocess.run([sys.executable, str(ROOT / "tests" / "sample.py"), str(SAMPLE)], check=True)


def cli(*args, timeout=300):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    run = subprocess.run([sys.executable, str(LAUNCHER), *args], capture_output=True, text=True,
                         encoding="utf-8", timeout=timeout, env=env, cwd=ROOT)
    if run.returncode:
        raise AssertionError(run.stderr[-2000:])
    return [json.loads(line) for line in run.stdout.splitlines() if line.startswith("{")]


class SharedCleanupTests(unittest.TestCase):
    def test_engine_uses_shared_cleanup(self):
        import dictate.cleanup
        self.assertIs(engine.clean, dictate.cleanup.clean)
        self.assertEqual(Path(dictate.cleanup.__file__).resolve().parent, ROOT / "dictate")


class CliTests(unittest.TestCase):
    def check(self, result):
        self.assertEqual(result["audio_s"], 5.0)
        self.assertIn("회의", result["text"])
        self.assertIn("자료", result["text"])
        self.assertTrue(result["text"].endswith("."))
        self.assertGreater(result["processing_ms"], 0)

    def test_cpu_wav(self):
        with tempfile.TemporaryDirectory() as directory:
            result, = cli("--config-dir", directory, "--device", "cpu", "wav", str(SAMPLE), "--json")
        self.check(result)
        self.assertEqual(result["device"], "cpu")

    @unittest.skipUnless(engine.add_cuda_dll_dirs() is not None and engine.cuda_ready(), "no CUDA GPU/cuBLAS")
    def test_cuda_wav(self):
        with tempfile.TemporaryDirectory() as directory:
            result, = cli("--config-dir", directory, "--device", "cuda", "wav", str(SAMPLE), "--json")
        self.check(result)
        self.assertEqual(result["device"], "cuda")

    def test_hints_and_plain_output(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "hints.txt").write_text("회의실\n\n자료\n", encoding="utf-8")
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            run = subprocess.run([sys.executable, str(LAUNCHER), "--config-dir", directory, "--device", "cpu",
                                  "wav", str(SAMPLE)], capture_output=True, text=True, encoding="utf-8",
                                 timeout=300, env=env, check=True)
        self.assertIn("회의실", run.stdout)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.pipeline = engine.Pipeline(cls.folder.name, device="cpu")

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_silence_is_empty_after_conversion(self):
        silent = Path(self.folder.name) / "silence.wav"
        with wave.open(str(silent), "wb") as wav:   # stereo 48 kHz forces conversion
            wav.setparams((2, 2, 48000, 0, "NONE", ""))
            wav.writeframes(bytes(48000 * 4))
        result = self.pipeline.run(silent)
        self.assertEqual(result["audio_s"], 1)
        self.assertEqual(result["text"], "")
        self.assertEqual(result["route"], "silent")

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            self.pipeline.run(Path(self.folder.name) / "missing.wav")

    def test_short_window_matches_sample(self):
        audio = engine.read_wav(SAMPLE)
        raw, route = self.pipeline.engine.transcribe(audio)
        self.assertEqual(route, "short")
        self.assertIn("회의실", raw)

    def test_level_db(self):
        import numpy as np
        self.assertLess(engine.level_db(np.zeros(1600, np.float32)), engine.QUIET_DB)
        self.assertAlmostEqual(engine.level_db(np.full(1600, 0.5, np.float32)), -6.02, places=1)


class HookTests(unittest.TestCase):
    def test_hook_opt_in_and_fallback(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, clear=False):
            os.environ.pop("MURMUR_LLM_KEY", None)
            directory = Path(folder)
            hook = directory / "llm-cleanup.cmd"
            hook.write_text("@echo off\r\nmore >nul\r\necho 수정.\r\n", encoding="utf-8")
            self.assertEqual(engine.optional_hook("원문.", directory), "원문.")
            os.environ["MURMUR_LLM_KEY"] = "test"
            hook.write_text("@echo off\r\nchcp 65001 >nul\r\nmore >nul\r\necho 수정.\r\n", encoding="utf-8")
            self.assertEqual(engine.optional_hook("원문.", directory), "수정.")
            hook.write_text("@echo off\r\nexit /b 1\r\n", encoding="utf-8")
            self.assertEqual(engine.optional_hook("원문.", directory), "원문.")


if __name__ == "__main__":
    unittest.main()
