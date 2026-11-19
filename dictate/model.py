"""Whisper model for the menu app: reuse a Hugging Face cache copy, or fetch one copy into murdic's folder."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError
from murmur.stt import DEFAULT_MODEL

# Pinned so every first run downloads the same weights as the release build.
REVISION = "45f3915923c7a79a5a5b5a7d909d39aeb0e5630e"
FILES = ["config.json", "weights.npz"]
MARKER = ".murdic-complete"  # written only after a complete download; its absence means "fetch again"


class ModelError(RuntimeError):
    """The message is Korean and is shown in the settings window."""


def model_dir(config_dir: Path) -> Path:
    return config_dir / "models" / DEFAULT_MODEL.replace("/", "--")


def resolve(config_dir: Path, report=None, refetch: bool = False) -> str:
    """Return a local path that mlx_whisper can load, downloading the model if it is missing."""
    target = model_dir(config_dir)
    if refetch:
        shutil.rmtree(target, ignore_errors=True)
    else:
        if (target / MARKER).is_file():
            return str(target)
        try:
            # A copy already in the Hugging Face cache (for example from murmur) is used as is.
            return snapshot_download(DEFAULT_MODEL, local_files_only=True)
        except LocalEntryNotFoundError:
            pass
    return download(target, report or (lambda fraction: None))


def download(target: Path, report) -> str:
    try:
        info = HfApi().model_info(DEFAULT_MODEL, revision=REVISION, files_metadata=True)
        sizes = {sibling.rfilename: sibling.size or 0 for sibling in info.siblings or []}
        expected = max(sum(sizes[name] for name in FILES), 1)
    except Exception as error:
        raise _failed("모델 정보를 가져오지 못했습니다. 인터넷 연결을 확인한 뒤 다시 받기를 누르세요.", error) from error
    target.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_download(DEFAULT_MODEL, revision=REVISION, local_dir=str(target), allow_patterns=FILES,
                          tqdm_class=_byte_progress(report, expected))
    except Exception as error:
        raise _failed("음성 모델을 받지 못했습니다. 인터넷 연결을 확인한 뒤 다시 받기를 누르세요.", error) from error
    (target / MARKER).write_text(REVISION + "\n", encoding="utf-8")
    report(1.0)
    return str(target)


def _byte_progress(report, expected: int):
    """tqdm class for huggingface_hub: reports the byte fraction over all files being downloaded.

    The hf-xet transfer path keeps data outside the target folder, so counting files on disk shows nothing
    until a file is finished. The per-file byte bars update in both transfer paths.
    """
    from tqdm import tqdm

    counted: dict[int, int] = {}
    last = [0.0]

    class ByteProgress(tqdm):
        def update(self, n=1):
            result = super().update(n)
            if self.unit == "B":
                counted[id(self)] = self.n
                fraction = min(sum(counted.values()) / expected, 0.99)
                if fraction - last[0] >= 0.005:
                    last[0] = fraction
                    report(fraction)
            return result

    return ByteProgress


def _failed(message: str, error: Exception) -> ModelError:
    # Keep the technical detail in the log; the window shows only the Korean sentence.
    print(f"[model] {type(error).__name__}: {error}", file=sys.stderr, flush=True)
    return ModelError(message)
