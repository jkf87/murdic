"""Make a reproducible five-second Korean speech fixture with macOS Yuna."""
import pathlib
import subprocess
import sys
import tempfile
import wave

out = pathlib.Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as folder:
    wav = pathlib.Path(folder) / "voice.wav"
    subprocess.run(["say", "-v", "Yuna", "-r", "190", "-o", str(wav),
                    "--data-format=LEI16@16000", "오늘 오후 세 시에 회의실에서 만나요. 준비한 자료도 가져오세요."], check=True)
    with wave.open(str(wav)) as source:
        assert source.getparams()[:3] == (1, 2, 16000)
        speech = source.readframes(source.getnframes())
    if len(speech) > 160000:
        raise ValueError("Speech exceeds the five-second fixture")
    with wave.open(str(out), "wb") as target:
        target.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        target.writeframes(speech.ljust(160000, b"\0"))
