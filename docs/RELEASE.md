# 배포판 DMG (`make dmg`)

개발 빌드(`make run`, `make install`)는 그대로입니다. 배포판은 Python과 패키지를 앱 안에 넣은 DMG입니다. 사용자는 DMG를 열어 `murdic.app`을 Applications로 끌어 놓으면 됩니다.

## 빌드

```sh
make dmg
```

결과는 `build/release/`에 생깁니다.

- `murdic-<버전>-arm64.dmg`: 버전을 넣은 이름(예: `murdic-0.3-arm64.dmg`). 버전은 `mac/Info.plist`의 `CFBundleShortVersionString`에서 가져옵니다.
- `murdic-arm64.dmg`: 같은 파일의 버전 없는 이름입니다(APFS 복제본이라 디스크를 더 쓰지 않습니다). README와 사이트의 다운로드 링크가 이 이름을 씁니다. 릴리스에는 두 파일을 함께 올립니다.
- `work/murdic.app`: DMG에 넣기 전의 앱입니다. 검증에 씁니다.

크기 (2026-11-19 실측): DMG 145.4 MB(UDZO), 압축을 풀면 앱 번들 485.2 MB입니다. 목표 300 MB 이하를 만족합니다. 모델(약 481 MB)은 DMG에 넣지 않습니다.

필요한 것: Apple Silicon, Xcode 명령줄 도구(`swiftc`, `codesign`), 로컬 서명 인증서(`scripts/sign-local`이 만든 `murdic Local Code Signing`), 인터넷(첫 빌드 때 런타임, PyPI 휠, murmur 저장소를 받습니다).

`scripts/build-release.py`가 하는 일:

1. python-build-standalone 3.14.10(arm64, 릴리스 20261110)을 `build/cache/`에 받고 SHA256을 확인합니다.
2. `dictate/`, 아이콘, Swift 소스(배포 타깃 macOS 14.0)로 앱을 만듭니다. Info.plist의 `DictatePython`은 번들 안 상대 경로(`Contents/Resources/python/bin/python3`)입니다.
3. `scripts/release-requirements.txt`의 고정 패키지 26개를 `--no-deps`로 설치합니다. `mlx-whisper==0.4.3`과 murmur 코어(커밋 `0c0c409`)도 각각 `--no-deps`로 설치합니다.
4. 테스트, Tk, pip, 헤더, `.pyc`, `bin/`의 부가 스크립트를 지웁니다.
5. 번들 밖을 가리키는 install name과 rpath를 고칩니다(아래 "번들 밖 경로").
6. `scripts/sign-local`로 서명하고 `codesign --verify --deep --strict`로 확인합니다.
7. `/Applications` 바로가기, 배경 이미지, Finder 창 배치를 넣고 UDZO(zlib 9)로 압축합니다.

## 넣지 않은 것

- **torch**: mlx-whisper는 torch를 필수 의존성으로 선언하지만 `torch_whisper.py`에서만 쓰고, murdic은 그 모듈을 import하지 않습니다. 그래서 제외합니다(설치 시 약 536 MB).
- **Whisper 모델**(`mlx-community/whisper-small-mlx`, 약 481 MB): 첫 실행 때 받습니다. 저장 위치는 `~/Library/Application Support/murdic/models/`이고, 리비전은 `45f3915…`로 고정합니다. 설정 창에 진행률이 나오고, 실패하면 **다시 받기** 버튼이 나옵니다. Hugging Face 캐시에 이미 있으면 그대로 씁니다.
- 개발 파일: `.pyc`, `tests/`, `idlelib`, `ensurepip` 등.

## 서명

Developer ID가 없어 공증을 할 수 없습니다. 두 방식을 비교했고, 개발 빌드와 같은 **로컬 인증서**(`scripts/sign-local`)를 골랐습니다.

| 항목 | ad-hoc (`codesign -s -`) | 로컬 인증서 (선택) |
| --- | --- | --- |
| Designated requirement | `cdhash` 기반이라 빌드마다 바뀜 | `identifier "local.murmur.dictate"` + 인증서 leaf라 같은 인증서면 유지 |
| 업데이트 후 마이크·손쉬운 사용·입력 모니터링 허가 | 빌드마다 초기화될 가능성이 큼 | 같은 DR이면 유지 |
| `spctl -a -t exec` | rejected | rejected (차이 없음) |
| 다른 Mac에서 | 첫 실행 안내는 같음 | 같음. 인증서가 없어도 서명은 `codesign --verify`를 통과 |

실측 (같은 앱을 두 방식으로 서명해 비교, 2026-11-19):

- 로컬 인증서로 서명한 DMG 안 앱: `Authority=murdic Local Code Signing`, DR `identifier "local.murmur.dictate" and certificate leaf = H"2b90d642…"`. 개발 설치본(`~/Applications/murdic.app`)과 DR이 같습니다.
- 파일 한 개를 바꾸고 다시 서명했을 때의 DR: ad-hoc은 `cdhash H"ed1313a4…"`에서 `cdhash H"c36bdaad…"`로 바뀌고, 로컬 인증서는 두 번 모두 같은 값입니다.
- `spctl -a -t exec -vv`와 격리 속성(quarantine)을 붙인 `spctl -a -t open --context context:primary-signature`: 두 방식 모두 `rejected`입니다. 로컬 인증서는 `origin=murdic Local Code Signing`이 함께 표시됩니다. 공증이 없으니 당연한 결과입니다.

결정: 로컬 인증서. Gatekeeper 판정은 둘 다 거부되므로 첫 실행 부담은 같습니다. 차이는 업데이트 뒤 권한 유지인데, 로컬 인증서는 같은 DR을 유지합니다. 인증서 개인키는 이 Mac의 로그인 키체인에만 있고, DMG에는 공개 인증서와 서명만 들어갑니다. 앱은 hardened runtime 없이 서명합니다. 공증을 하지 않기 때문입니다.

## 첫 실행 안내 (사용자용)

공증되지 않은 앱이라 macOS가 처음 실행을 막습니다.

1. `murdic.app`을 Applications로 끌어 놓은 뒤 실행합니다. "확인되지 않은 개발자" 경고가 뜨면 닫습니다.
2. macOS 15 이상: **시스템 설정 → 개인정보 보호 및 보안**에서 아래쪽의 **"그래도 열기"**를 누르고 다시 엽니다.
3. 또는 터미널에서 격리 속성을 지웁니다: `xattr -dr com.apple.quarantine /Applications/murdic.app`
4. 처음 실행하면 Whisper 모델(약 481 MB)을 받습니다. 설정 창에서 진행률을 볼 수 있습니다.
5. 마이크, 손쉬운 사용, 입력 모니터링 권한을 설정 창에서 허용합니다.

## 번들 밖 경로 검증

```sh
python3 scripts/verify-release.py <murdic.app> build/sample.wav [--fresh-home]
```

- **otool**: 모든 Mach-O의 링크 라이브러리와 LC_RPATH가 `/usr/lib`, `/System`, 또는 `@` 상대 경로인지 확인합니다. 설치 이름(LC_ID)도 같은 기준입니다.
- **strings**: 모든 파일을 `strings -a`로 훑어 `/opt/homebrew`, `/Users/conanssam-m4`, `~/.murmur`, 사용자 site-packages(`Library/Python/3`), 저장소 경로(`murmur-dictate`)를 찾습니다. 일반 상수(`/tmp`, `/usr/local`, CI 디버그 경로)는 개수만 보고합니다.
- **실행 시**: `env -i PATH=/usr/bin:/bin`, `python -s`, 작업 디렉터리 `Contents/Resources`로 실행해서 `sys.path`와 로드된 모든 모듈 파일이 번들 안인지 확인합니다.
- **엔진**: 메뉴 앱과 같은 JSON 라인 `serve` 프로토콜로 `build/sample.wav`를 전사합니다. `--fresh-home`은 HOME과 HF_HOME을 빈 폴더로 바꿔 모델을 처음부터 받게 합니다.

## 알려진 한계와 사람이 확인할 것

- **Murmur 라이선스**: 코어 저장소 README는 라이선스를 "Private"으로 표기합니다. DMG는 코어를 포함해 공개로 배포하므로, 릴리스 전에 업스트림 조건을 확인해야 합니다.
- **최소 macOS 14.0**: mlx arm64 휠의 태그 기준입니다. 실기 검증은 macOS 26.5 한 대에서만 했습니다.
- **다른 Mac의 첫 실행**: 공증이 없어 경고 창과 "그래도 열기" 흐름은 사람이 직접 봐야 합니다.
- **개발 환경의 numpy**: Homebrew Python 개발 환경은 numpy를 사용자 site-packages(`~/Library/Python/3.14`)에서 가져옵니다. 번들은 이 경로를 쓰지 않고 고정 버전을 넣습니다.
- **권한 유지**: 같은 인증서로 서명한 업데이트에서 마이크·손쉬운 사용·입력 모니터링 허가가 유지되는지는 다른 버전을 설치해 직접 확인해야 합니다.
