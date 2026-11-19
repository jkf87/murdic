"""First-run downloads with progress and SHA-256 checks.

* Whisper small (CTranslate2) from Hugging Face, pinned to one revision.
* On PCs with an NVIDIA driver: cuBLAS 12 from the official PyPI wheel
  (only the two DLLs CTranslate2 needs are extracted).
Files go to %LOCALAPPDATA%\\murdic; interrupted downloads resume from `.part`.
"""
import hashlib
import logging
import os
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path

from . import __version__

log = logging.getLogger("murdic.download")
USER_AGENT = f"murdic/{__version__} (Windows)"
CHUNK = 1 << 20

MODEL_REPO = "Systran/faster-whisper-small"
MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
MODEL_FILES = [  # name, bytes, sha256
    ("config.json", 2370, "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828"),
    ("tokenizer.json", 2203239, "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"),
    ("vocabulary.txt", 459861, "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913"),
    ("model.bin", 483546902, "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"),
]
CUBLAS_WHEEL = dict(
    url="https://files.pythonhosted.org/packages/20/e2/fc9a0e985249d873150276d5afb02e39a66817fedbf1a385724393e505ed/"
        "nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl",
    size=553162896, sha256="623f43027d40d44ceadf0043f002bd25cf353e8f13ce90b9a87057019f560661")
CUBLAS_DLLS = ("cublas64_12.dll", "cublasLt64_12.dll")


class Cancelled(Exception):
    pass


class DownloadError(RuntimeError):
    pass


def data_dir():
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "murdic"


def model_dir():
    return data_dir() / "models" / "faster-whisper-small"


def cuda_dir():
    return data_dir() / "cuda"


def model_ready(folder=None):
    folder = Path(folder or model_dir())
    return all((folder / name).is_file() and (folder / name).stat().st_size == size
               for name, size, _ in MODEL_FILES)


def cublas_ready():
    return all((cuda_dir() / name).is_file() for name in CUBLAS_DLLS)


def nvidia_driver_present():
    return (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvcuda.dll").exists()


def fetch(url, dest, size, sha256, progress=None, cancel=None, offset=0, total=None):
    """Download `url` to `dest` (resuming `dest.part`), verify size and SHA-256."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if have > size:
        part.unlink()
        have = 0
    digest = hashlib.sha256()
    if have:
        with open(part, "rb") as existing:
            for block in iter(lambda: existing.read(CHUNK), b""):
                digest.update(block)
    if have < size:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if have:
            request.add_header("Range", f"bytes={have}-")
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except OSError as error:
            raise DownloadError(f"내려받기 실패: {error}") from error
        with response:
            if have and response.status != 206:   # server ignored Range: start over
                have, digest = 0, hashlib.sha256()
                mode = "wb"
            else:
                mode = "ab" if have else "wb"
            with open(part, mode) as out:
                last = 0.0
                while True:
                    if cancel and cancel.is_set():
                        raise Cancelled()
                    try:
                        block = response.read(CHUNK)
                    except OSError as error:
                        raise DownloadError(f"내려받기가 끊겼습니다: {error}") from error
                    if not block:
                        break
                    out.write(block)
                    digest.update(block)
                    have += len(block)
                    now = time.monotonic()
                    if progress and (now - last > 0.1 or have >= size):
                        last = now
                        progress(offset + have, total or size)
    if have != size or digest.hexdigest() != sha256:
        part.unlink(missing_ok=True)
        raise DownloadError(f"{dest.name} 파일 검증에 실패했습니다. 다시 시도하세요.")
    os.replace(part, dest)
    if progress:
        progress(offset + size, total or size)
    return dest


def download_model(progress=None, cancel=None):
    folder = model_dir()
    total = sum(size for _, size, _ in MODEL_FILES)
    done = 0
    for name, size, sha256 in MODEL_FILES:
        target = folder / name
        if not (target.is_file() and target.stat().st_size == size):
            url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{name}"
            fetch(url, target, size, sha256, progress, cancel, done, total)
        done += size
        if progress:
            progress(done, total)
    log.info("Model ready in %s", folder)
    return folder


def download_cublas(progress=None, cancel=None):
    wheel = data_dir() / "downloads" / CUBLAS_WHEEL["url"].rsplit("/", 1)[1]
    fetch(CUBLAS_WHEEL["url"], wheel, CUBLAS_WHEEL["size"], CUBLAS_WHEEL["sha256"], progress, cancel)
    target = cuda_dir()
    staging = target.with_name("cuda.new")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            name = info.filename.rsplit("/", 1)[-1]
            if name in CUBLAS_DLLS or (info.filename.endswith(".dist-info/License.txt")):
                with archive.open(info) as source, open(staging / (name if name in CUBLAS_DLLS
                                                                   else "NVIDIA-cuBLAS-LICENSE.txt"), "wb") as out:
                    shutil.copyfileobj(source, out, CHUNK)
    if not all((staging / name).is_file() for name in CUBLAS_DLLS):
        raise DownloadError("cuBLAS 휠에서 DLL을 찾지 못했습니다.")
    shutil.rmtree(target, ignore_errors=True)
    os.replace(staging, target)
    wheel.unlink(missing_ok=True)
    log.info("cuBLAS ready in %s", target)
    return target
