"""Small, version-independent user settings (no device indices persisted)."""
import json

HOTKEYS = {"오른쪽 Ctrl": 0xA3, "F8": 0x77}


def load(directory):
    try:
        value = json.loads((directory / "windows.json").read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return {}
        device = value.get("microphone")
        if device is not None and (not isinstance(device, dict)
                                  or set(device) != {"name", "hostapi"}
                                  or not all(isinstance(v, str) for v in device.values())):
            value.pop("microphone", None)
        if value.get("hotkey") not in HOTKEYS:
            value.pop("hotkey", None)
        return value
    except (OSError, ValueError):
        return {}


def save(directory, value):
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / "windows.json.tmp"
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(directory / "windows.json")
