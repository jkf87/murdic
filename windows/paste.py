"""Guarded Windows paste; preserve clipboard formats and subsequent copies."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import time
import uuid

import win32clipboard as clipboard
import win32con
import win32gui


@contextmanager
def opened(owner):
    for attempt in range(20):
        try:
            clipboard.OpenClipboard(owner)
            break
        except Exception:
            if attempt == 19:
                raise RuntimeError("클립보드가 사용 중입니다. 다시 시도하세요.") from None
            time.sleep(0.01)
    try:
        yield
    finally:
        clipboard.CloseClipboard()


class PasteTransaction:
    def __init__(self, owner, text):
        self.owner = owner
        self.saved = []
        self.sequence = None
        self.marker_format = clipboard.RegisterClipboardFormat("murdic.clipboard.transaction")
        self.marker = uuid.uuid4().bytes
        self.text = text
        with opened(owner):
            fmt = clipboard.EnumClipboardFormats(0)
            while fmt:
                data = clipboard.GetClipboardData(fmt)
                # Handles (bitmap/metafile) and file-drop tuples cannot be safely
                # copied using this API. Fail BEFORE clearing any clipboard data.
                if not isinstance(data, (str, bytes)):
                    raise RuntimeError("이 클립보드 형식은 보관할 수 없습니다. 결과 창에서 직접 복사하세요.")
                self.saved.append((fmt, data))
                fmt = clipboard.EnumClipboardFormats(fmt)
            clipboard.EmptyClipboard()
            try:
                clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
                clipboard.SetClipboardData(self.marker_format, self.marker)
            except Exception:
                self._put_back()
                raise
            self.sequence = clipboard.GetClipboardSequenceNumber()

    def _put_back(self):
        clipboard.EmptyClipboard()
        for fmt, data in self.saved:
            clipboard.SetClipboardData(fmt, data)

    def restore(self):
        if self.sequence is None:
            return
        with opened(self.owner):
            # Windows may synthesize ANSI text/locale formats after a paste,
            # changing the sequence without a user copy. A private token plus
            # the exact text proves ownership even after that conversion.
            if (clipboard.IsClipboardFormatAvailable(self.marker_format)
                    and clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT)
                    and clipboard.GetClipboardData(self.marker_format) == self.marker
                    and clipboard.GetClipboardData(win32con.CF_UNICODETEXT) == self.text):
                self._put_back()
            self.sequence = None


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", INPUTUNION)]


user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def modifiers_down():
    return any(key_down(vk) for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C))


def post_paste(target):
    if not target or win32gui.GetForegroundWindow() != target or not win32gui.IsWindow(target):
        raise RuntimeError("입력 대상이 바뀌어 자동 입력을 취소했습니다. 결과 창에서 복사하세요.")
    if modifiers_down():
        raise RuntimeError("Ctrl·Shift·Alt·Windows 키를 뗀 뒤 결과 창에서 복사하세요.")
    events = (INPUT * 4)()
    for event, (vk, flags) in zip(events, [(0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)]):
        event.type = 1
        event.ki = KEYBDINPUT(wVk=vk, dwFlags=flags)
    sent = user32.SendInput(4, events, ctypes.sizeof(INPUT))
    if sent != 4:
        # Release only keys this batch might have pressed if a partial send occurs.
        if sent:
            releases = (INPUT * 2)()
            for event, vk in zip(releases, (0x56, 0x11)):
                event.type = 1
                event.ki = KEYBDINPUT(wVk=vk, dwFlags=2)
            user32.SendInput(2, releases, ctypes.sizeof(INPUT))
        raise RuntimeError("자동 입력을 전송하지 못했습니다. 관리자 권한 앱에는 직접 붙여넣으세요.")
