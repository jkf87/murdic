#!/usr/bin/env bash
# 머딕 Android IME 전사 실측: 모델별로 WAV 한 개를 IME의 실제 경로(전사→정리→commitText)로 보내고
# logcat의 지연과 앱 메모리(PSS)를 적는다. 디버그 빌드 + 머딕 키보드가 켜진 입력란이 필요하다.
#
#   scripts/android-bench.sh <wav(16 kHz 모노 16bit)> <모델파일 폴더> [모델 id ...]
#   예) scripts/android-bench.sh ../build/sample.wav ~/models base-q5_1 small-q5_1
#
# 모델 파일 이름은 ggml-<id>.bin. 앱이 이미 받은 모델은 폴더에 없어도 된다.
set -euo pipefail
WAV=$1; DIR=$2; shift 2
MODELS=("${@:-base-q5_1 base small-q5_1 small}")
PKG=com.murdic.mobile
ADB=${ADB:-adb}
RUNS=${RUNS:-3}

$ADB push "$WAV" /data/local/tmp/murdic-bench.wav >/dev/null
$ADB shell run-as $PKG cp /data/local/tmp/murdic-bench.wav files/bench.wav
$ADB shell run-as $PKG mkdir -p files/models

for id in ${MODELS[*]}; do
  if [ -f "$DIR/ggml-$id.bin" ] && ! $ADB shell run-as $PKG ls "files/models/ggml-$id.bin" >/dev/null 2>&1; then
    $ADB push "$DIR/ggml-$id.bin" /data/local/tmp/ >/dev/null
    $ADB shell run-as $PKG cp "/data/local/tmp/ggml-$id.bin" files/models/
    $ADB shell rm "/data/local/tmp/ggml-$id.bin"
  fi
  $ADB shell "echo '{\"model\":\"$id\"}' | run-as $PKG sh -c 'cat > files/murdic-settings.json'"
  for i in $(seq 1 "$RUNS"); do
    $ADB logcat -c
    $ADB shell am broadcast -a $PKG.DEBUG_TRANSCRIBE_FILE --es path /data/data/$PKG/files/bench.wav >/dev/null
    line=""
    for _ in $(seq 1 240); do
      line=$($ADB logcat -d -s MurdicIme:I | grep "transcribed" | tail -1 || true)
      [ -n "$line" ] && break
      sleep 0.5
    done
    pss=$($ADB shell dumpsys meminfo $PKG | awk '/TOTAL PSS:/ {print $3; exit} /^ *TOTAL / {print $2; exit}')
    echo "$id run$i ${line#*transcribed } pss_kb=$pss"
  done
done
