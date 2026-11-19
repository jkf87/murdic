"""Notification-area icon and menu (pystray). Menu actions are posted to the UI thread."""
import logging
import threading

from PIL import Image, ImageDraw

from . import paths
from .hotkey import HOTKEYS
from .postprocess import HINT_PRESETS

log = logging.getLogger("murdic.tray")


def load_icon(warning=False):
    source = paths.icon_png()
    image = Image.open(source).convert("RGBA").resize((64, 64), Image.LANCZOS) if source else \
        Image.new("RGBA", (64, 64), "#202124")
    if warning:
        image = image.copy()
        ImageDraw.Draw(image).ellipse((40, 40, 63, 63), fill="#f9ab00", outline="#202124", width=3)
    return image


class Tray:
    def __init__(self, app):
        import pystray
        self.pystray = pystray
        self.app = app
        self.icons = {False: load_icon(False), True: load_icon(True)}
        self.icon = pystray.Icon("murdic", self.icons[False], "murdic", menu=pystray.Menu(self._items))
        self._thread = threading.Thread(target=self._run, name="murdic-tray", daemon=True)

    def _run(self):
        try:
            self.icon.run()
        except Exception:
            log.exception("Tray icon stopped")

    def start(self):
        self._thread.start()

    def _post(self, function, *args):
        return lambda icon, item: self.app.post(function, *args)

    def _items(self):
        Item, Menu = self.pystray.MenuItem, self.pystray.Menu
        app = self.app
        selection = app.selection
        mics = [Item(selection.default_title, self._post(app.select_microphone, None),
                     checked=lambda _: selection.pinned_id is None, radio=True)]
        for mic in selection.inputs.devices:
            mics.append(Item(mic.name.replace("&", "&&"), self._post(app.select_microphone, mic),
                             checked=lambda _, m=mic: selection.pinned_id == m.id, radio=True))
        keys = [Item(key.title, self._post(app.select_hotkey, name),
                     checked=lambda _, n=name: app.hotkey_name == n, radio=True)
                for name, key in HOTKEYS.items()]
        presets = [Item(title if not hints else f"{title} — {hints}", self._post(app.select_preset, name),
                        checked=lambda _, n=name: app.preset == n, radio=True)
                   for name, (title, hints) in HINT_PRESETS.items()]
        active = selection.active
        items = [
            Item(app.status, None, enabled=False),
            Item(f"엔진: {app.engine_label}", None, enabled=False),
            Menu.SEPARATOR,
            Item("마이크: " + (active.name.replace("&", "&&") if active else "없음"), Menu(*mics)),
            Item("3초 마이크 테스트", self._post(app.test_microphone), enabled=app.can_test),
            Item("단축키", Menu(*keys)),
            Item("도메인 힌트: " + HINT_PRESETS[app.preset][0], Menu(*presets)),
            Menu.SEPARATOR,
            Item("힌트·용어·설정 폴더 열기", self._post(app.open_config)),
        ]
        if paths.FROZEN:
            items.append(Item("Windows 시작 시 실행", self._post(app.toggle_autostart),
                              checked=lambda _: app.autostart))
        if app.gpu_available_to_download:
            items.append(Item("GPU 가속 받기 (약 553 MB)", self._post(app.download_gpu), enabled=app.can_restart))
        items += [Item("엔진 다시 시작", self._post(app.restart_engine), enabled=app.can_restart),
                  Item("종료", self._post(app.quit))]
        return items

    def refresh(self, warning=False):
        try:
            self.icon.icon = self.icons[warning]
            self.icon.title = ("murdic — " + self.app.status)[:127]
            self.icon.update_menu()
        except Exception:  # the icon may not be running yet
            pass

    def stop(self):
        try:
            self.icon.stop()
        except Exception:
            pass
