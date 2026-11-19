"""Diagnostics: environment summary, per-device recording test (`murdic-cli mic-test`)."""
import logging
import platform
import sys
import time

from . import __version__

log = logging.getLogger("murdic.diag")


def portaudio_devices():
    """Every PortAudio input device: name, host API, default rate, channels."""
    import sounddevice as sd
    apis = sd.query_hostapis()
    return [dict(index=i, name=d["name"], hostapi=apis[d["hostapi"]]["name"],
                 default_samplerate=d["default_samplerate"], channels=d["max_input_channels"])
            for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]


def environment():
    info = dict(murdic=__version__, windows=platform.platform(), windows_build=sys.getwindowsversion().build,
                python=sys.version.split()[0], frozen=bool(getattr(sys, "frozen", False)))
    try:
        import sounddevice as sd
        info.update(sounddevice=sd.__version__, portaudio=sd.get_portaudio_version()[1])
        info["portaudio_inputs"] = portaudio_devices()
    except Exception as error:
        info["portaudio_error"] = f"{type(error).__name__}: {error}"
    try:
        from .audio import list_microphones
        snapshot = list_microphones()
        info["endpoints"] = [dict(name=m.name, id=m.id, default=m.id == snapshot.default_id)
                             for m in snapshot.devices]
    except Exception as error:
        info["endpoints_error"] = f"{type(error).__name__}: {error}"
    return info


def log_environment():
    """One startup record of versions and input devices (for bug reports)."""
    try:
        info = environment()
        log.info("murdic %s | %s (build %s) | Python %s | frozen=%s | sounddevice %s | %s",
                 info["murdic"], info["windows"], info["windows_build"], info["python"], info["frozen"],
                 info.get("sounddevice"), info.get("portaudio"))
        for device in info.get("portaudio_inputs", []):
            log.info("Input [%s] #%d %s | %.0f Hz | %d ch", device["hostapi"], device["index"], device["name"],
                     device["default_samplerate"], device["channels"])
        for endpoint in info.get("endpoints", []):
            log.info("Endpoint %s%s", endpoint["name"], " (default)" if endpoint["default"] else "")
        for key in ("portaudio_error", "endpoints_error"):
            if key in info:
                log.warning("%s: %s", key, info[key])
    except Exception:
        log.exception("Could not record the environment")


def mic_test(name=None, seconds=0.5):
    """Record `seconds` from each microphone (or those whose name contains `name`).

    Returns one dict per device with success, backend, levels and the full traceback
    on failure. Levels are reported, not judged: a quiet room is still a success."""
    import numpy as np

    from .audio import Capture, list_microphones
    from .engine import SAMPLE_RATE
    snapshot = list_microphones()
    devices = [m for m in snapshot.devices if not name or name.casefold() in m.name.casefold()]
    results = []
    for mic in devices:
        capture = Capture(mic).start()
        capture.started.wait(5)
        time.sleep(seconds)
        row = dict(name=mic.name, id=mic.id, default=mic.id == snapshot.default_id)
        try:
            audio, max_db = capture.stop()
            row.update(ok=True, backend=capture.backend, seconds=round(len(audio) / SAMPLE_RATE, 3),
                       samples=int(len(audio)), peak=round(float(np.abs(audio).max()) if len(audio) else 0.0, 6),
                       max_block_dbfs=round(max_db, 1))
        except Exception as error:
            from .errors import describe
            row.update(ok=False, backend=capture.backend, error=describe(error),
                       traceback=capture.traceback or "")
        results.append(row)
    return results
