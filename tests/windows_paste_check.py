"""Interactive native paste smoke test. Only types into its own test window.

Run: python tests/windows_paste_check.py
The existing clipboard is restored; unsupported clipboard formats abort the test.
"""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import win32gui
from windows.paste import PasteTransaction, clipboard, opened, post_paste

root = tk.Tk()
root.title("murdic · Native paste check")
root.geometry("560x230")
status = tk.StringVar(value="Run check sends Korean text only to the field below.")
ttk.Label(root, textvariable=status, wraplength=520).pack(padx=20, pady=20)
entry = tk.Text(root, height=3)
entry.pack(padx=20, fill="x")
transaction = None


def finish():
    global transaction
    try:
        transaction.restore()
        with opened(root.winfo_id()):
            assert all(clipboard.GetClipboardData(fmt) == data for fmt, data in transaction.saved), \
                "Clipboard changed during the check"
        assert entry.get("1.0", "end-1c") == "오늘 회의 자료를 준비해 주세요.", "Text did not reach the test field"
        status.set("PASS · Korean paste and original clipboard restoration")
        print("PASS: Korean paste and original clipboard restoration", flush=True)
        transaction = None
    except Exception as error:
        status.set("FAIL · " + str(error))
        print("FAIL:", str(error), flush=True)


def start():
    global transaction
    if transaction:
        return
    entry.delete("1.0", "end")
    entry.focus_set()
    try:
        transaction = PasteTransaction(root.winfo_id(), "오늘 회의 자료를 준비해 주세요.")
        post_paste(win32gui.GetForegroundWindow())
        root.after(450, finish)
    except Exception as error:
        if transaction:
            transaction.restore()
            transaction = None
        status.set("FAIL · " + str(error))


def close():
    if transaction:
        transaction.restore()
    root.destroy()


ttk.Button(root, text="Run check", command=start).pack(pady=15)
root.protocol("WM_DELETE_WINDOW", close)
root.mainloop()
