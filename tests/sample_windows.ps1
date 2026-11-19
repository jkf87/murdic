$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voice = $synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ko-KR' } | Select-Object -First 1
    if (-not $voice) { throw 'Install a Korean Windows speech voice before generating this fixture.' }
    $synth.SelectVoice($voice.VoiceInfo.Name)
    $synth.Rate = 3
    $format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
    $synth.SetOutputToWaveFile($env:MURDIC_SAMPLE_OUTPUT, $format)
    # Unicode code points keep this script compatible with Windows PowerShell 5.1's default encoding.
    $sentence = -join ([char[]](0xC624,0xB298,0x20,0xD68C,0xC758,0x20,0xC790,0xB8CC,0xB97C,0x20,0xC900,0xBE44,0xD574,0x20,0xC8FC,0xC138,0xC694,0x2E))
    $synth.Speak($sentence)
} finally {
    $synth.Dispose()
}
