"""Drive a Notepad window for measurements (benchmark and desktop end-to-end test)."""
import ctypes
import subprocess
import tempfile
import time
import uuid
from ctypes import wintypes
from pathlib import Path

from .hotkey import Key, send_keys

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32")
WM_GETTEXT, WM_GETTEXTLENGTH, WM_SETTEXT, WM_CLOSE = 0x0D, 0x0E, 0x0C, 0x10
SMTO_ABORTIFHUNG = 0x2
ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.SendMessageTimeoutW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                       wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t))
user32.SendMessageTimeoutW.restype = wintypes.LPARAM
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


def _title(hwnd):
    buffer = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buffer, 512)
    return buffer.value


def _class(hwnd):
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


class Notepad:
    """Opens a new empty temporary file in Notepad and reads its text with WM_GETTEXT."""

    def __init__(self, timeout=15):
        self.folder = tempfile.TemporaryDirectory()
        self.file = Path(self.folder.name) / f"murdic-{uuid.uuid4().hex[:8]}.txt"
        self.file.write_text("", encoding="utf-8")
        subprocess.Popen(["notepad.exe", str(self.file)])
        deadline = time.monotonic() + timeout
        self.hwnd = self.edit = None
        while time.monotonic() < deadline and not self.edit:
            time.sleep(0.2)
            self.hwnd = self._find_window()
            if self.hwnd:
                self.edit = self._find_edit()
        if not self.edit:
            raise RuntimeError("메모장 창을 찾지 못했습니다.")

    def _find_window(self):
        found = []

        def visit(hwnd, _):
            if user32.IsWindowVisible(hwnd) and self.file.stem in _title(hwnd):
                found.append(hwnd)
            return True
        user32.EnumWindows(ENUMPROC(visit), 0)
        return found[0] if found else None

    def _find_edit(self):
        found = []

        def visit(hwnd, _):
            if _class(hwnd) in ("RichEditD2DPT", "Edit") and user32.IsWindowVisible(hwnd):
                found.append(hwnd)
            return True
        user32.EnumChildWindows(self.hwnd, ENUMPROC(visit), 0)
        return found[0] if found else None

    def text(self):
        result = ctypes.c_size_t()
        user32.SendMessageTimeoutW(self.edit, WM_GETTEXTLENGTH, 0, 0, SMTO_ABORTIFHUNG, 1000, ctypes.byref(result))
        buffer = ctypes.create_unicode_buffer(result.value + 1)
        user32.SendMessageTimeoutW(self.edit, WM_GETTEXT, result.value + 1, ctypes.addressof(buffer),
                                   SMTO_ABORTIFHUNG, 1000, ctypes.byref(result))
        return buffer.value.replace("\r", "")

    def clear(self):
        empty = ctypes.create_unicode_buffer("")
        result = ctypes.c_size_t()
        user32.SendMessageTimeoutW(self.edit, WM_SETTEXT, 0, ctypes.addressof(empty), SMTO_ABORTIFHUNG, 1000,
                                   ctypes.byref(result))

    def focus(self):
        """Bring Notepad to the front (attach to the foreground thread to pass the foreground lock)."""
        for _ in range(10):
            if user32.GetForegroundWindow() == self.hwnd:
                return True
            current = user32.GetForegroundWindow()
            mine = kernel32.GetCurrentThreadId()
            theirs = user32.GetWindowThreadProcessId(current, None) if current else 0
            if theirs and theirs != mine:
                user32.AttachThreadInput(mine, theirs, True)
            user32.ShowWindow(self.hwnd, 9)  # SW_RESTORE
            user32.BringWindowToTop(self.hwnd)
            user32.SetForegroundWindow(self.hwnd)
            if theirs and theirs != mine:
                user32.AttachThreadInput(mine, theirs, False)
            time.sleep(0.15)
        return user32.GetForegroundWindow() == self.hwnd

    def is_front(self):
        return user32.GetForegroundWindow() == self.hwnd

    def wait_for(self, expected, start, timeout=3.0):
        """Poll until the text equals `expected`; return ms since `start` (perf_counter) or None."""
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if self.text().strip() == expected:
                return round((time.perf_counter() - start) * 1000)
            time.sleep(0.005)
        return None

    def close(self):
        if self.is_front():   # save the temp file so Notepad closes without asking
            ctrl = user32.MapVirtualKeyW(0x11, 0)
            s = user32.MapVirtualKeyW(0x53, 0)
            send_keys([Key(0x11, ctrl, False, True), Key(0x53, s, False, True),
                       Key(0x53, s, False, False), Key(0x11, ctrl, False, False)])
            time.sleep(0.5)
        user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        time.sleep(0.5)
        try:
            self.folder.cleanup()
        except OSError:
            pass
