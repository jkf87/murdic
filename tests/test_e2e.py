import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

if importlib.util.find_spec("murmur") is None:  # Windows uses windows/tests/test_e2e_windows.py
    raise unittest.SkipTest("Murmur core (macOS backend) is not installed")

from dictate.backend import optional_hook  # noqa: E402


class IntegrationTests(unittest.TestCase):
    def test_real_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, "-m", "dictate", "--config-dir", directory, "wav",
                       "build/sample.wav", "--json"]
            run = subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
            result = json.loads(run.stdout)
            self.assertEqual(result["audio_s"], 5.0)
            self.assertIn("회의", result["text"])
            self.assertIn("자료", result["text"])
            self.assertGreater(result["processing_ms"], 0)

    def test_service_silence_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            silent = Path(directory) / "silence.wav"
            # Force conversion from stereo 48 kHz.
            with wave.open(str(silent), "wb") as wav:
                wav.setparams((2, 2, 48000, 0, "NONE", ""))
                wav.writeframes(bytes(48000 * 4))
            requests = [dict(wav=str(silent) + ".missing"), dict(wav=str(silent))]
            proc = subprocess.run([sys.executable, "-m", "dictate", "--config-dir", directory, "serve"],
                                  input="".join(json.dumps(x) + "\n" for x in requests),
                                  check=True, capture_output=True, text=True, timeout=120)
            ready, error, result = map(json.loads, proc.stdout.splitlines())
            self.assertEqual([ready["event"], error["event"], result["event"]], ["ready", "error", "result"])
            self.assertEqual(result["audio_s"], 1)
            self.assertEqual(result["text"], "")

    def test_hook_opt_in_and_fallback(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, clear=True):
            directory = Path(folder)
            hook = directory / "llm-cleanup"
            hook.write_text("#!/bin/sh\ncat >/dev/null\necho '수정.'\n")
            hook.chmod(0o700)
            self.assertEqual(optional_hook("원문.", directory), "원문.")
            os.environ["MURMUR_LLM_KEY"] = "test"
            self.assertEqual(optional_hook("원문.", directory), "수정.")
            hook.write_text("#!/bin/sh\nexit 1\n")
            self.assertEqual(optional_hook("원문.", directory), "원문.")
