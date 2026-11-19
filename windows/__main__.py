r"""Run from the checkout with: .venv\Scripts\python.exe -m windows"""
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

if sys.platform != "win32":
    raise SystemExit("This desktop entry point requires Windows.")

import pystray
from PIL import Image, ImageDraw
import win32api
import win32event
import win32gui
import win32process

from dictate.backend import CONFIG_DIR, Pipeline
from .audio import Capture, MAX_SECONDS, inputs, resolve_device
from .paste import PasteTransaction, key_down, modifiers_down, post_paste
from .settings import HOTKEYS, load, save


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("murdic · Windows")
        self.root.geometry("580x490")
        self.root.minsize(500, 440)
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)
        self.root.report_callback_exception = self.callback_error
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / "hints.txt").touch(exist_ok=True)
        self.settings = load(CONFIG_DIR)
        self.events = queue.Queue()
        self.state = "failed"
        self.pipeline = None
        self.capture = None
        self.transaction = None
        self.target = None
        self.held = False
        self.closed = False
        self.started = 0
        self.hotkey = tk.StringVar(value=self.settings.get("hotkey", "오른쪽 Ctrl"))
        self.status = tk.StringVar(value="모델 준비 중…")
        self.microphone = tk.StringVar()
        self.meter = tk.DoubleVar(value=0)
        self.build_ui()
        self.tray = pystray.Icon("murdic", self.icon("#355e99"), "murdic", menu=pystray.Menu(
            pystray.MenuItem("설정 / 결과 보기", lambda: self.events.put(("show", None)), default=True),
            pystray.MenuItem("종료", lambda: self.events.put(("quit", None))),
        ))
        self.tray.run_detached()
        self.refresh_devices()
        self.restart()
        self.root.after(20, self.tick)

    @staticmethod
    def icon(color):
        image = Image.new("RGBA", (64, 64))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((18, 6, 46, 43), radius=14, fill=color)
        draw.arc((10, 20, 54, 53), 0, 180, fill=color, width=5)
        draw.line((32, 51, 32, 60), fill=color, width=5)
        draw.line((23, 60, 41, 60), fill=color, width=5)
        return image

    def build_ui(self):
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="머딕 · Windows", font=("맑은 고딕", 17, "bold")).pack(anchor="w")
        ttk.Label(frame, textvariable=self.status, wraplength=530).pack(anchor="w", pady=(10, 12))
        ttk.Label(frame, text="마이크").pack(anchor="w")
        self.devices = ttk.Combobox(frame, textvariable=self.microphone, state="readonly")
        self.devices.pack(fill="x", pady=4)
        self.devices.bind("<<ComboboxSelected>>", self.choose_device)
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text="3초 마이크 테스트", command=self.test_microphone).pack(side="left")
        ttk.Button(row, text="마이크 권한", command=lambda: os.startfile(
            "ms-settings:privacy-microphone")).pack(side="left", padx=6)
        ttk.Progressbar(frame, variable=self.meter, maximum=100).pack(fill="x", pady=4)
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="누르고 말할 키").pack(side="left", padx=(0, 10))
        keys = ttk.Combobox(row, textvariable=self.hotkey, values=list(HOTKEYS),
                            state="readonly", width=15)
        keys.pack(side="left")
        keys.bind("<<ComboboxSelected>>", self.choose_key)
        ttk.Label(frame, text="입력할 앱에서 키를 누르고 말한 뒤 떼세요. Esc로 녹음을 취소합니다.",
                  wraplength=530).pack(anchor="w", pady=4)
        ttk.Label(frame, text="최근 결과 · 자동 입력이 취소되면 여기서 선택해 복사하세요.",
                  wraplength=530).pack(anchor="w", pady=(8, 4))
        self.result = tk.Text(frame, height=4, wrap="word", font=("맑은 고딕", 11))
        self.result.pack(fill="both", expand=True)
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(12, 0))
        ttk.Button(row, text="힌트 / 설정 폴더", command=lambda: os.startfile(str(CONFIG_DIR))).pack(side="left")
        ttk.Button(row, text="엔진 다시 시작", command=self.restart).pack(side="left", padx=6)
        ttk.Button(row, text="종료", command=self.quit).pack(side="right", padx=(6, 0))
        ttk.Button(row, text="트레이로 숨기기", command=self.root.withdraw).pack(side="right")

    def set_status(self, message):
        self.status.set(message)
        if hasattr(self, "tray"):
            self.tray.title = ("murdic · " + message)[:127]

    def ready(self, message=None):
        self.state = "ready" if self.pipeline else "failed"
        self.target = None
        self.meter.set(0)
        self.tray.icon = self.icon("#355e99")
        self.set_status(message or f"준비 완료 · {self.hotkey.get()}을 누르고 말하세요.")

    def refresh_devices(self):
        self.device_list = [(None, None)] + inputs()
        labels = ["시스템 기본 마이크"] + [f'{d["name"]} ({d["hostapi"]})'
                                      for _, d in self.device_list[1:]]
        self.devices["values"] = labels
        selected = next((i for i, (_, identity) in enumerate(self.device_list)
                         if identity == self.settings.get("microphone")), 0)
        self.devices.current(selected)
        if not selected and self.settings.get("microphone"):
            self.settings["microphone"] = None
            save(CONFIG_DIR, self.settings)

    def choose_device(self, event=None):
        if self.capture:
            self.cancel("마이크 변경으로 녹음을 취소했습니다.")
        self.settings["microphone"] = self.device_list[self.devices.current()][1]
        save(CONFIG_DIR, self.settings)

    def choose_key(self, event=None):
        if self.capture:
            self.cancel("단축키 변경으로 녹음을 취소했습니다.")
        self.settings["hotkey"] = self.hotkey.get()
        self.held = key_down(HOTKEYS[self.hotkey.get()])
        save(CONFIG_DIR, self.settings)
        if self.state == "ready":
            self.ready()

    def work(self, kind, function):
        def run():
            try:
                self.events.put((kind, function()))
            except Exception as error:
                self.events.put(("error", str(error)))
        threading.Thread(target=run, daemon=True).start()

    def restart(self):
        if self.state not in ("ready", "failed"):
            return
        if self.transaction:
            self.restore_clipboard()
            if self.transaction:
                return
        self.state = "loading"
        self.pipeline = None
        self.set_status("음성인식 모델 준비 중… 처음에는 모델을 다운로드합니다.")
        self.work("loaded", Pipeline)

    def start_capture(self, testing=False):
        if self.state != "ready":
            return
        try:
            if not testing:
                target = win32gui.GetForegroundWindow()
                if not target or win32process.GetWindowThreadProcessId(target)[1] == os.getpid():
                    self.set_status("메모장 등 입력할 앱을 선택한 뒤 단축키를 누르세요.")
                    return
                self.target = target
            capture = Capture(resolve_device(self.settings.get("microphone")))
            capture.start()
            self.capture = capture
            self.started = time.monotonic()
            self.state = "testing" if testing else "recording"
            self.tray.icon = self.icon("#d43e43")
            self.set_status(("3초 마이크 테스트 · " if testing else "녹음 중 · ") + capture.name)
        except Exception as error:
            self.ready("마이크를 열 수 없습니다: " + str(error))

    def test_microphone(self):
        self.start_capture(testing=True)

    def cancel(self, message):
        capture, self.capture = self.capture, None
        if capture:
            try:
                capture.stop(discard=True)
            except Exception as error:
                message += " · " + str(error)
        self.ready(message)

    def finish(self):
        capture, self.capture = self.capture, None
        if capture is None:
            return
        testing = self.state == "testing"
        try:
            audio = capture.stop(discard=testing)
            if testing or capture.peak < 10 ** (-65 / 20):
                self.ready(("입력 소리가 없었습니다 · " if capture.peak < 10 ** (-65 / 20)
                            else "마이크 입력 확인 · ") + capture.name)
                return
            self.state = "processing"
            self.tray.icon = self.icon("#ba821c")
            self.set_status("한국어를 정리하는 중…")
            self.work("result", lambda: self.pipeline.run_audio(audio))
        except Exception as error:
            self.ready("녹음 처리 오류: " + str(error))

    def receive_result(self, result):
        text = result["text"]
        self.result.delete("1.0", "end")
        self.result.insert("1.0", text)
        if not text:
            self.ready("인식된 말이 없습니다. 마이크를 확인하고 다시 말하세요.")
            return
        if not self.target or win32gui.GetForegroundWindow() != self.target:
            self.ready("입력 대상이 바뀌었습니다. 트레이의 결과 창에서 복사하세요.")
            return
        self.state = "pasting"
        self.paste_deadline = time.monotonic() + 1
        self.try_paste(text)

    def try_paste(self, text):
        if self.closed:
            return
        if modifiers_down() and time.monotonic() < self.paste_deadline:
            self.root.after(25, lambda: self.try_paste(text))
            return
        try:
            if not self.target or win32gui.GetForegroundWindow() != self.target:
                raise RuntimeError("입력 대상이 바뀌었습니다. 결과 창에서 복사하세요.")
            if modifiers_down():
                raise RuntimeError("보조 키가 눌려 있습니다. 결과 창에서 복사하세요.")
            self.transaction = PasteTransaction(self.root.winfo_id(), text)
            post_paste(self.target)
            self.root.after(450, self.restore_clipboard)
        except Exception as error:
            self.restore_clipboard(message=str(error))

    def restore_clipboard(self, attempt=0, message=None):
        try:
            if self.transaction:
                self.transaction.restore()
                self.transaction = None
            self.ready(message or "입력 전송 완료 · 다음 문장을 말하세요.")
        except Exception as error:
            if attempt < 4 and not self.closed:
                self.root.after(150, lambda: self.restore_clipboard(attempt + 1, message))
            else:
                self.state = "failed"
                self.set_status("클립보드 복원 실패. 종료 전에 다시 시도하세요: " + str(error))

    def tick(self):
        if self.closed:
            return
        try:
            self.poll()
        except Exception as error:
            if self.capture:
                self.cancel("오류: " + str(error))
            else:
                self.set_status("오류: " + str(error))
        finally:
            if not self.closed:
                self.root.after(20, self.tick)

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "loaded":
                    self.pipeline = value
                    self.ready()
                elif kind == "result":
                    self.receive_result(value)
                elif kind == "error":
                    self.ready("오류: " + value + " · 엔진 다시 시작을 눌러 재시도하세요.")
                elif kind == "show":
                    self.root.deiconify()
                    self.root.lift()
                elif kind == "quit":
                    self.quit()
                    if self.closed:
                        return
        except queue.Empty:
            pass
        if self.target and win32gui.GetForegroundWindow() != self.target:
            self.target = None
            if self.state == "recording":
                self.cancel("입력 대상이 바뀌어 녹음을 취소했습니다.")
        if self.capture:
            self.meter.set(min(100, self.capture.level * 500))
            if self.capture.error or not self.capture.stream.active:
                self.cancel(self.capture.error or "마이크 연결이 끊겼습니다. 장치와 권한을 확인하세요.")
            elif key_down(0x1B):
                self.cancel("녹음을 취소했습니다.")
            elif self.state == "recording" and any(
                key_down(vk) for vk in range(0x08, 0xFF)
                if vk not in {HOTKEYS[self.hotkey.get()], 0x10, 0x11, 0x12,
                              0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
            ):
                self.cancel("다른 키가 눌려 녹음을 취소했습니다.")
            elif time.monotonic() - self.started >= (3 if self.state == "testing" else MAX_SECONDS):
                if self.state == "testing":
                    self.finish()
                else:
                    self.cancel("180초 제한으로 녹음을 취소했습니다. 문장을 나누어 말하세요.")
        down = key_down(HOTKEYS[self.hotkey.get()])
        if down != self.held:
            self.held = down
            if down:
                self.start_capture()
            elif self.state == "recording":
                self.finish()

    def callback_error(self, kind, error, traceback):
        self.set_status("오류: " + str(error))

    def quit(self):
        if self.capture:
            self.cancel("종료 중…")
        if self.transaction:
            try:
                self.transaction.restore()
            except Exception as error:
                self.set_status("클립보드 복원 후 종료할 수 있습니다. 다시 종료를 누르세요: " + str(error))
                self.root.deiconify()
                return
        self.closed = True
        self.tray.stop()
        self.root.destroy()


def main():
    mutex = win32event.CreateMutex(None, False, "Local\\murdic.Windows")
    if win32api.GetLastError() == 183:
        messagebox.showinfo("murdic", "이미 실행 중입니다. 트레이 아이콘에서 설정을 여세요.")
        win32api.CloseHandle(mutex)
        return
    try:
        root = tk.Tk()
        App(root)
        root.mainloop()
    finally:
        win32api.CloseHandle(mutex)


if __name__ == "__main__":
    main()
