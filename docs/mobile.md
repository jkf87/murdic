# 머딕 모바일 (React Native, Android + iOS)

앱 폴더 `mobile/`. 작업 분담과 지시는 `docs/tasks/MOBILE.md`. iOS 키보드 설계는 `docs/ios-keyboard.md`(iOS 작업자).
이 문서에는 결정과 실측을 적는다. Android 부분은 ANDROID 작업자가 쓴다.

## 결정

| 항목 | 결정 | 이유 |
| --- | --- | --- |
| RN 버전 | **0.84.1** (bare, New Architecture, Hermes), `@react-native-community/cli@21.0.0`으로 생성 | whisper.rn 0.7.4가 개발·테스트에 쓰는 버전. 0.88.1은 2026-11-19에 나와 라이브러리 호환이 확인되지 않음 |
| 전사 | `whisper.rn@0.7.4` (whisper.cpp, JSI), 언어 `ko` 고정, greedy, 스레드 4, GPU는 iOS만(`useGpu: Platform.OS === 'ios'`) | 지시서 결정. **`beamSize`를 넘기지 말 것**: 1이어도 whisper.rn이 빔 서치로 바꿔 에뮬레이터에서 2~4배 느려졌다(base 3,870→1,986 ms, small 16,985→5,445 ms, 첫 회 기준) |
| 녹음(앱) | `@fugood/react-native-audio-pcm-stream@1.1.4` — 16 kHz 모노 16bit PCM을 base64 조각으로 받아 메모리에서 합친 뒤 `transcribeData(ArrayBuffer)` | whisper.rn과 같은 개발사, 파일을 거치지 않아 녹음이 디스크에 남지 않음 |
| 모델 다운로드 | `@dr.pogodin/react-native-fs@2.38.1` 고정 (`react-native-fs`는 2025-02 이후 정체). 2.41은 네이티브 스펙의 `ArrayBuffer`를 RN 0.84 codegen이 못 읽어 Android 빌드 실패, 2.38.1이 RN 0.84.1 기준 마지막 버전 | 진행률·이어받기 없는 단순 다운로드, 크기 검증 후 `.part` → 이름 바꾸기 |
| 복사 | `@react-native-clipboard/clipboard`, 공유는 RN `Share` | |
| 모델 | HuggingFace `ggerganov/whisper.cpp`의 `base-q5_1`(60 MB) / `base`(148 MB) / `small-q5_1`(190 MB) / `small`(488 MB). **기본 `base`** | 아래 실측: 이 CPU(fp16 지원 arm64)에선 양자화 모델이 f16보다 느렸고 base가 가장 빠르면서 예문을 정확히 받았다. 실기기 실측 뒤 다시 정한다. 앱에서 받아 `<filesDir>/models/ggml-<id>.bin`에 둔다 |
| 모델 선택 공유 | `<filesDir>/murdic-settings.json` `{"model":"base"}` | 앱(JS)과 Android IME(Kotlin)가 같은 파일을 읽는다 |
| 정리 규칙 | `dictate/cleanup.py` → `mobile/src/cleanup.ts`(앱), `…/ime/Cleanup.kt`(Android IME) | IME는 RN 런타임 밖의 서비스라 JS를 부를 수 없음 |
| 정리 예문 | 단일 원본 `mobile/shared/cleanup_cases.json` (`mobile/scripts/export_cleanup_cases.py`가 `tests/test_cleanup.py`에서 뽑음). Python(`tests/test_cleanup_cases.py`), jest, JUnit이 같은 JSON을 검사 | 세 구현이 어긋나지 않게 |
| JS 정규식 | Python `\w` → `[\p{L}\p{N}_]` + `u` 플래그 | JS `\w`는 ASCII만 잡아 한글 경계가 틀어짐 |
| Android IME 전사 | whisper.rn의 `cpp/` 소스로 IME 전용 JNI 라이브러리 `murdicwhisper_*`를 별도 라이브러리 모듈 `:imewhisper`로 빌드 (`android/imewhisper/src/main/cpp`). app 모듈에 CMake를 직접 걸면 RN의 `libappmodules.so` 빌드를 덮어써 앱이 뜨지 않는다(실제로 겪음) | whisper.rn의 `.so`는 JSI 전용이고 심볼을 숨겨(`-fvisibility=hidden`) 링크할 수 없음. 같은 소스를 쓰므로 whisper.cpp 버전은 하나 |
| JNI 문자열 | 전사 결과를 UTF-8 바이트 배열로 넘겨 Kotlin에서 디코드 | `NewStringUTF`는 깨진 UTF-8·4바이트 문자에서 크래시 가능 |
| ABI | `reactNativeArchitectures=arm64-v8a,x86_64` | 실사용 기기는 arm64, armeabi-v7a·x86 빌드는 시간만 늘림. arm64는 fp16 변형과 armv8 기본 변형을 같이 넣고 `/proc/cpuinfo`로 고른다 |
| IME 녹음 | `AudioRecord` `VOICE_RECOGNITION` 16 kHz, 마이크 버튼 누르는 동안. 누르는 순간 모델을 미리 열어 둠 | RECORD_AUDIO 권한은 앱에서 받는다(IME는 런타임 권한 요청 불가 → 상태줄을 누르면 앱이 열림) |
| 무음·환각 | 녹음의 0.1초 창 RMS 최댓값이 0.01(약 −40 dBFS) 미만이면 전사하지 않고 안내. whisper의 `[음악]` 같은 대괄호 표기는 지운다(앱 `src/recorder.ts`·`src/transcriber.ts`, IME `PcmRecorder`·`Cleanup.stripAnnotations`, 같은 테스트 예) | 에뮬레이터 무음 입력에서 whisper가 "[뚜껑이의 상품을…]"을 만들어 그대로 입력됐다 |
| IME 디버그 훅 | 디버그 빌드에서만 `com.murdic.mobile.DEBUG_TRANSCRIBE_FILE` 방송을 받으면 WAV 파일을 같은 전사→정리→`commitText` 경로로 보낸다 | 에뮬레이터에서 사람이 말하지 않고 입력 경로를 검증하기 위해(`mobile/scripts/android-bench.sh`가 이걸로 모델별 실측). 릴리스 빌드(`debuggable=false`)에서는 등록하지 않음 |

## Android 개발 환경 (이 맥에 설치한 것, 2026-11-19)

Homebrew:
- `openjdk@17` (17.x) — `JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`
- cask `android-commandlinetools` — `sdkmanager`/`avdmanager` 부트스트랩용

`sdkmanager --sdk_root=$HOME/Library/Android/sdk` (라이선스 `--licenses` 수락, 합계 약 8.5 GB):
- `cmdline-tools;latest`, `platform-tools`, `emulator`
- `platforms;android-36`, `build-tools;36.0.0` (RN 0.84 템플릿 compileSdk/targetSdk 36)
- `ndk;27.1.12297006`, `cmake;3.22.1` (whisper.cpp 네이티브 빌드)
- `system-images;android-36;google_apis;arm64-v8a` (Apple Silicon에서 하드웨어 가속)

AVD `murdic_api36`: Pixel 7, RAM 6 GB, 데이터 8 GB, `hw.audioInput=yes`.

환경 변수(셸에 넣을 것):
```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export ANDROID_HOME=$HOME/Library/Android/sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
```
`mobile/android/local.properties`(`sdk.dir=…`)는 gitignore 대상이라 각자 만든다.

## 실행

```sh
cd mobile && npm install
emulator -avd murdic_api36 &
npx react-native run-android        # Metro가 함께 뜬다
```

## Android 실측 (에뮬레이터, 2026-11-19)

환경: 호스트 Apple M4 · 32 GB, AVD `murdic_api36`(arm64-v8a, 4코어, RAM 6 GB, fp16 지원 → IME는 `murdicwhisper_v8fp16`, 앱은 `rnwhisper_v8fp16_va_2`), 디버그 빌드(네이티브는 두 경로 모두 `-O3`), 스레드 4, greedy.
음성: `tests/sample.py`와 같은 Yuna 5초 WAV "오늘 오후 세 시에 회의실에서 만나요. 준비한 자료도 가져오세요."
**실기기 수치가 아니다.** 에뮬레이터 vCPU는 M4 코어라 보통 폰보다 빠르다. 실기기 실측은 사람이 할 일.

IME 경로(`android-bench.sh`, 전사→정리→`commitText`, 3회, 모델은 이미 페이지 캐시에 있는 상태):

| 모델 | 전사 ms (1/2/3회) | 모델 열기 | 앱 프로세스 PSS | 결과 |
| --- | --- | --- | --- | --- |
| base-q5_1 | 1,246 / 1,092 / 1,131 | — | 217 MB | 정확 |
| base | 873 / 849 / 866 | 86 ms | 311 MB | 정확 |
| small-q5_1 | 4,054 / 4,546 / 4,907 | 106 ms | 421 MB | 정확 |
| small | 3,026 / 3,603 / 3,746 | 452 ms | 715 MB | 정확 |

앱 경로(whisper.rn `transcribe(file)`, 앱 재시작 직후 1회차 / 2회차, PSS는 RN 디버그 런타임 포함):

| 모델 | 1회차 ms | 2회차 ms | PSS | 결과 |
| --- | --- | --- | --- | --- |
| base-q5_1 | 2,692 | 1,102 | 408 MB | 마침표 대신 쉼표("만나요, 준비한…"). 빔 서치 설정 때는 "준비한 자."에서 잘림 |
| base | 4,102 | 1,285 | 494 MB | 정확 |
| small-q5_1 | 49,858 | 6,645 | 652 MB | 정확 |
| small | 17,610 | 4,369 | 943 MB | 정확 |

- 1회차가 큰 것은 모델 파일을 처음 읽어 들이는 비용이다(IME 표는 같은 파일이 이미 캐시에 있음). 실사용에서는 앱·키보드를 처음 쓸 때 한 번 생긴다. IME는 마이크를 누르는 순간 모델을 미리 연다.
- 앱 경로가 IME 경로보다 1.3~1.5배 느리다(웜 기준). 같은 whisper.cpp 소스·같은 CPU 변형이라 원인은 확인 못 함. 후보: whisper.rn의 JSI/스레드 처리, 디버그 런타임.
- 앱 다운로드: base-q5_1 60 MB를 에뮬레이터 망에서 약 48초, 크기 검증 후 `files/models/`에 저장되고 IME가 같은 파일을 읽는 것 확인.

### 에뮬레이터 검증 결과

- 앱 실행·모델 받기·모델 선택·`sample.wav` 전사(Hermes에서 `cleanup.ts` 동작) 확인.
- IME: `ime enable/set`으로 켜고, 이 시스템 이미지에 메모 앱(Keep 등)과 Play 스토어가 없어 **연락처 › 새 연락처 › 메모(Notes) 칸**에서 입력. 디버그 훅으로 "음, 내일 세 시, 아니 네 시에 회의실에서 만나요"(3.2초) → 원문 "음, 내일 3시, 아니 4시에 회의실에서 만나요" → **"내일 4시에 회의실에서 만나요."** 가 입력됨(1,197 ms).
- 실제 마이크 버튼(누름 7초 → 뗌) 경로도 녹음·전사·입력까지 동작. 다만 헤드리스 에뮬레이터에는 호스트 마이크 소리가 들어오지 않아(레벨 0.0000) 말소리 인식은 검증 못 함 → 무음 게이트가 "소리가 거의 들리지 않았어요" 안내를 띄우는 것까지 확인.
- 고친 버그: 손을 뗀 뒤 큐에 남은 레벨 갱신이 결과 문구를 덮던 문제, Android ICU 정규식이 `UNICODE_CHARACTER_CLASS`를 지원하지 않아 IME 정리가 예외로 죽던 문제(JDK 단위 테스트로는 안 잡힘 → `\s`를 Python `isspace` 집합으로 풀어 씀).

### 테스트

- jest 40건(정리 예문 35 + 딥링크 2 + 무음·주석 2 + 앱 렌더 1), `tsc --noEmit`
- JUnit 35건(`./gradlew :app:testDebugUnitTest`: 정리 예문 33 + 무음·주석 2), Python `tests/test_cleanup_cases.py`
- 세 구현이 같은 `mobile/shared/cleanup_cases.json`·`cleanup_extra_cases.json`을 검사

## iOS (IOS 작업자, 2026-11-19)

설계·흐름은 `docs/ios-keyboard.md`. 여기는 결정과 상태만.

| 항목 | 결정 | 이유 |
| --- | --- | --- |
| 키보드 | 네이티브 Swift 타깃 `MurdicKeyboard`(`com.murdic.mobile.keyboard`), RN 없음 | 키보드 메모리 한도가 작고 마이크를 못 씀 |
| 앱 열기 | 응답자 체인에서 `UIApplication`의 `openURL:options:completionHandler:` 호출 | 키보드에서 `extensionContext.open`이 안 됨. 실기기·심사 확인 필요 |
| 결과 전달 | App Group `group.com.murdic.mobile` UserDefaults JSON + Darwin 알림 `com.murdic.mobile.result` | 키보드가 떠 있을 때도 바로 감지 |
| 시각 단위 | `createdAt`·`finishedAt` 밀리초 | JS가 `Date.now() - createdAt`으로 비교 |
| 앱 모듈 | `MurdicShared`(Objective-C, 브리징 헤더 없음) — `writeResult`, `readPending`(5분 지난 것·이미 결과 보낸 것은 null) | New Arch interop 층으로 `NativeModules`에서 보임 |
| URL 전달 | `AppDelegate.application(_:open:options:)`에서 `RCTOpenURLNotification` 직접 발송 | `RCTLinkingManager`와 같은 형식, Swift 헤더 import 문제 회피 |
| 전체 접근 | `RequestsOpenAccess = YES`, 꺼져 있으면 키보드에 설정 안내 | App Group 공유에 필요 |
| Xcode 프로젝트 | `mobile/ios/scripts/add_keyboard_target.rb`(Homebrew CocoaPods의 xcodeproj gem)로 타깃·Embed·entitlements 추가, 재실행 안전 | 프로젝트를 사람 손 없이 재현 |

### iOS 개발 환경(이 맥, 2026-11-19)

- CocoaPods 1.17.0 (Homebrew, Ruby 4.0.10 함께 설치). `cd mobile/ios && pod install` — Xcode 없이도 성공(56초, pod 78개: whisper-rn 0.7.4, RNAudioPcmStream 1.1.4 포함).
- **Xcode 없음**(Command Line Tools만) → iOS 빌드·시뮬레이터 불가. 설치 후 `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`.
- 빌드 전 검사: 키보드 Swift는 Mac Catalyst UIKit으로 `swiftc -typecheck -application-extension` 통과, `MurdicShared.m`은 `clang -fsyntax-only` 통과(일부러 틀린 코드는 실패하는 것 확인). 실제 iOS 빌드는 아직 아니다.

### iOS 실측

아직 없다(Xcode 설치 후 시뮬레이터에서 base·small 모델 로드 시간, 5초 한국어 전사 지연, 메모리 최고치를 잰다). 시뮬레이터는 맥 CPU/GPU를 써서 실기기와 다르다.

## 전사 튜닝 이식 (`docs/STT_TUNING.md`, IOS 작업자, 2026-11-19)

RN은 두 플랫폼이 JS를 같이 쓰므로 `mobile/src/postprocess.ts` 하나로 Android·iOS 모두 적용된다(연결은 `docs/tasks/REQUESTS.md` 요청 참고).

| 원본(Murmur, mlx_whisper) | whisper.rn 0.7.4 (= whisper.cpp, iOS·Android 같은 JSI 코드) | 결과 |
| --- | --- | --- |
| `temperature=0.0` 단일 | `temperature: 0`, **`temperatureInc: 0`** | whisper.cpp 기본 `temperature_inc`가 0.2라 꼭 넘겨야 폴백이 꺼진다 |
| `condition_on_previous_text=False` | JSI가 항상 `no_context = true` | 같음(옵션 없음) |
| `no_speech_threshold=0.6`, `logprob_threshold=-1.0` | JS 옵션 없음, whisper.cpp 기본값 0.6 / -1.0 | 같음. "무음 확률 > 0.6 이고 평균 logprob < -1.0이면 건너뜀" 판정도 같다(whisper.cpp `is_no_speech`) |
| `compression_ratio_threshold=1.8` | 대응 없음(`entropy_thold` 2.4 기본) | **근사하지 않는다.** mlx_whisper `decode_with_fallback`에서 이 값은 다음 온도로 다시 디코딩할지만 정한다. 온도가 0.0 하나라 결과에 영향이 없다. whisper.cpp `entropy_thold`도 폴백 판정에만 쓰여 `temperatureInc: 0`이면 마찬가지 |
| `initial_prompt` | `prompt` | `buildPrompt(프리셋, 사용자 고유명사)` |

- 환각 필터·용어 교정: `postprocess.py` 1:1 이식. 파이썬 의미 맞춤 — 길이·인덱스는 코드포인트, `strip()`/`split()`은 파이썬 공백 집합, 정규식 문자 클래스 동일.
- 맥판 예외(main `dictate/backend.py filter_transcript`): 환각 판정이어도 **결과가 환각 문구 하나뿐이고 0.3초 말소리 창이 3개 이상**이면 살린다("감사합니다" 받아쓰기). 맥판은 webrtcvad가 설치돼 있지 않아 Murmur VAD의 **RMS 경로**(창 RMS ≥ 0.005, int16/32768)를 실제로 쓴다 — 모바일 `countSpeechWindows`도 같은 식.
- 테스트: `mobile/scripts/gen_postprocess_cases.py`가 원본 코드(Murmur `postprocess.py`·`vad.py` + 맥판 main `filter_transcript`)로 `shared/postprocess_cases.json`(환각 58·용어 14·필터 20·말소리 창 14)을 만들고 `__tests__/postprocess.test.ts`가 대조 — 114개 통과. 일부러 틀린 구현(UTF-16 길이, 창 기준 2)은 각각 실패하는 것 확인.
- 알려진 차이: 말소리 창 RMS는 원본이 float32, JS가 float64로 계산한다. 경계(0.005)에 아주 가까운 창에서만 갈릴 수 있다(예문은 경계 ±3%까지 일치).
- iOS 키보드: 앱이 환각으로 버린 경우 `writeResult(req, '')` → 키보드는 아무것도 넣지 않고 "인식된 말이 없어요" 표시.
