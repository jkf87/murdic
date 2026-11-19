"""Windows unit tests; no model download, microphone access or clipboard mutation."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import wave

import numpy as np

from dictate import backend
from dictate.windows_stt import WindowsSTT
from windows import settings


class PipelineTests(unittest.TestCase):
    def test_windows_does_not_import_murmur_and_uses_utf8_hints(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sys, "platform", "win32"), \
                patch("dictate.windows_stt.WindowsSTT") as factory:
            directory = Path(folder)
            (directory / "hints.txt").write_text("머딕\n\n고유명사\n", encoding="utf-8")
            factory.return_value.transcribe.return_value = SimpleNamespace(
                text="어 오늘 오늘 회의", language="ko", inference_ms=20)
            pipeline = backend.Pipeline(directory)
            result = pipeline.run_audio(np.ones(16000, dtype=np.float32))
            self.assertEqual(result["text"], "오늘 회의.")
            self.assertEqual(result["audio_s"], 1)
            self.assertEqual(factory.return_value.transcribe.call_args.kwargs,
                             {"language": "ko", "domain_hints": "머딕, 고유명사"})

    def test_empty_audio_does_not_call_engine(self):
        with patch.object(sys, "platform", "win32"), patch("dictate.windows_stt.WindowsSTT") as factory:
            result = backend.Pipeline().run_audio(np.array([], dtype=np.float32))
            self.assertEqual(result["text"], "")
            factory.return_value.transcribe.assert_not_called()

    def test_macos_keeps_murmur_and_voice_gate(self):
        stt = MagicMock(DEFAULT_MODEL="original-model")
        vad = MagicMock()
        hub = MagicMock()
        hub.snapshot_download.return_value = "cached-model"
        vad.VoiceActivityDetector.return_value.has_speech.return_value = False
        with patch.object(sys, "platform", "darwin"), patch.dict(sys.modules, {
            "murmur": MagicMock(), "murmur.stt": stt, "murmur.vad": vad,
            "huggingface_hub": hub,
            "huggingface_hub.errors": SimpleNamespace(LocalEntryNotFoundError=FileNotFoundError),
        }):
            pipeline = backend.Pipeline()
            result = pipeline.run_audio(np.zeros(16000, dtype=np.float32))
            stt.WhisperSTT.assert_called_once_with("cached-model")
            stt.WhisperSTT.return_value.preload.assert_called_once()
            stt.WhisperSTT.return_value.transcribe.assert_not_called()
            self.assertEqual(result["text"], "")

    def test_service_recovers_after_bad_request(self):
        pipeline = MagicMock()
        pipeline.run.return_value = {"text": "회의.", "raw": "회의"}
        output = io.StringIO()
        requests = 'not-json\n' + json.dumps({"wav": "sample.wav"}) + '\n'
        with patch.object(sys, "stdin", io.StringIO(requests)):
            backend.serve(pipeline, output)
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([r["event"] for r in records], ["ready", "error", "result"])
        self.assertEqual(records[-1]["text"], "회의.")

    def test_cpu_model_and_lazy_iterator_failures(self):
        library = MagicMock()
        library.WhisperModel.return_value.transcribe.return_value = (
            iter([SimpleNamespace(text=" 회의 자료 ")]), SimpleNamespace(language="ko"))
        with patch.dict(sys.modules, {"faster_whisper": library}), patch.dict(os.environ, {}, clear=True):
            recognizer = WindowsSTT()
            library.WhisperModel.assert_called_once_with("small", device="cpu", compute_type="int8")
            self.assertEqual(recognizer.transcribe(np.zeros(16000)).text, "회의 자료")
            self.assertTrue(library.WhisperModel.return_value.transcribe.call_args.kwargs["vad_filter"])
            def fail():
                raise RuntimeError("decoder failed")
                yield
            library.WhisperModel.return_value.transcribe.return_value = (fail(), SimpleNamespace(language="ko"))
            with self.assertRaisesRegex(RuntimeError, "decoder failed"):
                recognizer.transcribe(np.zeros(16000))

    @unittest.skipUnless(sys.platform == "win32", "Windows decoder")
    def test_stereo_wav_conversion_and_truncated_pcm(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "stereo.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setparams((2, 2, 48000, 0, "NONE", ""))
                wav.writeframes(bytes(48000 * 4))
            audio = backend.read_wav(path)
            self.assertEqual(len(audio), 16000)
            self.assertTrue(np.all(audio == 0))
            with wave.open(str(path), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", ""))
                wav.writeframes(bytes(32000))
            path.write_bytes(path.read_bytes()[:-100])
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                backend.read_wav(path)


class SettingsTests(unittest.TestCase):
    def test_korean_device_round_trip_and_corrupt_file(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            value = {"hotkey": "F8", "microphone": {"name": "마이크", "hostapi": "Windows WASAPI"}}
            settings.save(directory, value)
            self.assertEqual(settings.load(directory), value)
            (directory / "windows.json").write_text("broken", encoding="utf-8")
            self.assertEqual(settings.load(directory), {})
            settings.save(directory, {"hotkey": "invalid", "microphone": 99})
            self.assertEqual(settings.load(directory), {})


@unittest.skipUnless(sys.platform == "win32", "Windows native modules")
class ClipboardTests(unittest.TestCase):
    def setUp(self):
        from windows import paste
        self.paste = paste
        self.data = {13: "원래 텍스트", 49152: b"<b>original</b>"}
        self.sequence = 1
        self.clipboard = MagicMock()
        self.clipboard.RegisterClipboardFormat.return_value = 49153
        self.clipboard.IsClipboardFormatAvailable.side_effect = lambda fmt: fmt in self.data
        self.clipboard.EnumClipboardFormats.side_effect = self.enumerate
        self.clipboard.GetClipboardData.side_effect = self.data.__getitem__
        self.clipboard.EmptyClipboard.side_effect = self.empty
        self.clipboard.SetClipboardData.side_effect = self.put
        self.clipboard.SetClipboardText.side_effect = lambda text, fmt: self.put(fmt, text)
        self.clipboard.GetClipboardSequenceNumber.side_effect = lambda: self.sequence
        self.patch = patch.object(paste, "clipboard", self.clipboard)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def enumerate(self, previous):
        formats = [0] + list(self.data)
        offset = formats.index(previous) + 1
        return formats[offset] if offset < len(formats) else 0

    def empty(self):
        self.data.clear()
        self.sequence += 1

    def put(self, fmt, data):
        self.data[fmt] = data
        self.sequence += 1

    def test_restores_unicode_and_html(self):
        saved = self.data.copy()
        transaction = self.paste.PasteTransaction(1, "새 문장")
        self.assertEqual(self.data[13], "새 문장")
        transaction.restore()
        self.assertEqual(self.data, saved)
        transaction.restore()
        self.assertEqual(self.data, saved)

    def test_subsequent_copy_is_not_overwritten(self):
        transaction = self.paste.PasteTransaction(1, "받아쓰기")
        self.empty()
        self.put(13, "사용자가 새로 복사함")
        transaction.restore()
        self.assertEqual(self.data, {13: "사용자가 새로 복사함"})

    def test_windows_format_synthesis_still_restores_original(self):
        saved = self.data.copy()
        transaction = self.paste.PasteTransaction(1, "받아쓰기")
        self.put(1, b"synthesized ANSI")
        transaction.restore()
        self.assertEqual(self.data, saved)

    def test_changed_text_with_retained_marker_is_not_overwritten(self):
        transaction = self.paste.PasteTransaction(1, "받아쓰기")
        self.put(13, "새 복사")
        transaction.restore()
        self.assertEqual(self.data[13], "새 복사")

    def test_unsupported_handle_fails_without_touching_clipboard(self):
        self.data[2] = 12345
        saved = self.data.copy()
        with self.assertRaises(RuntimeError):
            self.paste.PasteTransaction(1, "받아쓰기")
        self.assertEqual(self.data, saved)
        self.clipboard.EmptyClipboard.assert_not_called()

    def test_restore_can_retry_after_clipboard_contention(self):
        saved = self.data.copy()
        transaction = self.paste.PasteTransaction(1, "받아쓰기")
        self.clipboard.OpenClipboard.side_effect = RuntimeError("busy")
        with patch.object(self.paste.time, "sleep"), self.assertRaises(RuntimeError):
            transaction.restore()
        self.clipboard.OpenClipboard.side_effect = None
        transaction.restore()
        self.assertEqual(self.data, saved)

    def test_changed_target_or_held_modifier_never_sends_keys(self):
        with patch.object(self.paste.win32gui, "GetForegroundWindow", return_value=2), \
                patch.object(self.paste.user32, "SendInput") as send:
            with self.assertRaises(RuntimeError):
                self.paste.post_paste(1)
            send.assert_not_called()
        with patch.object(self.paste.win32gui, "GetForegroundWindow", return_value=1), \
                patch.object(self.paste.win32gui, "IsWindow", return_value=True), \
                patch.object(self.paste, "modifiers_down", return_value=True), \
                patch.object(self.paste.user32, "SendInput") as send:
            with self.assertRaises(RuntimeError):
                self.paste.post_paste(1)
            send.assert_not_called()


@unittest.skipUnless(sys.platform == "win32", "Windows audio dependencies")
class CaptureTests(unittest.TestCase):
    def test_quick_release_without_frames_returns_empty_audio(self):
        from windows import audio
        with patch.object(audio.sd, "query_devices", return_value={"name": "mic", "default_samplerate": 48000}), \
                patch.object(audio.sd, "RawInputStream"):
            self.assertEqual(len(audio.Capture().stop()), 0)

    def test_native_rate_capture_resamples_without_files(self):
        from windows import audio
        with patch.object(audio.sd, "query_devices", return_value={"name": "mic", "default_samplerate": 48000}), \
                patch.object(audio.sd, "RawInputStream"):
            capture = audio.Capture()
            capture._audio(bytes(96000), 48000, None, False)
            result = capture.stop()
            self.assertEqual(len(result), 16000)
            self.assertEqual(capture.chunks, [])
            self.assertTrue(np.all(result == 0))

    def test_capture_limit_and_discard(self):
        from windows import audio
        with patch.object(audio.sd, "query_devices", return_value={"name": "mic", "default_samplerate": 16000}), \
                patch.object(audio.sd, "RawInputStream"):
            capture = audio.Capture()
            capture.frames = 16000 * audio.MAX_SECONDS
            with self.assertRaises(audio.sd.CallbackAbort):
                capture._audio(bytes(200), 100, None, False)
            self.assertIn("180", capture.error)
            self.assertIsNone(capture.stop(discard=True))
            self.assertEqual(capture.chunks, [])

    def test_missing_device_is_not_replaced_by_another_index(self):
        from windows import audio
        with patch.object(audio, "inputs", return_value=[(9, {"name": "new mic", "hostapi": "WASAPI"})]):
            with self.assertRaises(ValueError):
                audio.resolve_device({"name": "old mic", "hostapi": "WASAPI"})
            self.assertEqual(audio.resolve_device({"name": "new mic", "hostapi": "WASAPI"}), 9)


@unittest.skipUnless(sys.platform == "win32", "Windows desktop state machine")
class DesktopStateTests(unittest.TestCase):
    def test_focus_change_retains_result_but_never_pastes(self):
        from windows.__main__ import App
        app = App.__new__(App)
        app.result = MagicMock()
        app.target = 10
        app.ready = MagicMock()
        app.try_paste = MagicMock()
        with patch("windows.__main__.win32gui.GetForegroundWindow", return_value=11):
            app.receive_result({"text": "한국어 결과."})
        app.result.insert.assert_called_once_with("1.0", "한국어 결과.")
        app.try_paste.assert_not_called()
        app.ready.assert_called_once()

    def test_loading_or_processing_never_opens_microphone(self):
        from windows.__main__ import App
        app = App.__new__(App)
        with patch("windows.__main__.Capture") as capture:
            for state in ("loading", "processing", "pasting", "recording", "failed"):
                app.state = state
                app.start_capture()
            capture.assert_not_called()

    def test_cancel_discards_audio_and_clears_capture(self):
        from windows.__main__ import App
        app = App.__new__(App)
        capture = app.capture = MagicMock()
        app.ready = MagicMock()
        app.cancel("cancelled")
        capture.stop.assert_called_once_with(discard=True)
        self.assertIsNone(app.capture)
        app.ready.assert_called_once_with("cancelled")


if __name__ == "__main__":
    unittest.main()
