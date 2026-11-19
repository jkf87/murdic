"""First-run window: download the Whisper model (required) and, on NVIDIA PCs, cuBLAS (optional)."""
import logging
import threading
import time
import tkinter as tk
from tkinter import ttk

from . import download
from .errors import describe

log = logging.getLogger("murdic.firstrun")
FONT = "Malgun Gothic"


class FirstRun:
    """Runs the steps in order and calls `done(gpu_installed)` on the UI thread.

    `app.post` schedules callables on the Tk thread; `app.quit` exits."""

    def __init__(self, app, model, gpu, done):
        self.app, self.done = app, done
        self.steps = ([("model", "받아쓰기 모델(Whisper small)을 내려받습니다 · 약 486 MB",
                        "처음 한 번만 받습니다. 이후에는 인터넷 없이 동작합니다.", download.download_model)]
                      if model else [])
        if gpu:
            self.steps.append(("gpu", "NVIDIA GPU 가속 파일(cuBLAS)을 내려받습니다 · 약 553 MB",
                               "건너뛰면 CPU로 전사합니다. 나중에 트레이 메뉴에서 받을 수 있습니다.",
                               download.download_cublas))
        self.gpu_installed = False
        self.cancel = threading.Event()
        self.window = tk.Toplevel(app.root)
        self.window.title("머딕 준비")
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.on_cancel)
        frame = ttk.Frame(self.window, padding=20)
        frame.pack(fill="both")
        self.title = ttk.Label(frame, font=(FONT, 11, "bold"), wraplength=420)
        self.title.pack(anchor="w")
        self.note = ttk.Label(frame, font=(FONT, 9), foreground="#5f6368", wraplength=420)
        self.note.pack(anchor="w", pady=(4, 12))
        self.bar = ttk.Progressbar(frame, length=420, maximum=1000)
        self.bar.pack(fill="x")
        self.detail = ttk.Label(frame, font=(FONT, 9))
        self.detail.pack(anchor="w", pady=(6, 12))
        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e")
        self.retry = ttk.Button(buttons, text="다시 시도", command=self.start_step)
        self.skip = ttk.Button(buttons, text="건너뛰기", command=self.on_skip)
        self.close = ttk.Button(buttons, text="취소", command=self.on_cancel)
        self.close.pack(side="right")
        self.index = 0
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - self.window.winfo_width()) // 2
        y = (self.window.winfo_screenheight() - self.window.winfo_height()) // 3
        self.window.geometry(f"+{x}+{y}")
        self.window.lift()
        self.window.focus_force()
        self.start_step()

    @property
    def step(self):
        return self.steps[self.index]

    def start_step(self):
        if self.index >= len(self.steps):
            self.finish()
            return
        key, title, note, function = self.step
        self.title.configure(text=title)
        self.note.configure(text=note)
        self.detail.configure(text="연결 중…", foreground="")
        self.bar.configure(value=0)
        self.retry.pack_forget()
        if key == "gpu":
            self.skip.pack(side="right", padx=(0, 8))
        self.cancel.clear()
        self.started = time.monotonic()
        threading.Thread(target=self._work, args=(function,), name="murdic-download", daemon=True).start()

    def _work(self, function):
        try:
            function(lambda done, total: self.app.post(self.progress, done, total), self.cancel)
            self.app.post(self.step_done)
        except download.Cancelled:
            pass
        except Exception as error:
            log.warning("Download failed: %s", describe(error), exc_info=True)
            self.app.post(self.failed, describe(error))

    def progress(self, done, total):
        self.bar.configure(value=done * 1000 // max(total, 1))
        elapsed = max(time.monotonic() - self.started, 0.1)
        self.detail.configure(text=f"{done * 100 // max(total, 1)}% · {done / 2**20:,.0f} / {total / 2**20:,.0f} MB"
                                   f" · {done / 2**20 / elapsed:,.1f} MB/s")
        self.app.set_status(f"{'모델' if self.step[0] == 'model' else 'GPU 파일'} 내려받는 중… "
                            f"{done * 100 // max(total, 1)}%")

    def step_done(self):
        if self.step[0] == "gpu":
            self.gpu_installed = True
        self.skip.pack_forget()
        self.index += 1
        self.start_step()

    def failed(self, message):
        self.detail.configure(text=message + " 인터넷 연결을 확인하세요.", foreground="#c5221f")
        self.retry.pack(side="right", padx=(0, 8))

    def on_skip(self):
        self.cancel.set()
        self.app.settings.update(gpu_download="skipped")
        self.skip.pack_forget()
        self.index += 1
        self.start_step()

    def on_cancel(self):
        self.cancel.set()
        if self.step[0] == "gpu":
            self.on_skip()
            return
        self.window.destroy()
        self.app.quit()

    def finish(self):
        self.window.destroy()
        self.done(self.gpu_installed)
