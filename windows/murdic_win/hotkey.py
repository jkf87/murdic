"""Hold-to-talk hotkey: a pure state machine plus a WH_KEYBOARD_LL hook.

The hotkey's own events are swallowed so the focused app never sees them
(a bare Alt press would otherwise move focus to the menu bar and break Ctrl+V).

Korean keyboards: with the common "type 1" driver the physical right Alt sends
VK_HANGUL (한/영) and right Ctrl sends VK_HANJA. "오른쪽 Alt" therefore matches
both VK_RMENU and VK_HANGUL from the right-Alt position (scan code 0x38), but
not a dedicated 한/영 key (scan 0x72/0xF2). To keep language switching usable,
a short tap (< TAP_SECONDS) cancels the take and replays 한/영 (or 한자,
Caps Lock, Scroll Lock) so the key keeps its normal function; only holding it
records. A bare Alt/Ctrl tap is not replayed (an Alt tap would open menus).
Pressing any other key while holding cancels the take; for Alt/Ctrl the
modifier is replayed first so shortcuts such as AltGr or RCtrl+C still work.
"""
import ctypes
import logging
import os
import threading
import time
from ctypes import wintypes
from typing import NamedTuple, Optional, Tuple

log = logging.getLogger("murdic.hotkey")

VK_CAPITAL, VK_SCROLL = 0x14, 0x91
VK_HANGUL, VK_HANJA = 0x15, 0x19
VK_RCONTROL, VK_RMENU = 0xA3, 0xA5
SCAN_ALT, SCAN_CTRL = 0x38, 0x1D
TAP_SECONDS = 0.30
MAGIC = 0x6D757264  # "murd": dwExtraInfo of events murdic injects itself


class Hotkey(NamedTuple):
    key: str
    title: str
    matches: Tuple[Tuple[int, Optional[int]], ...]  # (vk, scan or None for any)
    modifier: bool

    def match(self, vk, scan):
        return any(vk == v and (s is None or scan == s) for v, s in self.matches)


HOTKEYS = {
    "right_alt": Hotkey("right_alt", "오른쪽 Alt", ((VK_RMENU, None), (VK_HANGUL, SCAN_ALT)), True),
    "right_ctrl": Hotkey("right_ctrl", "오른쪽 Ctrl", ((VK_RCONTROL, None), (VK_HANJA, SCAN_CTRL)), True),
    "caps_lock": Hotkey("caps_lock", "Caps Lock", ((VK_CAPITAL, None),), False),
    "scroll_lock": Hotkey("scroll_lock", "Scroll Lock", ((VK_SCROLL, None),), False),
}
DEFAULT_HOTKEY = "right_alt"


class Key(NamedTuple):
    vk: int
    scan: int
    extended: bool
    down: bool


class HoldMachine:
    """Feeds raw key events; returns (suppress, actions).

    Actions: ("start",), ("finish",), ("cancel", reason) and ("inject", [Key, ...])."""

    def __init__(self, hotkey, clock=time.monotonic):
        self.hotkey, self.clock = hotkey, clock
        self.state = "idle"        # idle | held | passthrough | swallow
        self.pressed = None        # the Key that started the hold
        self.since = 0.0

    def reset(self):
        self.state, self.pressed = "idle", None

    def feed(self, key):
        if self.hotkey.match(key.vk, key.scan):
            return self._hotkey(key)
        if key.down and self.state == "held":
            if self.hotkey.modifier:
                self.state = "passthrough"
                replay = self.pressed._replace(down=True)
                return True, [("cancel", "combo"), ("inject", [replay, key])]
            self.state = "swallow"
            return False, [("cancel", "combo")]
        return False, []

    def _hotkey(self, key):
        if key.down:
            if self.state == "idle":
                self.state, self.pressed, self.since = "held", key, self.clock()
                return True, [("start",)]
            return self.state != "passthrough", []   # auto-repeat
        state, self.state = self.state, "idle"
        if state == "held":
            if self.clock() - self.since < TAP_SECONDS:
                actions = [("cancel", "tap")]
                if self.pressed.vk not in (VK_RMENU, VK_RCONTROL):
                    actions.append(("inject", [self.pressed._replace(down=True), self.pressed._replace(down=False)]))
                return True, actions
            return True, [("finish",)]
        return state == "swallow", []   # passthrough/idle: let the release through


# --- Win32 -------------------------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_QUIT = 0x100, 0x101, 0x104, 0x105, 0x12
LLKHF_EXTENDED, LLKHF_INJECTED = 0x01, 0x10
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x1, 0x2
ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def send_keys(keys):
    """Inject key events tagged with MAGIC so murdic's own hook ignores them."""
    events = (INPUT * len(keys))()
    for event, key in zip(events, keys):
        event.type = INPUT_KEYBOARD
        flags = (KEYEVENTF_EXTENDEDKEY if key.extended else 0) | (0 if key.down else KEYEVENTF_KEYUP)
        event.u.ki = KEYBDINPUT(key.vk, key.scan, flags, 0, MAGIC)
    sent = user32.SendInput(len(keys), events, ctypes.sizeof(INPUT))
    if sent != len(keys):
        raise OSError(ctypes.get_last_error(), "SendInput was blocked")


class KeyboardHook(threading.Thread):
    """Runs the low-level hook on its own message loop.

    `on_action(action, timestamp)` must return quickly; the app queues it."""

    def __init__(self, hotkey, on_action):
        super().__init__(name="murdic-hotkey", daemon=True)
        self.machine = HoldMachine(hotkey)
        self.on_action = on_action
        # For automated end-to-end tests that drive the hotkey with SendInput.
        self.accept_injected = os.environ.get("MURDIC_ACCEPT_INJECTED") == "1"
        self._proc = HOOKPROC(self._callback)
        self._thread_id = None
        self.ready = threading.Event()
        self.error = None

    def set_hotkey(self, hotkey):
        self.machine = HoldMachine(hotkey)

    def _callback(self, code, wparam, lparam):
        if code == 0:
            try:
                info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                injected = bool(info.flags & LLKHF_INJECTED)
                if not injected or (self.accept_injected and info.dwExtraInfo != MAGIC):
                    key = Key(info.vkCode, info.scanCode, bool(info.flags & LLKHF_EXTENDED),
                              wparam in (WM_KEYDOWN, WM_SYSKEYDOWN))
                    suppress, actions = self.machine.feed(key)
                    now = time.perf_counter()
                    for action in actions:
                        if action[0] == "inject":
                            send_keys(action[1])
                        else:
                            self.on_action(action, now)
                    if suppress:
                        return 1
            except Exception:  # never let an exception escape into user32
                log.exception("Keyboard hook error")
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            self.error = OSError(ctypes.get_last_error(), "SetWindowsHookEx failed")
            self.ready.set()
            return
        self.ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
        finally:
            user32.UnhookWindowsHookEx(hook)

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
