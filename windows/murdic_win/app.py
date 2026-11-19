"""Tray app controller: hotkey -> record -> transcribe -> paste (mirrors mac/App.swift).

Everything that touches state runs on the Tk main thread. The keyboard hook,
device watcher, capture, engine and tray post callables to `self.queue`.
"""
import ctypes
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor

from . import paste, paths
from .audio import Capture, DeviceWatcher, MicrophoneSelection
from .engine import QUIET_DB, Engine, Pipeline
from .hotkey import DEFAULT_HOTKEY, HOTKEYS, KeyboardHook
from .settings import Settings

log = logging.getLogger("murdic.app")
MAX_TAKE_SECONDS = 120
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def single_instance():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.CreateMutexW(None, False, "Local\\murdic-single-instance")
    return handle if ctypes.get_last_error() != 183 else None  # ERROR_ALREADY_EXISTS


def message_box(text):
    ctypes.windll.user32.MessageBoxW(None, text, "murdic", 0x40)


class App:
    def __init__(self, directory, device="auto"):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        hints = directory / "hints.txt"
        if not hints.exists():
            hints.write_text("", encoding="utf-8")
        self.settings = Settings(directory)
        self.device = device
        self.queue = queue.Queue()
        self.root = tk.Tk()
        self.root.withdraw()
        from .overlay import Overlay
        self.overlay = Overlay(self.root)
        self.selection = MicrophoneSelection(self.settings)
        name = self.settings.get("hotkey", DEFAULT_HOTKEY)
        self.hotkey_name = name if name in HOTKEYS else DEFAULT_HOTKEY
        self.state = "loading"
        self.status = "모델 준비 중…"
        self.pipeline = None
        self.engine_label = "준비 중"
        self.capture = None
        self.target = None
        self.transaction = None
        self.take_started = 0.0
        self.test_timer = None
        self.worker = ThreadPoolExecutor(1, thread_name_prefix="murdic-engine")
        self.hook = KeyboardHook(HOTKEYS[self.hotkey_name], lambda a, t: self.post(self.on_key, a, t))
        self.watcher = DeviceWatcher(lambda snapshot: self.post(self.devices_changed, snapshot))
        from .tray import Tray
        self.tray = Tray(self)

    # --- plumbing ---------------------------------------------------------
    def post(self, function, *args):
        self.queue.put((function, args))

    def _pump(self):
        try:
            while True:
                function, args = self.queue.get_nowait()
                try:
                    function(*args)
                except Exception:
                    log.exception("UI task failed")
                    self.overlay.hide()
                    if self.state in ("recording", "processing", "pasting"):
                        self.ready()
        except queue.Empty:
            pass
        if self.state == "recording":
            self._watch_take()
        self.root.after(15, self._pump)

    def run(self):
        self.hook.start()
        self.hook.ready.wait(5)
        if self.hook.error:
            message_box(f"전역 단축키를 설치할 수 없습니다: {self.hook.error}")
            return 1
        self.watcher.start()
        self.tray.start()
        self.load_engine()
        self.root.after(15, self._pump)
        self.root.mainloop()
        return 0

    def set_status(self, text, warning=False):
        self.status = text
        log.info("Status: %s", text)
        self.tray.refresh(warning)

    @property
    def hotkey(self):
        return HOTKEYS[self.hotkey_name]

    @property
    def can_test(self):
        return self.capture is None and self.state in ("ready", "failed") and self.selection.active is not None

    @property
    def can_restart(self):
        return self.state in ("ready", "failed")

    # --- engine -------------------------------------------------------------
    def load_engine(self):
        self.state = "loading"
        self.set_status("모델 준비 중…")

        def load():
            try:
                pipeline = Pipeline(self.directory, Engine(device=self.device))
                self.post(self.engine_loaded, pipeline)
            except Exception as error:
                log.exception("Engine failed")
                self.post(self.report, str(error))
        threading.Thread(target=load, name="murdic-load", daemon=True).start()

    def engine_loaded(self, pipeline):
        self.pipeline = pipeline
        self.engine_label = pipeline.engine.label
        log.info("Engine ready after %.0f ms since launch", (time.perf_counter() - STARTED) * 1000)
        self.ready()

    def restart_engine(self):
        if self.can_restart:
            self.pipeline = None
            self.load_engine()

    def ready(self, status=None):
        self.state = "ready"
        self.target = None
        self.set_status(status or f"{self.hotkey.title} 키를 누른 채 말하세요")

    def report(self, message):
        self.state = "failed"
        self.overlay.hide()
        self.set_status(message, warning=True)

    def notify(self, message):
        self.overlay.notice(message)
        self.set_status(message)

    # --- microphones --------------------------------------------------------
    def devices_changed(self, snapshot):
        previous = self.selection.active
        lost = self.selection.update(snapshot)
        moved = self.capture is not None and self.capture.microphone != self.selection.active
        if moved:
            self.cancel_take()
        if lost:
            self.notify(f"{lost} 연결 끊김 → " + ("사용할 마이크 없음" if self.selection.active is None
                                              else "기본 마이크 사용"))
        elif moved:
            self.notify(f"마이크 변경: {previous.name if previous else '없음'} → "
                        f"{self.selection.active.name if self.selection.active else '없음'}")
        else:
            self.tray.refresh(self.state == "failed")

    def select_microphone(self, mic):
        if mic is not None and mic not in self.selection.inputs.devices:
            return
        self.cancel_take()
        self.selection.select(mic)
        self.tray.refresh(self.state == "failed")

    def test_microphone(self):
        mic = self.selection.active
        if not self.can_test:
            return
        self.capture = Capture(mic, test=True, on_level=lambda db: self.post(self.overlay.update, db),
                               on_failure=lambda error: self.post(self.capture_failed, error)).start()
        self.overlay.show("마이크 테스트 중… 말해 보세요", microphone=mic.name)
        self.set_status("마이크 테스트 중…")
        self.test_timer = self.root.after(3000, self.finish_test)

    def finish_test(self):
        self.test_timer = None
        capture, self.capture = self.capture, None
        if capture is None or not capture.test:
            return
        try:
            _, db = capture.stop()
        except Exception as error:
            self.notify(str(error))
            return
        message = self.quiet_message(capture) if db < QUIET_DB else "입력 확인 · " + capture.microphone.name
        self.notify(message)
        if self.state == "ready":
            self.status = message

    def quiet_message(self, capture):
        return "입력 소리가 없었어요 — 마이크: " + capture.microphone.name

    def capture_failed(self, error):
        capture = self.capture
        if capture is None:
            return
        self.cancel_take()
        self.notify(f"{capture.microphone.name}: {error}")

    # --- hotkey flow --------------------------------------------------------
    def on_key(self, action, when):
        kind = action[0]
        if kind == "start":
            self.begin()
        elif kind == "finish":
            self.finish(when)
        elif kind == "cancel" and self.state == "recording":
            log.info("Take cancelled (%s)", action[1])
            self.cancel_take()

    def begin(self):
        if self.state == "loading":
            self.overlay.notice("모델 준비 중…")
            return
        if self.state != "ready":
            return
        if self.capture is not None:   # a microphone test is running
            self.cancel_take()
        mic = self.selection.active
        if mic is None:
            self.notify("연결된 입력 마이크가 없습니다.")
            return
        self.target = paste.foreground()
        self.capture = Capture(mic, on_level=lambda db: self.post(self.level, db),
                               on_failure=lambda error: self.post(self.capture_failed, error)).start()
        self.state = "recording"
        self.take_started = time.monotonic()
        self.overlay.show("녹음 중 · 키를 떼면 입력", microphone=mic.name)
        self.set_status("녹음 중")

    def level(self, db):
        if self.state == "recording":
            self.overlay.update(db)

    def _watch_take(self):
        if paste.foreground() != self.target:
            log.info("Focus moved during the take")
            self.cancel_take()
            self.notify("입력할 창이 바뀌어 녹음을 취소했습니다.")
        elif time.monotonic() - self.take_started > MAX_TAKE_SECONDS:
            self.cancel_take()
            self.notify("녹음이 2분을 넘어 취소했습니다.")

    def cancel_take(self):
        if self.test_timer:
            self.root.after_cancel(self.test_timer)
            self.test_timer = None
        capture, self.capture = self.capture, None
        if capture is not None:
            try:
                capture.stop()
            except Exception:
                pass
        self.overlay.hide()
        if self.state == "recording":
            self.ready()
        else:
            self.tray.refresh(self.state == "failed")

    def finish(self, released):
        if self.state != "recording":
            return
        capture, self.capture = self.capture, None
        self.state = "processing"
        self.overlay.show("전사 중…")
        self.set_status("전사 중…")
        try:
            audio, db = capture.stop()
        except Exception as error:
            self.ready()
            self.notify(f"{capture.microphone.name}: {error}")
            return
        if db < QUIET_DB:
            self.ready()
            self.notify(self.quiet_message(capture))
            return
        future = self.worker.submit(self.pipeline.run_audio, audio)
        future.add_done_callback(lambda done: self.post(self.transcribed, done, released))

    def transcribed(self, future, released):
        try:
            result = future.result()
        except Exception as error:
            log.exception("Transcription failed")
            self.report(f"전사 오류: {error}. 메뉴에서 엔진을 다시 시작하세요.")
            return
        log.info("Transcribed %.2f s in %.0f ms on %s (%s)", result["audio_s"], result["processing_ms"],
                 result["device"], result["route"])
        text = result["text"]
        if not text:
            self.overlay.hide()
            self.ready()
            return
        if paste.foreground() != self.target:
            self.overlay.hide()
            self.ready("입력할 창이 바뀌어 받아쓰기를 취소했습니다.")
            return
        paste.wait_for_modifiers()
        try:
            self.transaction = paste.PasteTransaction(text)
            paste.send_paste()
        except Exception as error:
            if self.transaction:
                self.transaction.restore()
                self.transaction = None
            self.overlay.hide()
            self.ready()
            self.notify(str(error))
            return
        elapsed = round((time.perf_counter() - released) * 1000)
        log.info("Ctrl+V sent %d ms after key release (%d chars)", elapsed, len(text))
        self.state = "pasting"
        self.overlay.hide()
        self.root.after(int(paste.RESTORE_DELAY * 1000), lambda: self.pasted(elapsed))

    def pasted(self, elapsed):
        if self.transaction:
            self.transaction.restore()
            self.transaction = None
        self.ready(f"최근 Ctrl+V 전송까지 {elapsed} ms")

    # --- menu -----------------------------------------------------------------
    def select_hotkey(self, name):
        if name not in HOTKEYS:
            return
        self.cancel_take()
        self.hotkey_name = name
        self.settings.update(hotkey=name)
        self.hook.set_hotkey(HOTKEYS[name])
        if self.state == "ready":
            self.ready()

    def open_config(self):
        os.startfile(self.directory)

    @property
    def autostart(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, "murdic")
                return True
        except OSError:
            return False

    def toggle_autostart(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if self.autostart:
                winreg.DeleteValue(key, "murdic")
            else:
                winreg.SetValueEx(key, "murdic", 0, winreg.REG_SZ, f'"{sys.executable}"')
        self.tray.refresh(self.state == "failed")

    def quit(self):
        self.cancel_take()
        if self.transaction:
            self.transaction.restore()
        self.hook.stop()
        self.watcher.stop()
        self.tray.stop()
        self.worker.shutdown(wait=False, cancel_futures=True)
        self.root.quit()


STARTED = time.perf_counter()


def run_app(directory, device="auto"):
    mutex = single_instance()
    if mutex is None:
        message_box("머딕이 이미 실행 중입니다. 작업 표시줄 오른쪽 알림 영역의 아이콘을 확인하세요.")
        return 0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    try:
        return App(directory, device).run()
    except Exception as error:
        log.exception("murdic failed to start")
        message_box(f"머딕을 시작할 수 없습니다: {error}")
        return 1
