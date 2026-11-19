# Windows 전사 엔진 선택: faster-whisper (CTranslate2)

측정일 2026-11-19 · AMD Ryzen 5 3600(6코어) · 32 GB · NVIDIA RTX A4000 16 GB(드라이버 596.71) · Windows 11 Education 26200 · Python 3.13.7. 모델은 Whisper small, 한국어 고정입니다.

## 결론

**faster-whisper 1.2.1(CTranslate2 4.9.0)**을 씁니다. CPU에서는 int8이 기본이고, NVIDIA GPU와 cuBLAS가 있으면 CUDA float16을 자동으로 씁니다. 디코딩 설정은 Murmur와 같습니다([STT_TUNING.md](STT_TUNING.md) §1).

1. **CPU 지연이 가장 짧습니다.** Whisper는 5초 발화에도 30초 창을 인코딩합니다. CTranslate2는 더 짧은 멜 창을 받아 주므로, murdic은 창을 발화 길이에 맞춥니다(최소 15초, 발화보다 3초 이상 길게). 그 결과 30초 창보다 약 1.1초 빠릅니다. Murmur 임계값(압축비 > 1.8, logprob < −1.0)에 걸리는 결과는 Murmur와 똑같은 30초 창으로 다시 디코딩합니다. 10초 창에서는 문장 마침표가 가끔 빠져서 최소를 15초로 정했습니다.
2. **설치가 쉽습니다.** pip 휠 하나에 CPU와 CUDA 백엔드가 같이 들어 있고 PyInstaller로 그대로 묶입니다. GPU에 필요한 것은 cuBLAS DLL 두 개(735 MB)뿐입니다. cuDNN을 빼도 결과와 속도가 같았습니다(아래). whisper.cpp는 CPU판과 CUDA판 바이너리가 따로 있습니다. CUDA판은 1.1 GB(cuBLAS 450 MB + ggml-cuda 544 MB)이고, Python에서 쓰려면 프로세스를 실행하거나(호출마다 모델 로드 430–700 ms) 서버를 띄우거나 바인딩을 직접 빌드해야 합니다.
3. GPU에서는 두 엔진이 비슷합니다(모델 로드 제외 시 whisper.cpp가 조금 느림). 따라서 GPU 성능이 결정 요인은 아닙니다.

## 지연 비교 (따뜻한 상태, 3회 중앙값, ms)

`windows/tools/engine_compare.py`로 Windows TTS(Heami) 문장 다섯 개를 측정했습니다. faster-whisper는 murdic 설정(greedy, temperature 0)을 썼습니다. whisper.cpp(b5454, `whisper-cli`, ggml-small)는 기본값(beam 5)에 murdic과 같은 창 규칙(`-ac`)을 주었고, 호출마다 다시 하는 모델 로드 시간은 뺐습니다.

| 문장 길이 | fw CPU 단축 창 | fw CPU 30초 창 | whisper.cpp CPU | fw CUDA | whisper.cpp CUDA |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2.2 s "네, 알겠습니다." | **862** | 2,005 | 1,898 | **171** | 234 |
| 3.2 s 자기수정 문장 | **936** | 2,004 | 2,116 | **219** | 315 |
| 4.4 s 말버릇 문장 | **1,004** | 2,091 | 2,360 | **250** | 452 |
| 5.6 s 두 문장 | **1,021** | 2,125 | 2,502 | **296** | 464 |
| 16.9 s 세 문장 요약 | **1,834** | 2,790 | 4,717 | **654** | 1,014 |
| 모델 로드(1회) | 1.9–2.9 s | | 0.43–0.47 s/호출 | 1.1–1.5 s | 0.65–0.70 s/호출 |

- 단어는 다섯 문장 모두 단축 창과 30초 창이 같았고, 문장부호만 세 건에서 달랐습니다(어느 한쪽이 늘 낫지는 않았습니다). 16.9초 문장에서 whisper.cpp는 "고객 문의"를 "고객 무늬"로 받아썼습니다.
- 앞선 시험에서 whisper.cpp에 `-ac 768`(15.4초)처럼 발화보다 짧은 창을 고정으로 주자, 16.9초 문장 끝에서 "10시 10시 10시…" 반복 환각이 생겼습니다. 창을 줄일 때는 발화 길이에 맞춰야 합니다.
- 30초 창 기준 CPU 비교(5초 샘플): faster-whisper int8 2.1–2.3 s, whisper.cpp 3.5–3.8 s(인코딩만), `-ac 512` greedy 1.4 s(모델 로드 제외).

## GPU 라이브러리 최소 구성

CTranslate2 4.9 + Whisper small(float16)으로 DLL 조합별로 전사해 봤습니다(`nvidia-cublas-cu12` 12.9, `nvidia-cudnn-cu12` 9.28).

| DLL 구성 | 크기 | 결과 | 따뜻한 지연 |
| --- | ---: | --- | ---: |
| cuBLAS + cuBLASLt | 735 MB | 정확 | 421–452 ms |
| + cuDNN 전체 | 1,948 MB | 정확 | 420–466 ms |

설치본에는 GPU 파일을 넣지 않습니다. NVIDIA 드라이버(`nvcuda.dll`)가 있는 PC에서만 첫 실행 때 PyPI의 공식 휠(553 MB, SHA-256 고정)을 받아 DLL 두 개만 꺼냅니다. GPU가 없거나 로드에 실패하면 CPU int8로 넘어갑니다.

## 앱 전체 지연 실측

[windows/README.md](../windows/README.md#지연-실측)에 메모장 실측(WAV → 전사 → Ctrl+V → 메모장에 보임)과 앱 전체 경로(키 떼기 → 메모장에 보임) 결과가 있습니다.
