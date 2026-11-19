"""Small JSON settings file (%APPDATA%\\murdic\\settings.json)."""
import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger("murdic.settings")


class Settings:
    def __init__(self, directory):
        self.path = Path(directory) / "settings.json"
        self._lock = threading.Lock()
        self._data = {}
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self._data, dict):
                self._data = {}
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as error:
            log.warning("Ignoring unreadable settings: %s (%s)", error, type(error).__name__, exc_info=True)

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def update(self, **values):
        with self._lock:
            for key, value in values.items():
                if value is None:
                    self._data.pop(key, None)
                else:
                    self._data[key] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, self.path)
