"""Make a reproducible five-second Korean speech fixture.

macOS uses the Yuna voice (`say`); Windows uses the built-in Heami voice
(System.Speech via PowerShell). Both write 16 kHz mono PCM16 padded to 5 s.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import wave

SENTENCE = "오늘 오후 세 시에 회의실에서 만나요. 준비한 자료도 가져오세요."


def synthesize(wav):
    if sys.platform == "win32":
        # Rate 3 keeps Heami's reading of the sentence under five seconds (about 4.5 s).
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ko-KR' } | Select-Object -First 1;"
            "if (-not $v) { throw 'Korean TTS voice (ko-KR) is not installed' };"
            "$s.SelectVoice($v.VoiceInfo.Name); $s.Rate = 3;"
            "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
            "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono);"
            "$s.SetOutputToWaveFile($env:MURDIC_SAMPLE_OUT, $f);"
            "$s.Speak($env:MURDIC_SAMPLE_TEXT); $s.Dispose()"
        )
        env = dict(os.environ, MURDIC_SAMPLE_OUT=str(wav), MURDIC_SAMPLE_TEXT=SENTENCE)
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       check=True, env=env)
    else:
        subprocess.run(["say", "-v", "Yuna", "-r", "190", "-o", str(wav),
                        "--data-format=LEI16@16000", SENTENCE], check=True)


out = pathlib.Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as folder:
    wav = pathlib.Path(folder) / "voice.wav"
    synthesize(wav)
    with wave.open(str(wav)) as source:
        assert source.getparams()[:3] == (1, 2, 16000)
        speech = source.readframes(source.getnframes())
    if len(speech) > 160000:
        raise ValueError("Speech exceeds the five-second fixture")
    with wave.open(str(out), "wb") as target:
        target.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        target.writeframes(speech.ljust(160000, b"\0"))
