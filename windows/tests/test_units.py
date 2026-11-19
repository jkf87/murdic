"""Unit tests for the hotkey state machine, microphone selection and clipboard."""
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from murdic_win import audio, hotkey, paste  # noqa: E402
from murdic_win.audio import InputDevices, Microphone, MicrophoneSelection  # noqa: E402
from murdic_win.hotkey import HOTKEYS, HoldMachine, Key  # noqa: E402
from murdic_win.settings import Settings  # noqa: E402


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


RALT_DOWN = Key(hotkey.VK_RMENU, 0x38, True, True)
RALT_UP = RALT_DOWN._replace(down=False)
HANGUL_DOWN = Key(hotkey.VK_HANGUL, 0x38, True, True)   # Korean type-1 layout, right Alt position
HANGUL_UP = HANGUL_DOWN._replace(down=False)
A_DOWN = Key(0x41, 0x1E, False, True)


class HoldMachineTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.machine = HoldMachine(HOTKEYS["right_alt"], self.clock)

    def test_hold_records_and_swallows(self):
        self.assertEqual(self.machine.feed(RALT_DOWN), (True, [("start",)]))
        self.assertEqual(self.machine.feed(RALT_DOWN), (True, []))       # auto-repeat
        self.clock.now += 1.2
        self.assertEqual(self.machine.feed(RALT_UP), (True, [("finish",)]))
        self.assertEqual(self.machine.state, "idle")

    def test_korean_right_alt_is_hangul(self):
        self.assertEqual(self.machine.feed(HANGUL_DOWN), (True, [("start",)]))
        self.clock.now += 0.1
        suppress, actions = self.machine.feed(HANGUL_UP)
        # A tap keeps 한/영 working: cancel the take and replay the key.
        self.assertTrue(suppress)
        self.assertEqual(actions, [("cancel", "tap"), ("inject", [HANGUL_DOWN, HANGUL_UP])])

    def test_dedicated_hangul_key_is_not_the_hotkey(self):
        self.assertEqual(self.machine.feed(Key(hotkey.VK_HANGUL, 0x72, False, True)), (False, []))

    def test_alt_tap_is_not_replayed(self):
        self.machine.feed(RALT_DOWN)
        self.clock.now += 0.05
        self.assertEqual(self.machine.feed(RALT_UP), (True, [("cancel", "tap")]))

    def test_combo_replays_modifier(self):
        self.machine.feed(RALT_DOWN)
        suppress, actions = self.machine.feed(A_DOWN)
        self.assertTrue(suppress)
        self.assertEqual(actions, [("cancel", "combo"), ("inject", [RALT_DOWN, A_DOWN])])
        self.assertEqual(self.machine.feed(RALT_DOWN), (False, []))      # repeats pass through
        self.assertEqual(self.machine.feed(RALT_UP), (False, []))        # release reaches the app
        self.assertEqual(self.machine.feed(RALT_DOWN), (True, [("start",)]))

    def test_non_modifier_combo_passes_key(self):
        machine = HoldMachine(HOTKEYS["caps_lock"], self.clock)
        caps = Key(hotkey.VK_CAPITAL, 0x3A, False, True)
        machine.feed(caps)
        self.assertEqual(machine.feed(A_DOWN), (False, [("cancel", "combo")]))
        self.clock.now += 1
        self.assertEqual(machine.feed(caps._replace(down=False)), (True, []))

    def test_other_keys_pass_when_idle(self):
        self.assertEqual(self.machine.feed(A_DOWN), (False, []))
        self.assertEqual(self.machine.feed(RALT_UP), (False, []))        # stray release


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.settings = Settings(self.folder.name)
        self.builtin = Microphone("{a}", "마이크(Realtek)")
        self.usb = Microphone("{b}", "USB 마이크")

    def tearDown(self):
        self.folder.cleanup()

    def test_default_follows_system(self):
        selection = MicrophoneSelection(self.settings)
        selection.update(InputDevices((self.builtin, self.usb), "{b}"))
        self.assertEqual(selection.active, self.usb)
        self.assertEqual(selection.default_title, "시스템 기본값 (현재: USB 마이크)")

    def test_pinned_device_is_saved_and_lost_once(self):
        selection = MicrophoneSelection(self.settings)
        selection.update(InputDevices((self.builtin, self.usb), "{a}"))
        selection.select(self.usb)
        reloaded = MicrophoneSelection(Settings(self.folder.name))
        reloaded.update(InputDevices((self.builtin, self.usb), "{a}"))
        self.assertEqual(reloaded.active, self.usb)
        # Unplugged: fall back to the default and forget the pin.
        self.assertEqual(reloaded.update(InputDevices((self.builtin,), "{a}")), "USB 마이크")
        self.assertEqual(reloaded.active, self.builtin)
        self.assertIsNone(reloaded.update(InputDevices((self.builtin, self.usb), "{a}")))
        self.assertEqual(reloaded.active, self.builtin)
        self.assertIsNone(Settings(self.folder.name).get("microphone_id"))

    def test_no_devices(self):
        selection = MicrophoneSelection(self.settings)
        selection.update(InputDevices((), None))
        self.assertIsNone(selection.active)
        self.assertEqual(selection.default_title, "시스템 기본값 (현재: 없음)")


class AudioTests(unittest.TestCase):
    def test_error_messages(self):
        self.assertIn("개인 정보", audio.explain(RuntimeError("Error 0x80070005")))
        self.assertEqual(audio.explain(RuntimeError("Error 0x88890004")),
                         "마이크 연결이 끊겼습니다. [Error 0x88890004 (RuntimeError)]")
        # Shure MV7+ via SoundCard raised a bare AssertionError: never show an empty message.
        self.assertEqual(audio.explain(AssertionError()), "마이크 오류: AssertionError")
        self.assertIn("개인 정보", audio.explain(OSError("Unanticipated host error [Windows WASAPI error -2147024891]")))

    def test_portaudio_matching(self):
        mic = Microphone("{x}", "마이크(2- Shure MV7+)")
        inputs = [(3, dict(name="스피커 루프백")), (18, dict(name="마이크(2- Shure MV7+)")),
                  (19, dict(name="마이크(2- Shure MV7+)"))]
        self.assertEqual(audio.match_portaudio(mic, inputs)[0], 18)
        self.assertEqual(audio.match_portaudio(mic, inputs, same_name_rank=1)[0], 19)
        self.assertEqual(audio.match_portaudio(mic, inputs, same_name_rank=5)[0], 19)
        mme = [(1, dict(name="마이크(2- Shure MV7"))]          # MME truncates long names
        self.assertEqual(audio.match_portaudio(mic, mme)[0], 1)
        self.assertIsNone(audio.match_portaudio(Microphone("{y}", "USB Mic"), inputs))

    def test_capture_resamples_device_rate_to_16k(self):
        capture = audio.Capture(Microphone("{x}", "t"), test=False)
        capture.rate = 48000
        capture._chunks = [np.ones(4800, np.float32) * 0.5, np.ones(4800, np.float32) * 0.5]
        samples, _ = capture.stop()
        self.assertEqual(len(samples), 3200)
        self.assertAlmostEqual(float(samples.mean()), 0.5, places=5)

    def test_watcher_reports_changes_only(self):
        snapshots = iter([InputDevices(), InputDevices(), InputDevices((Microphone("x", "X"),), "x")])
        seen = []
        watcher = audio.DeviceWatcher(seen.append, interval=0, lister=lambda: next(snapshots))
        for _ in range(3):
            snapshot = watcher.lister()
            if snapshot != watcher.last:
                watcher.last = snapshot
                watcher.changed(snapshot)
        self.assertEqual(len(seen), 2)


class ClipboardTests(unittest.TestCase):
    def test_round_trip_and_newer_copy_kept(self):
        original = paste.read_text()
        try:
            paste.write_text("원래 클립보드 🙂")
            transaction = paste.PasteTransaction("받아쓴 문장.")
            self.assertEqual(paste.read_text(), "받아쓴 문장.")
            self.assertTrue(transaction.restore())
            self.assertEqual(paste.read_text(), "원래 클립보드 🙂")

            transaction = paste.PasteTransaction("두 번째.")
            paste.write_text("사용자가 새로 복사")
            self.assertFalse(transaction.restore())
            self.assertEqual(paste.read_text(), "사용자가 새로 복사")
        finally:
            if original is not None:
                paste.write_text(original)

    def test_unreadable_format_is_skipped_and_paste_continues(self):
        # A delayed-rendering format whose owner never renders it reads as NULL,
        # like data promised by an app that has quit.
        promised = paste.user32.RegisterClipboardFormatW("murdic-test-promised")
        with paste._Open():
            paste.user32.EmptyClipboard()
            paste._set(paste.CF_UNICODETEXT, "남겨 둘 텍스트\0".encode("utf-16-le"))
            paste.user32.SetClipboardData(promised, None)
        transaction = paste.PasteTransaction("받아쓴 문장.")
        self.assertEqual(paste.read_text(), "받아쓴 문장.")
        self.assertNotIn(promised, [fmt for fmt, _ in transaction.saved])
        self.assertTrue(transaction.restore())
        self.assertEqual(paste.read_text(), "남겨 둘 텍스트")

    def test_empty_clipboard_restores_empty(self):
        with paste._Open():
            paste.user32.EmptyClipboard()
        transaction = paste.PasteTransaction("임시")
        self.assertTrue(transaction.restore())
        self.assertIsNone(paste.read_text())


if __name__ == "__main__":
    unittest.main()
