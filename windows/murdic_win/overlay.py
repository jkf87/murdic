"""Small floating recording window (level meter + microphone name), like mac/Overlay.swift.

It never takes focus (WS_EX_NOACTIVATE), ignores the mouse (WS_EX_TRANSPARENT)
and is shown/hidden with Win32 calls so the focused app keeps the caret.
"""
import ctypes
import tkinter as tk
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")
GWL_EXSTYLE = -20
WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = 0x8, 0x20, 0x80
WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x80000, 0x8000000
SW_HIDE = 0
SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x10, 0x40
HWND_TOPMOST = wintypes.HWND(-1)
MONITOR_DEFAULTTONEAREST = 2

user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wintypes.UINT)
user32.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
user32.MonitorFromPoint.restype = wintypes.HMONITOR


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


BG, FG, MUTED, TRACK, FILL = "#202124", "#f1f3f4", "#bdc1c6", "#3c4043", "#5bd18b"
FONT = "Malgun Gothic"


def work_area_at_cursor():
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    return info.rcWork


class Overlay:
    def __init__(self, root):
        self.root = root
        self.scale = root.winfo_fpixels("1i") / 96
        s = self.scale
        self.width, self.height = int(324 * s), int(60 * s)
        self.window = tk.Toplevel(root, bg=BG)
        self.window.overrideredirect(True)
        self.window.geometry(f"{self.width}x{self.height}+-20000+-20000")
        self.window.attributes("-topmost", True, "-alpha", 0.96)
        self.canvas = tk.Canvas(self.window, width=self.width, height=self.height, bg=BG,
                                highlightthickness=0, bd=0)
        self.canvas.pack()
        self.label = self.canvas.create_text(int(16 * s), int(20 * s), anchor="w", fill=FG,
                                             font=(FONT, 10, "bold"), text="")
        bar_y = int(42 * s)
        self.bar_box = (int(16 * s), bar_y, int(121 * s), bar_y + int(8 * s))
        self.track = self.canvas.create_rectangle(*self.bar_box, fill=TRACK, width=0)
        self.fill = self.canvas.create_rectangle(*self.bar_box[:3], self.bar_box[3], fill=FILL, width=0)
        self.device = self.canvas.create_text(int(132 * s), bar_y + int(4 * s), anchor="w", fill=MUTED,
                                              font=(FONT, 9), text="")
        self.window.update_idletasks()
        self.hwnd = int(self.window.wm_frame(), 16)
        style = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
                                 | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOPMOST)
        corner = ctypes.c_int(2)  # DWMWCP_ROUND on Windows 11; ignored elsewhere
        dwmapi.DwmSetWindowAttribute(wintypes.HWND(self.hwnd), 33, ctypes.byref(corner), ctypes.sizeof(corner))
        self.window.update()
        user32.ShowWindow(self.hwnd, SW_HIDE)
        self._dismiss = None
        self.visible = False

    def _truncate(self, text, item, width_px):
        self.canvas.itemconfigure(item, text=text)
        if self.canvas.bbox(item)[2] - self.canvas.bbox(item)[0] <= width_px:
            return
        while len(text) > 1:
            text = text[:-1]
            self.canvas.itemconfigure(item, text=text + "…")
            if self.canvas.bbox(item)[2] - self.canvas.bbox(item)[0] <= width_px:
                return

    def show(self, text, microphone=None):
        self._cancel_dismiss()
        s = self.scale
        self._truncate(text, self.label, int(292 * s))
        state = "normal" if microphone else "hidden"
        for item in (self.track, self.fill, self.device):
            self.canvas.itemconfigure(item, state=state)
        if microphone:
            self._truncate(microphone, self.device, int(176 * s))
        # Without a meter the single line sits in the middle.
        self.canvas.coords(self.label, int(16 * s), int((20 if microphone else 30) * s))
        self.update(-160)
        area = work_area_at_cursor()
        x = (area.left + area.right - self.width) // 2
        y = area.bottom - self.height - int(56 * s)
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, x, y, self.width, self.height,
                            SWP_NOACTIVATE | SWP_SHOWWINDOW)
        self.visible = True
        self.canvas.update_idletasks()

    def update(self, db):
        level = min(1.0, max(0.0, (db + 60) / 60))
        x0, y0, x1, y1 = self.bar_box
        self.canvas.coords(self.fill, x0, y0, x0 + (x1 - x0) * level, y1)

    def notice(self, text, seconds=3):
        self.show(text)
        self._dismiss = self.root.after(int(seconds * 1000), self.hide)

    def _cancel_dismiss(self):
        if self._dismiss:
            self.root.after_cancel(self._dismiss)
            self._dismiss = None

    def hide(self):
        self._cancel_dismiss()
        user32.ShowWindow(self.hwnd, SW_HIDE)
        self.visible = False
