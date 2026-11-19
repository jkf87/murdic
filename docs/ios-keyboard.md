# iOS 키보드 익스텐션 · App Group · 앱 왕복 설계

머딕 모바일 iOS판에서 "어디서든 입력"을 구현하는 설계 문서다. 작성: IOS 작업자, 2026-11-19.
상태 표시: **[확정]** 정한 것 · **[검증 필요]** 시뮬레이터나 실기기에서 확인해야 하는 것.

## 1. 전제

- 서드파티 키보드 익스텐션은 **마이크를 쓸 수 없다**. 녹음과 전사는 반드시 메인 앱(React Native)에서 한다. **[확정]**
- 키보드 익스텐션은 메모리 한도가 작다(수십 MB 수준). whisper 모델(base 142 MB, small 466 MB)은 키보드에 올리지 않는다. 키보드는 결과 문자열만 다룬다. **[확정]**
- iOS에는 "이전 앱으로 돌아가기" 공개 API가 없다. 앱에서 원래 앱으로는 사용자가 직접 돌아간다(상단 상태 막대의 `◀ 앱 이름` 링크 또는 홈 막대 스와이프). **[확정]**

## 2. 타깃과 식별자

| 타깃 | 종류 | 번들 ID(가안) | 비고 |
| --- | --- | --- | --- |
| `murdic` | RN 앱(메인) | `com.murdic.mobile` | 녹음·whisper.rn·정리·결과 기록 |
| `MurdicKeyboard` | Custom Keyboard Extension(Swift) | `com.murdic.mobile.keyboard` | 앱 안에 Embed App Extensions로 포함 |

- App Group: `group.com.murdic.mobile` (두 타깃 entitlements에 모두 넣는다).
- URL scheme: `murdic` (앱 Info.plist `CFBundleURLTypes`).
- 번들 ID 앞부분과 Team ID는 실제 Apple 개발자 계정으로 사람이 확정한다. 코드에서는 App Group ID를 상수 한 곳(`SharedConfig`)에만 둔다.

## 3. 왕복 흐름

```
[다른 앱 입력란] ─ 머딕 키보드 🎤 탭
   │ ① req = UUID, App Group에 pending{req, createdAt} 기록
   │ ② murdic://dictate?req=<req>&src=keyboard 열기
   ▼
[머딕 앱] 받아쓰기 화면 (URL로 열리면 바로 녹음 시작)
   │ ③ 녹음(AVAudioSession record, 16 kHz mono WAV 임시 파일)
   │ ④ 정지 → whisper.rn 전사(ko 고정) → cleanup.ts 정리
   │ ⑤ App Group에 result{req, text, finishedAt} 기록 + Darwin 알림 발송
   │ ⑥ 화면: "원래 앱으로 돌아가면 입력됩니다" + 결과 미리보기/복사
   ▼  사용자가 원래 앱으로 복귀
[다른 앱 입력란] 머딕 키보드 다시 표시
   │ ⑦ viewWillAppear / Darwin 알림 → result 읽기
   │ ⑧ result.req == pending.req 이고 5분 이내면 textDocumentProxy.insertText(text)
   │ ⑨ consumed 표시(같은 결과 두 번 넣지 않기), pending 지움
```

### 3.1 키보드 → 앱 열기 (②)

- `extensionContext.open(_:)`은 Today 위젯용이라 키보드에서는 동작하지 않는다. **[확정]**
- 응답자 체인을 따라 올라가 `UIApplication` 인스턴스를 찾고 `open(_:options:completionHandler:)`를 부르는 방식을 쓴다. 공개 API를 우회하는 방식이다. **[검증 필요: 실기기 동작 · App Store 심사]**
- 열기에 실패하면 키보드에 "머딕 앱을 열어 말한 뒤 돌아오세요" 안내를 띄운다. 이 경우에도 ⑤~⑨는 같다(사용자가 앱을 직접 열면 pending이 남아 있으므로 앱이 이어받는다).
- 보조 진입점(선택): App Intents `StartDictationIntent`(`openAppWhenRun`)를 두면 단축어·동작 버튼에서도 같은 화면을 연다. 키보드 왕복의 필수 요소는 아니다.

### 3.2 앱 쪽 (③~⑥)

- RN `Linking`으로 `murdic://dictate` 를 받는다. `req`가 있으면 키보드 모드(결과를 App Group에 기록), 없으면 일반 모드(복사/공유).
- App Group 기록은 iOS 네이티브 모듈 `MurdicShared`가 맡는다(`mobile/ios/` 안, IOS 작업자 담당).
  - `writeResult(req: string, text: string): Promise<void>`
  - `readPending(): Promise<{req: string, createdAt: number} | null>`
  - Android에는 이 모듈이 없다. JS는 `Platform.OS === 'ios' && NativeModules.MurdicShared`일 때만 부른다.
- 녹음 파일은 앱 `tmp/`에 두고 전사 뒤 지운다. 모델 파일은 앱 `Application Support/models/`에 두며 App Group에는 넣지 않는다(키보드가 쓰지 않음).

### 3.3 키보드 쪽 (⑦~⑨)

- 결과 감지: `viewWillAppear`에서 한 번 읽고, 키보드가 떠 있는 동안에는 Darwin 알림(`CFNotificationCenterGetDarwinNotifyCenter`, 이름 `com.murdic.mobile.result`)으로 다시 읽는다.
- 삽입 조건: `pending.req == result.req`, `now - finishedAt < 300초`, `consumed != true`. 조건이 맞으면 `insertText` 후 `consumed = true`.
- 주의: 앱 복귀 직후 `textDocumentProxy`가 새 입력란과 아직 연결되지 않았을 수 있다. 첫 시도가 `documentContextBeforeInput == nil`이면 `textDidChange` 콜백에서 한 번 더 시도한다. **[검증 필요]**

### 3.4 App Group 저장 형식

`UserDefaults(suiteName: "group.com.murdic.mobile")`, 키 하나에 JSON 문자열을 저장한다.

```json
// key: "murdic.pending"
{ "req": "0B0F…", "createdAt": 1763540000.12 }
// key: "murdic.result"
{ "req": "0B0F…", "text": "내일 네 시에 만나요.", "finishedAt": 1763540007.80, "consumed": false }
```

결과는 마지막 한 건만 둔다. 삽입 후 텍스트를 비운다. 키보드는 결과 텍스트를 로그에 남기지 않는다.

## 4. 전체 접근 허용(Full Access)

- 키보드 Info.plist `NSExtensionAttributes.RequestsOpenAccess = YES`. **[확정]**
- 이유: 전체 접근 없이 키보드는 App Group 공유 저장소로 앱과 데이터를 주고받을 수 없다(Apple 키보드 가이드의 Open Access 항목). 결과 전달이 막히므로 필수로 둔다. **[검증 필요: 시뮬레이터에서 꺼진 상태로 읽기 실패 확인]**
- 머딕은 네트워크를 쓰지 않는다. 전체 접근을 켜도 키보드는 키 입력을 기록하거나 보내지 않는다는 점을 안내 화면에 적는다.
- 키보드는 `hasFullAccess`가 false면 마이크 버튼 자리에 "설정 › 일반 › 키보드 › 키보드 › 머딕 › 전체 접근 허용" 안내를 보인다.

### 4.1 앱 안내 화면(온보딩)

1. 마이크 권한 허용 (앱 받아쓰기 화면 첫 녹음 때 요청).
2. 설정 › 일반 › 키보드 › 키보드 › 새로운 키보드 추가 › 머딕.
3. 머딕 › 전체 접근 허용 켜기 (이유와 데이터 처리 설명).
4. 메모 앱에서 🌐로 머딕 키보드로 바꾸고 🎤를 눌러 시험.

`UIApplication.openSettingsURLString`은 앱 설정 화면을 연다. 그 화면에 "키보드" 항목이 생기므로 2~3단계 바로가기로 쓴다.

## 5. 키보드 UI(최소)

- 한 줄: 🌐(다음 키보드, `needsInputModeSwitchKey`일 때만) · 큰 🎤 버튼 · 스페이스 · ⌫ · ⏎.
- 상태 문구: "🎤를 누르면 머딕 앱이 열립니다" / "입력했습니다" / "전체 접근을 켜 주세요".
- 일반 자판은 넣지 않는다. 글자 입력은 🌐로 시스템 키보드로 바꿔 쓴다(1차 범위).
- 높이 약 216 pt. 다크 모드 대응.

## 6. 파일 소유와 요청

- IOS 작업자: `mobile/ios/**`(Xcode 프로젝트, Podfile, `MurdicKeyboard/` Swift 소스, `MurdicShared` 네이티브 모듈), `docs/ios-keyboard.md`, `docs/mobile.md`의 iOS 절.
- ANDROID 작업자: `mobile/package.json`, `mobile/src/**`(화면·딥링크 처리·`MurdicShared` 호출). 필요한 JS 변경은 `docs/tasks/REQUESTS.md`에 적어 요청한다.

## 7. whisper.rn iOS

- `pod install`로 whisper.rn을 넣고 Metal 가속을 켠다(`useGpu: true`). CoreML 인코더는 1차 범위에서 뺀다.
- 실측 항목(→ `docs/mobile.md`): 모델 로드 시간, 5초 한국어 WAV 전사 지연(base/small), 앱 메모리 최고치. 시뮬레이터는 맥 CPU/GPU를 쓰므로 실기기 수치와 다르다는 점을 함께 적는다.

## 8. 시뮬레이터 확인 계획

1. 앱 빌드·설치 → 받아쓰기 화면에서 녹음(시뮬레이터는 맥 마이크 사용) → 결과 표시.
2. 시뮬레이터 설정에서 머딕 키보드 추가 + 전체 접근 허용.
3. Safari 주소창 또는 메모 입력란에서 머딕 키보드 🎤 → 앱 열림 확인 → 말하기 → 원래 앱 복귀 → 텍스트 삽입 확인.
4. 전체 접근을 끈 상태에서 안내 문구가 나오는지 확인.

## 9. 다른 방식(지금은 채택 안 함)

- **백그라운드 오디오 세션**(앱을 한 번 열어 두면 백그라운드에서 녹음, 키보드가 Darwin 알림으로 시작·정지 요청): 앱 전환이 없어 사용감이 좋다. 대신 `UIBackgroundModes: audio`가 필요하고 심사 위험과 배터리 문제가 있다. 왕복 방식이 동작한 뒤 2차로 검토한다.
- **키보드 안에서 녹음**: 플랫폼 제약으로 불가.

## 10. 사람이 할 일(체크리스트)

- [ ] Xcode 설치(App Store, Apple ID) 후 `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`, `sudo xcodebuild -license accept`, iOS 시뮬레이터 런타임 받기. — 2026-11-19 현재 이 맥에는 Xcode가 없다(Command Line Tools만).
- [ ] Apple 개발자 계정과 Team ID 확정, 번들 ID 앞부분 결정.
- [ ] App Group `group.com.murdic.mobile` 등록, 앱·키보드 두 타깃 서명(Automatically manage signing).
- [ ] 실기기에서: 키보드 추가, 전체 접근 허용, 응답자 체인 앱 열기 동작, 원래 앱 복귀 후 삽입 확인.
- [ ] App Store 제출 시 응답자 체인 방식 심사 결과 확인, 개인정보 처리 안내(전체 접근 사유) 작성.
