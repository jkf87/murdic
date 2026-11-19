# Windows · 초기 지원 / Initial support

Windows 10/11 x64와 **64비트 Python 3.11–3.13**(Tcl/Tk 포함)이 필요합니다. NVIDIA GPU, CUDA, Homebrew, Swift, Murmur 설치는 필요하지 않습니다. CPU의 `faster-whisper` int8 엔진을 사용하며 Mac 설치 방법은 그대로입니다.

## 설치 / Install

저장소를 내려받은 폴더에서 PowerShell로 실행하세요. `python`이 위 버전인지 먼저 확인하세요.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt
.\.venv\Scripts\python.exe -m windows
```

The commands above create a local environment, install Windows dependencies, and open the tray application. Keep the checkout and `.venv` together. No administrator privileges or virtual-environment activation are required. `scripts/setup-windows.ps1` and `scripts/run-windows.ps1` provide equivalent helpers if your PowerShell policy allows local scripts.

첫 실행에는 `small` 모델을 Hugging Face에서 다운로드하므로 인터넷과 약 1 GB의 여유 공간을 준비하세요. 다운로드와 초기화가 끝나면 **준비 완료**가 표시됩니다. 이후 캐시된 모델로 로컬에서 인식합니다. 실행 중 콘솔 창은 열어 두세요. 콘솔 없이 실행하려면 같은 폴더에서 `.\.venv\Scripts\pythonw.exe -m windows`를 사용하세요.

The first launch downloads the model. After caching it, normal dictation works offline. `HF_HUB_OFFLINE=1` can enforce cache-only operation. Windows may warn that symlinks are unavailable; model caching still works without enabling Developer Mode or running as administrator.

## 사용 / Use

1. 설정 화면에서 마이크를 선택하고 **3초 마이크 테스트**를 눌러 레벨을 확인합니다. 기본 입력 장치가 없다면 사용할 마이크를 직접 선택하세요.
2. 메모장처럼 붙여넣기가 가능한 앱에 커서를 놓고 **오른쪽 Ctrl**을 누른 채 한국어로 말합니다. 설정에서 **F8**로 변경할 수 있습니다.
3. 키를 떼면 전사·정리 후 Ctrl+V를 전송합니다. 다른 창으로 이동하거나 Esc 또는 다른 키를 누르면 녹음이 취소됩니다. 전사 중 대상 창을 떠나면 자동 입력이 취소됩니다.
4. 자동 입력이 취소되면 트레이의 **설정 / 결과 보기**에서 최근 결과를 선택해 복사합니다. 제목 표시줄의 X는 트레이로 숨기며, 완전히 종료하려면 트레이 메뉴에서 **종료**를 누릅니다.

Hold right Ctrl (or F8) to record, release to transcribe and paste into the same foreground window. The tray microphone turns red during recording and amber during transcription. The settings window shows the level meter; there is no floating recording overlay in this initial version. A hotkey's ordinary key events are not suppressed. Avoid assigning a key already used by the target application.

## 설정과 데이터 / Settings and data

- `%APPDATA%\murdic\windows.json`: 마이크 이름·오디오 API와 단축키. 장치 번호는 저장하지 않습니다. 저장된 장치가 실행 시 없으면 기본값으로 돌아갑니다. 새 장치를 연결한 뒤 목록에 나타나지 않으면 앱을 다시 실행하세요.
- `%APPDATA%\murdic\hints.txt`: 고유명사를 UTF-8로 한 줄씩 적으면 다음 전사부터 반영됩니다.
- 녹음은 최대 180초이며 메모리에서만 처리합니다. 최근 결과는 앱 메모리에만 남습니다. 모델 캐시는 Hugging Face 기본 캐시 폴더를 사용합니다.
- 외부 LLM 훅은 기본적으로 꺼져 있습니다. 직접 `MURMUR_LLM_KEY` 환경변수와 설정 폴더의 `llm-cleanup.py`를 준비한 경우에만 현재 Python으로 실행합니다. stdin/stdout은 UTF-8이며 제한 시간은 4초입니다. 이때 텍스트의 외부 전송 여부는 작성한 훅에 달려 있습니다.

To choose another compatible CPU model, set `$env:MURDIC_WHISPER_MODEL='base'` before launching. The default `small` trades startup memory and CPU time for Korean accuracy. Model speed depends on the CPU; Mac benchmark numbers do not apply to Windows.

## 알려진 제한 / Known limitations

- 관리자 권한 앱, 보안 입력 창, Ctrl+V를 처리하지 않는 앱에는 자동 입력이 동작하지 않을 수 있습니다. 정상 전송 표시도 대상 앱의 실제 삽입 완료를 보장하지 않습니다. 최근 결과를 직접 복사할 수 있습니다.
- Unicode 텍스트와 바이트 형식(예: HTML/RTF) 클립보드를 보관하고 450 ms 후 복원합니다. 그사이 새로 복사한 내용은 덮어쓰지 않습니다. 비트맵 핸들·파일 목록 등 안전하게 복사할 수 없는 형식은 **클립보드를 변경하기 전에** 자동 입력을 중단합니다. 느리게 붙여넣기를 처리하는 앱은 수동 복사를 사용하세요.
- 마이크가 없거나 접근이 차단되면 **마이크 권한** 버튼으로 Windows 설정을 열고 입력 장치 및 데스크톱 앱 접근을 확인하세요. 앱은 시스템 권한을 자동으로 바꾸지 않습니다. 장치 연결 해제 시 현재 녹음은 취소됩니다.
- 이 버전은 소스 실행 방식입니다. 설치 EXE, 자동 업데이트, GPU 설정 UI, Mac과 동일한 모든 UI 기능은 포함하지 않습니다.

## 검증 / Validation

모델 다운로드나 실제 마이크·클립보드 변경 없이 단위 테스트를 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

실제 모델과 한국어 테스트 음성을 사용하려면 Windows 한국어 음성 합성 음성이 설치되어 있어야 합니다. 테스트 파일은 마이크 녹음이 아닌 로컬 합성 음성입니다.

```powershell
.\.venv\Scripts\python.exe tests\sample.py build\sample.wav
$env:MURDIC_RUN_INTEGRATION='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m dictate wav build\sample.wav --json
```

실제 Windows 붙여넣기 확인은 아래 명령으로 창을 연 뒤 **Run check**를 누르세요. 테스트 창에만 입력하고 원래 클립보드를 복원합니다. 실행 중 다른 내용을 복사하면 복원 검증이 실패할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe tests\windows_paste_check.py
```

The Windows CI workflow runs unit tests on Python 3.11 and 3.13. Real-model, microphone, and interactive paste checks are separate. Before marking the port ready, verify a physical utterance in Notepad, silence, cancellation, device removal, restart persistence, and preservation of a subsequent clipboard copy. Mac native tests still need a Mac.

## Architecture

`dictate/backend.py` retains the shared cleanup, hints, hook, WAV CLI, and JSON-lines worker. On Windows it lazily loads `dictate/windows_stt.py` (`faster-whisper`, CPU int8, bundled Silero VAD); on macOS it keeps the existing Murmur/MLX path. Windows audio conversion uses PyAV, while macOS retains `afconvert`.

`windows/` supplies Tk settings, a pystray icon, sounddevice capture, and guarded Win32 clipboard/keyboard input. Audio stays in memory, recognition runs on a background thread, and Tk updates run only on the main thread. No Murmur source is copied or installed for Windows. Dependencies and model weights retain their respective licenses.
