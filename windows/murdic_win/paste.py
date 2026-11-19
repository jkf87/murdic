"""Clipboard transaction + Ctrl+V, the Windows counterpart of mac/Paste.swift.

All clipboard formats that live in global memory are kept and restored after
the paste (GDI handle formats such as CF_BITMAP are re-synthesised by Windows
from CF_DIB). The dictated text is marked so it stays out of clipboard history
(Win+V) and cloud clipboard. If something new is copied before the restore,
the restore is skipped so the newer copy survives.
"""
import ctypes
import logging
import time
from ctypes import wintypes

from .hotkey import Key, send_keys

log = logging.getLogger("murdic.paste")
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
GHND = 0x0042
HANDLE_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}  # bitmap, metafile, palette, owner-display...
RESTORE_DELAY = 0.45  # seconds after Ctrl+V, as on macOS
VK_CONTROL, VK_V, VK_SHIFT, VK_MENU, VK_LWIN, VK_RWIN = 0x11, 0x56, 0x10, 0x12, 0x5B, 0x5C

for name, args, res in [
    ("OpenClipboard", (wintypes.HWND,), wintypes.BOOL),
    ("CloseClipboard", (), wintypes.BOOL),
    ("EmptyClipboard", (), wintypes.BOOL),
    ("EnumClipboardFormats", (wintypes.UINT,), wintypes.UINT),
    ("GetClipboardData", (wintypes.UINT,), wintypes.HANDLE),
    ("SetClipboardData", (wintypes.UINT, wintypes.HANDLE), wintypes.HANDLE),
    ("RegisterClipboardFormatW", (wintypes.LPCWSTR,), wintypes.UINT),
    ("GetClipboardSequenceNumber", (), wintypes.DWORD),
    ("GetForegroundWindow", (), wintypes.HWND),
    ("GetAsyncKeyState", (ctypes.c_int,), ctypes.c_short),
    ("MapVirtualKeyW", (wintypes.UINT, wintypes.UINT), wintypes.UINT),
    ("CreateWindowExW", (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                         ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                         wintypes.HINSTANCE, wintypes.LPVOID), wintypes.HWND),
]:
    function = getattr(user32, name)
    function.argtypes, function.restype = args, res
for name, args, res in [
    ("GlobalAlloc", (wintypes.UINT, ctypes.c_size_t), wintypes.HGLOBAL),
    ("GlobalLock", (wintypes.HGLOBAL,), wintypes.LPVOID),
    ("GlobalUnlock", (wintypes.HGLOBAL,), wintypes.BOOL),
    ("GlobalSize", (wintypes.HGLOBAL,), ctypes.c_size_t),
    ("GlobalFree", (wintypes.HGLOBAL,), wintypes.HGLOBAL),
]:
    function = getattr(kernel32, name)
    function.argtypes, function.restype = args, res


class PasteError(RuntimeError):
    pass


_owner = None


def owner_window():
    """A message-only window: SetClipboardData fails when the clipboard has no owner."""
    global _owner
    if _owner is None:
        _owner = user32.CreateWindowExW(0, "STATIC", "murdic-clipboard", 0, 0, 0, 0, 0,
                                        wintypes.HWND(-3), None, None, None)  # HWND_MESSAGE
    return _owner


class _Open:
    def __enter__(self):
        for _ in range(25):   # another app may hold the clipboard briefly
            if user32.OpenClipboard(owner_window()):
                return self
            time.sleep(0.02)
        raise PasteError("클립보드를 열 수 없어 입력을 중단했습니다.")

    def __exit__(self, *exc):
        user32.CloseClipboard()


def _private_formats():
    names = ("ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory",
             "CanUploadToCloudClipboard")
    return [user32.RegisterClipboardFormatW(name) for name in names]


def _set(fmt, data):
    handle = kernel32.GlobalAlloc(GHND, max(1, len(data)))
    if not handle:
        return False
    pointer = kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not user32.SetClipboardData(fmt, handle):
        kernel32.GlobalFree(handle)
        return False
    return True


def _mark_private():
    exclude, history, cloud = _private_formats()
    _set(exclude, b"")
    _set(history, (0).to_bytes(4, "little"))
    _set(cloud, (0).to_bytes(4, "little"))


def _read_format(fmt):
    handle = user32.GetClipboardData(fmt)
    if not handle:
        return None   # delayed rendering failed (source app quit, ...)
    size = kernel32.GlobalSize(handle)
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return None
    try:
        return ctypes.string_at(pointer, size)
    finally:
        kernel32.GlobalUnlock(handle)


def snapshot():
    """Copy every readable global-memory clipboard format. Call with the clipboard open.

    Best effort, as in mac/Paste.swift: formats that cannot be read are skipped
    and dictation continues; whatever was readable is restored after the paste."""
    private = set(_private_formats())
    saved, fmt, skipped = [], 0, 0
    while True:
        fmt = user32.EnumClipboardFormats(fmt)
        if not fmt:
            break
        if fmt in HANDLE_FORMATS or 0x300 <= fmt <= 0x3FF or fmt in private:
            continue
        try:
            data = _read_format(fmt)
        except Exception:   # never let one odd format stop dictation
            data = None
        if data is None:
            skipped += 1
        else:
            saved.append((fmt, data))
    if skipped:
        log.info("Clipboard: skipped %d unreadable format(s), kept %d", skipped, len(saved))
    return saved


def read_text():
    with _Open():
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)


def write_text(text, private=False):
    with _Open():
        user32.EmptyClipboard()
        if not _set(CF_UNICODETEXT, (text + "\0").encode("utf-16-le")):
            raise PasteError("텍스트를 클립보드에 넣을 수 없습니다.")
        if private:
            _mark_private()


class PasteTransaction:
    def __init__(self, text):
        with _Open():
            try:
                self.saved = snapshot()
            except Exception:
                log.exception("Clipboard could not be saved; pasting without restore data")
                self.saved = []
            user32.EmptyClipboard()
            if not _set(CF_UNICODETEXT, (text + "\0").encode("utf-16-le")):
                self._restore_open()
                raise PasteError("텍스트를 클립보드에 넣을 수 없습니다.")
            _mark_private()
        self.sequence = user32.GetClipboardSequenceNumber()

    def _restore_open(self):
        user32.EmptyClipboard()
        for fmt, data in self.saved:
            _set(fmt, data)
        if self.saved:
            _mark_private()   # the original is already in history; do not add it twice

    def restore(self):
        """Put the previous contents back unless something else was copied meanwhile."""
        if user32.GetClipboardSequenceNumber() != self.sequence:
            log.info("Clipboard changed after paste; keeping the newer copy")
            return False
        with _Open():
            self._restore_open()
        return True


def wait_for_modifiers(timeout=0.5):
    """Avoid turning Ctrl+V into Ctrl+Shift+V while the user still holds Shift/Alt/Win."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (VK_SHIFT, VK_MENU, VK_LWIN, VK_RWIN)):
            return
        time.sleep(0.01)


def send_paste():
    ctrl = user32.MapVirtualKeyW(VK_CONTROL, 0)
    v = user32.MapVirtualKeyW(VK_V, 0)
    send_keys([Key(VK_CONTROL, ctrl, False, True), Key(VK_V, v, False, True),
               Key(VK_V, v, False, False), Key(VK_CONTROL, ctrl, False, False)])


def foreground():
    return user32.GetForegroundWindow()
