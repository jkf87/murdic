# 머딕 모바일 (React Native, Android + iOS)

앱 폴더 `mobile/`. 작업 분담과 지시는 `docs/tasks/MOBILE.md`. iOS 키보드 설계는 `docs/ios-keyboard.md`(iOS 작업자).
이 문서에는 결정과 실측을 적는다. Android 부분은 ANDROID 작업자가 쓴다.

## 결정

| 항목 | 결정 | 이유 |
| --- | --- | --- |
| RN 버전 | **0.84.1** (bare, New Architecture, Hermes), `@react-native-community/cli@21.0.0`으로 생성 | whisper.rn 0.7.4가 개발·테스트에 쓰는 버전. 0.88.1은 2026-11-19에 나와 라이브러리 호환이 확인되지 않음 |
| 전사 | `whisper.rn@0.7.4` (whisper.cpp, JSI), 언어 `ko` 고정, greedy, 스레드 4, GPU 끔 | 지시서 결정. Android는 GPU 경로가 없고 iOS는 iOS 작업자가 Metal을 켬 |
| 녹음(앱) | `@fugood/react-native-audio-pcm-stream@1.1.4` — 16 kHz 모노 16bit PCM을 base64 조각으로 받아 메모리에서 합친 뒤 `transcribeData(ArrayBuffer)` | whisper.rn과 같은 개발사, 파일을 거치지 않아 녹음이 디스크에 남지 않음 |
| 모델 다운로드 | `@dr.pogodin/react-native-fs@2.41.0` (`react-native-fs`는 2025-02 이후 정체) | 진행률·이어받기 없는 단순 다운로드, 크기 검증 후 `.part` → 이름 바꾸기 |
| 복사 | `@react-native-clipboard/clipboard`, 공유는 RN `Share` | |
| 모델 | HuggingFace `ggerganov/whisper.cpp`의 `base-q5_1`(60 MB) / `base`(148 MB) / `small-q5_1`(190 MB, 기본) / `small`(488 MB) | 실측 표 참고. 앱에서 받아 `<filesDir>/models/ggml-<id>.bin`에 둔다 |
| 모델 선택 공유 | `<filesDir>/murdic-settings.json` `{"model":"small-q5_1"}` | 앱(JS)과 Android IME(Kotlin)가 같은 파일을 읽는다 |
| 정리 규칙 | `dictate/cleanup.py` → `mobile/src/cleanup.ts`(앱), `…/ime/Cleanup.kt`(Android IME) | IME는 RN 런타임 밖의 서비스라 JS를 부를 수 없음 |
| 정리 예문 | 단일 원본 `mobile/shared/cleanup_cases.json` (`mobile/scripts/export_cleanup_cases.py`가 `tests/test_cleanup.py`에서 뽑음). Python(`tests/test_cleanup_cases.py`), jest, JUnit이 같은 JSON을 검사 | 세 구현이 어긋나지 않게 |
| JS 정규식 | Python `\w` → `[\p{L}\p{N}_]` + `u` 플래그 | JS `\w`는 ASCII만 잡아 한글 경계가 틀어짐 |
| Android IME 전사 | whisper.rn의 `cpp/` 소스로 IME 전용 JNI 라이브러리 `murdicwhisper_*`를 앱 모듈에서 따로 빌드 (`android/app/src/main/cpp`) | whisper.rn의 `.so`는 JSI 전용이고 심볼을 숨겨(`-fvisibility=hidden`) 링크할 수 없음. 같은 소스를 쓰므로 whisper.cpp 버전은 하나 |
| JNI 문자열 | 전사 결과를 UTF-8 바이트 배열로 넘겨 Kotlin에서 디코드 | `NewStringUTF`는 깨진 UTF-8·4바이트 문자에서 크래시 가능 |
| ABI | `reactNativeArchitectures=arm64-v8a,x86_64` | 실사용 기기는 arm64, armeabi-v7a·x86 빌드는 시간만 늘림. arm64는 fp16 변형과 armv8 기본 변형을 같이 넣고 `/proc/cpuinfo`로 고른다 |
| IME 녹음 | `AudioRecord` `VOICE_RECOGNITION` 16 kHz, 마이크 버튼 누르는 동안. 누르는 순간 모델을 미리 열어 둠 | RECORD_AUDIO 권한은 앱에서 받는다(IME는 런타임 권한 요청 불가 → 상태줄을 누르면 앱이 열림) |
| IME 디버그 훅 | 디버그 빌드에서만 `com.murdic.mobile.DEBUG_TRANSCRIBE_FILE` 방송을 받으면 WAV 파일을 같은 전사→정리→`commitText` 경로로 보낸다 | 에뮬레이터에서 사람이 말하지 않고 입력 경로를 검증하기 위해. 릴리스 빌드(`debuggable=false`)에서는 등록하지 않음 |

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
