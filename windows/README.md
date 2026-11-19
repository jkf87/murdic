# 머딕 · murdic for Windows

Windows 10/11에서 어느 앱의 입력칸이든 **오른쪽 Alt를 누른 채 말하고 떼면**, 내 PC에서 한국어를 전사·정리해 커서 위치에 붙여 넣습니다. macOS판과 같은 정리 규칙(`dictate/cleanup.py`)과 Murmur 전사 튜닝(`docs/STT_TUNING.md`)을 씁니다.

## 설치 (일반 사용자)

1. `murdic-setup.exe` 하나를 받아 실행합니다. 관리자 권한이 필요 없고 `%LOCALAPPDATA%\Programs\murdic`에 설치됩니다. Python은 설치본에 들어 있습니다.
2. **SmartScreen 경고**: 설치 파일에 코드 서명 인증서가 없어 처음에 "Windows의 PC 보호" 창이 뜰 수 있습니다. **추가 정보 → 실행**을 누르세요. 브라우저가 다운로드를 막으면 다운로드 목록에서 **유지 → 그래도 유지**를 고릅니다.
3. 설치가 끝나면 머딕이 실행되고, 처음 한 번 **받아쓰기 모델(약 486 MB)**을 진행률 창에서 내려받습니다. NVIDIA GPU가 있으면 이어서 **GPU 가속 파일(cuBLAS, 약 553 MB)**도 받습니다. 이 단계는 건너뛸 수 있고, 건너뛰면 CPU로 전사합니다. 받은 파일은 SHA-256으로 검증하며, 이후에는 인터넷 없이 동작합니다.
4. 작업 표시줄 오른쪽 알림 영역(⌃ 안쪽일 수 있음)의 머딕 아이콘이 메뉴입니다.

제거는 **설정 › 앱 › 설치된 앱 › 머딕 (murdic)**에서 합니다. 내려받은 모델과 GPU 파일(`%LOCALAPPDATA%\murdic`)은 함께 지워집니다. 설정·힌트·용어 사전(`%APPDATA%\murdic`)은 남습니다.

## 받아쓰기

1. 메모장처럼 붙여넣기가 되는 곳에 커서를 둡니다.
2. **오른쪽 Alt**를 누른 채 말합니다. 화면 아래에 작은 창이 떠서 마이크 레벨과 마이크 이름을 보여 줍니다.
3. 키를 떼면 전사·정리한 문장이 커서 위치에 들어갑니다.

- **한/영 키와 충돌**: 한국어 키보드에서는 오른쪽 Alt가 한/영 키(VK_HANGUL)로 동작하는 경우가 많습니다. 머딕은 이 키를 **0.3초 이상 누르고 있을 때만** 녹음합니다. **짧게 누르면 원래대로 한/영 전환**이 됩니다. 따로 있는 한/영 키는 건드리지 않습니다. 오른쪽 Alt를 누른 채 다른 키를 누르면 녹음을 취소하고 그 조합키를 그대로 보냅니다.
- 트레이 메뉴 **단축키**에서 오른쪽 Ctrl(한자 키 위치 포함), Caps Lock, Scroll Lock으로 바꿀 수 있습니다.
- 녹음 중에 다른 창으로 옮기면 녹음을 취소합니다. 입력 소리가 거의 없으면(−65 dBFS 미만) 마이크 이름과 함께 알려 줍니다.
- 입력할 때는 클립보드의 모든 형식을 보관하고, 문장을 넣어 Ctrl+V를 보낸 다음 450 ms 뒤 원래대로 되돌립니다. 그사이 새로 복사한 내용은 보존합니다. 읽을 수 없는 형식은 건너뛰고 입력은 계속합니다. 받아쓴 문장은 클립보드 기록(Win+V)과 클라우드 클립보드에 남지 않게 표시합니다.

## 트레이 메뉴

| 항목 | 내용 |
| --- | --- |
| 상태 줄 | 준비 상태, 최근 Ctrl+V 전송까지 걸린 ms |
| 엔진 | `GPU (CUDA)` 또는 `CPU (n스레드)` |
| 마이크: 이름 | 시스템 기본값 또는 장치를 직접 선택(다음 실행에도 유지). 고른 장치가 빠지면 기본 마이크로 바뀌고, 다시 꽂아도 자동으로 되돌아가지 않습니다. |
| 3초 마이크 테스트 | 단축키 없이 레벨을 확인합니다. 녹음은 저장하지 않습니다. |
| 단축키 | 오른쪽 Alt(기본) / 오른쪽 Ctrl / Caps Lock / Scroll Lock |
| 도메인 힌트 | Murmur 프리셋(뉴스·시사, 우주·NASA, IT·개발, 의학·건강, 경제·금융, 스포츠) |
| 힌트·용어·설정 폴더 열기 | `hints.txt`: 한 줄에 고유명사 하나(프리셋 뒤에 붙음). `terms.txt`: `잘못 들린 말 => 바른 표기` |
| Windows 시작 시 실행, GPU 가속 받기, 엔진 다시 시작, 종료 | |

## 설치 검증 (2026-11-19)

| 항목 | 결과 |
| --- | --- |
| 설치 파일 | `dist\murdic-setup.exe` 80.8 MB(SHA-256 `1311ac56…f9b2ac`), 설치 후 280.5 MB |
| 새 로컬 계정 무인 설치 (`tools/newuser_install_test.ps1`, PATH에서 Python 제거) | 9.1초, 시작 메뉴 바로 가기·로그인 시 실행 등록 확인 |
| 그 계정에서 첫 CLI 실행 | 모델 463 MB를 받고 SHA-256 검증을 통과한 뒤 전사까지 51.9초. "오늘 오후 3시에 회의실에서 만나요. 준비한 자료도 가져오세요." |
| 그 계정에서 첫 트레이 앱 실행 (NVIDIA PC) | cuBLAS 553 MB를 받고 CUDA float16 엔진이 준비되기까지 54.4초 |
| 제거 | 앱, `%LOCALAPPDATA%\murdic`(모델·GPU), 로그인 시 실행, 바로 가기가 지워지고 `%APPDATA%\murdic` 설정은 남음 |

새 계정 시험은 SSH(비대화형 세션)에서 예약 작업으로 실행했기 때문에 그 계정의 화면에서 메모장 입력은 하지 못했습니다. 메모장 입력은 동결 빌드로 콘솔 사용자의 실제 데스크톱에서 확인했습니다(아래 실측). 예약 작업이 일괄 로그온을 해야 해서 시험 계정을 잠시 관리자 그룹에 넣었습니다. 설치본은 관리자 권한을 요구하지 않습니다(`PrivilegesRequired=lowest`). Windows Sandbox는 이 PC에서 꺼져 있고 켜려면 재부팅이 필요해 쓰지 않았습니다.

## 사람이 확인할 체크리스트

자동 검증은 마이크가 없는 PC에서 스피커 루프백으로 했습니다(아래 실측). 실제 마이크로 다음을 확인해 주세요.

- [ ] 새 사용자 계정 또는 Python이 없는 PC에서 `murdic-setup.exe` 실행 → SmartScreen **추가 정보 → 실행** → 설치 완료 후 진행률 창에서 모델 받기가 끝나는지
- [ ] 트레이 **마이크** 메뉴에 실제 마이크가 보이고, **3초 마이크 테스트** 중 말하면 레벨이 움직이고 "입력 확인 · 장치 이름"이 나오는지
- [ ] 메모장에서 오른쪽 Alt를 누른 채 "오늘 오후 세 시에 회의실에서 만나요"라고 말하고 떼면, 녹음 창에 마이크 이름이 보이고 문장이 입력되는지. 트레이 상태 줄의 "최근 Ctrl+V 전송까지 … ms"를 기록해 주세요.
- [ ] 한국어 키보드에서 오른쪽 Alt(한/영)를 짧게 눌러 한/영 전환이 그대로 되는지, 길게 눌렀을 때만 녹음되는지
- [ ] 크롬 주소창·카카오톡·워드 같은 다른 앱에서도 입력되는지. 붙여넣기 전에 복사해 둔 이미지나 서식 있는 글이 입력 뒤 클립보드에 그대로 남는지
- [ ] USB 마이크를 고른 뒤 녹음 중에 뽑으면 녹음이 취소되고 "연결 끊김 → 기본 마이크 사용" 안내가 나오는지. 다시 꽂아도 기본 마이크가 유지되는지
- [ ] 앱을 종료했다가 다시 열어 마이크·단축키·힌트 선택이 유지되는지
- [ ] 아무 말 없이 키를 눌렀다 떼면 아무것도 입력되지 않는지. 실제로 "감사합니다"라고 말하면 입력되는지
- [ ] Windows 설정 › 개인 정보 › 마이크에서 데스크톱 앱 접근을 끄면 마이크 접근 안내가 나오는지

## 한계

- **관리자 권한으로 실행한 창**(관리자 PowerShell 등)에는 Windows 보안 정책(UIPI) 때문에 단축키와 붙여넣기가 닿지 않습니다.
- 전사 언어는 한국어 고정입니다. 녹음은 메모리에만 두고 전사 뒤 버립니다. 선택적 LLM 훅(`%APPDATA%\murdic\llm-cleanup.cmd|.exe|.ps1`, `MURMUR_LLM_KEY` 설정 시)을 켜면 정리한 텍스트가 그 서비스로 전송됩니다.
- 오른쪽 Alt를 단축키로 쓰는 동안에는 AltGr 조합은 "누른 채 다른 키"로 처리됩니다(녹음 취소 후 그대로 전달).

## 개발

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r windows\requirements-build.txt
.venv\Scripts\python -m pip install nvidia-cublas-cu12==12.9.2.10   # 선택: 개발 중 GPU
.venv\Scripts\python tests\sample.py build\sample.wav                 # Windows TTS(Heami)로 5초 한국어 WAV
.venv\Scripts\python windows\murdic.py wav build\sample.wav --json    # 전사·정리 결과
.venv\Scripts\python windows\murdic.py                                # 트레이 앱
.venv\Scripts\python -m unittest discover -s tests -v                 # 공유 정리 테스트
.venv\Scripts\python -m unittest discover -s windows\tests -v         # Windows e2e·단위 테스트
powershell -ExecutionPolicy Bypass -File windows\build.ps1            # dist\murdic-setup.exe
```

| 경로 | 내용 |
| --- | --- |
| `murdic_win/engine.py` | faster-whisper(CTranslate2), CPU int8 / CUDA float16 자동, 단축 인코더 창 |
| `murdic_win/postprocess.py` | Murmur 환각 필터·용어 교정·VAD·힌트 프리셋 1:1 이식 |
| `murdic_win/hotkey.py` | 저수준 키보드 훅 + 누름 상태 기계(한/영 탭 재전송) |
| `murdic_win/audio.py` | WASAPI 입력 목록·선택·폴백·녹음 |
| `murdic_win/paste.py` | 클립보드 보관 → Ctrl+V → 복원 |
| `murdic_win/app.py`, `overlay.py`, `tray.py`, `firstrun.py` | 트레이 앱, 녹음 창, 첫 실행 다운로드 |
| `murdic.spec`, `installer.iss`, `build.ps1` | PyInstaller onedir + Inno Setup |
| `tools/engine_compare.py`, `tools/desktop_e2e.py` | 엔진 비교, 실제 데스크톱 전체 경로 실측 |

엔진 선택 근거와 지연 측정은 [docs/windows-engine.md](../docs/windows-engine.md)에 있습니다.

## 지연 실측

측정일 2026-11-19 · Ryzen 5 3600 · RTX A4000 · Windows 11 26200 · Win11 메모장(Store판 11.2609). Heami 음성으로 만든 5초 한국어 WAV(`tests/sample.py`)를 썼고 LLM 훅은 껐습니다. 동결 빌드(`dist\murdic`)를 콘솔 사용자의 실제 데스크톱에서 실행했습니다.

**메모장 붙여넣기**: `murdic-cli benchmark build\sample.wav --runs 5`. 측정 구간은 엔진에 음성을 넘긴 때부터 메모장 편집창에 글자가 보일 때까지입니다(WM_GETTEXT로 확인).

| 엔진 | 5회 (ms) | 중앙값 / 최댓값 | 그중 Ctrl+V → 화면 표시 |
| --- | --- | --- | --- |
| GPU (CUDA float16) | 356 / 324 / 287 / 324 / 322 | **324 / 356 ms** | 9–20 ms |
| CPU (int8, 6스레드) | 1,125 / 1,131 / 1,102 / 1,101 / 1,106 | **1,106 / 1,131 ms** | 11–20 ms |

다섯 번 모두 "오늘 오후 3시에 회의실에서 만나요. 준비한 자료도 가져오세요."가 입력됐고, 매번 입력 전 클립보드가 복원됐습니다. 앱 시작부터 모델 준비까지는 GPU 1.9 s, CPU 2.3 s였습니다.

**앱 전체 경로**: `windows/tools/desktop_e2e.py`. 이 PC에는 마이크가 없어서 스피커 루프백을 마이크로 썼습니다. 순서는 메모장에서 오른쪽 Alt 누름(SendInput) → WAV 재생 → 키 뗌 → 메모장에 글자가 보일 때까지입니다.

| 엔진 | 키 뗌 → 메모장 표시, 3회 | 앱 로그의 키 뗌 → Ctrl+V |
| --- | --- | --- |
| GPU | 477 / 361 / 401 ms | 458 / 347 / 388 ms |
| CPU | 1,118 / 1,121 / 1,145 ms | 1,068 / 1,103 / 1,127 ms |

이 측정에서는 단축키 훅, 녹음 창, 녹음, 포커스 확인, 클립보드 복원(6회 모두 성공)이 실제로 동작했습니다. 다만 받아쓴 문장 일부가 틀렸습니다("오후"→"5호", "회의실"→"편의실" 등). 측정 시간에 콘솔 세션 스피커에서 다른 소리(RMS 약 −34 dBFS)가 계속 나서 재생한 음성과 섞였기 때문입니다. 실제 마이크로 잰 지연과 정확도는 위 체크리스트로 확인해 주세요. 마이크를 멈추고 녹음을 마감하는 데는 50 ms 블록 하나 이내가 걸립니다.
