# 머딕 전사 튜닝 사양 (Murmur에서 가져옴 — 모든 플랫폼 공통)

가중치 미세조정은 없다. Murmur(jkf87/murmur, `core/src/murmur/stt.py`·`postprocess.py`, `app/Murmur/Views/SettingsView.swift`)에서 사용자가 튜닝한 **디코딩 설정·후처리·힌트**가 핵심이다. 엔진(MLX/faster-whisper/whisper.cpp)이 달라도 아래를 똑같이 맞춘다.

## 1. 디코딩 설정 (Whisper small, 한국어 고정)
| 항목 | 값 | faster-whisper | whisper.cpp / whisper.rn |
|---|---|---|---|
| language | "ko" | language="ko" | language: 'ko' |
| temperature | 0.0 (폴백 없음) | temperature=0.0 | temperature 0, temperatureInc 0 |
| condition_on_previous_text | False | 같은 이름 | no_context / 이전 텍스트 미사용 |
| no_speech_threshold | 0.6 | 같은 이름 | no_speech_thold 0.6 (지원 시) |
| compression_ratio_threshold | 1.8 | 같은 이름 | 엔트로피 임계(entropy_thold)로 근사 — 근사 방법 docs에 기록 |
| logprob_threshold | -1.0 | log_prob_threshold=-1.0 | logprob_thold -1.0 |
| initial_prompt | 도메인 힌트(아래 3) | initial_prompt | prompt |

## 2. 후처리 (전사 직후, cleanup 전에) — `postprocess.py` 그대로 이식
- **환각 필터 `is_hallucination`** → 참이면 결과 버림(아무것도 입력하지 않음):
  1) 2자 미만 / 빈 문자열  2) 단어 3개 이상인데 고유 단어 ≤2  3) 5~49자 덩어리가 3번 연속 반복
  4) 한·일·중·영·숫자·기본 문장부호 외 문자가 15% 초과  5) 알려진 환각 문구와 일치(끝 마침표 제거 후):
     "도움이 되었습니다", "감사합니다", "구독과 좋아요", "날씨였습니다", "시청해 주셔서 감사합니다", "시청해주셔서 감사합니다", "좋아요와 구독"
  6) "..." 5회 이상
- **용어 교정 `TERM_CORRECTIONS`** (치환, 순서대로): "클드"→"Claude", "클로드"→"Claude", "클라우드 코드"→"Claude Code", "클드 코드"→"Claude Code", "쉬프트"→"시프트", "코덱스"→"Codex"
  ※ 원본 순서상 "클로드 코드"는 "Claude 코드"가 됨 — 원본 동작 그대로 두되, 사전은 사용자가 추가할 수 있게 설정 파일로.
- 정확한 정규식·경계값은 원본 파일을 읽어 1:1로. 예문 테스트를 원본 동작과 대조(Python 원본에 같은 입력을 넣어 기대값 생성).

## 3. 도메인 힌트 프리셋 (initial_prompt)
(없음) / 뉴스·시사: "트럼프, 나토, NATO, 관세, 대통령" / 우주·NASA: "아르테미스, NASA, SLS, 스타십, 오리온" / IT·개발: "Claude Code, HWPX, GitHub, API, SDK" / 의학·건강: "혈압, 당뇨, MRI, CT, 항생제" / 경제·금융: "GDP, 금리, 인플레이션, 연준, 코스피" / 스포츠: "손흥민, 토트넘, 프리미어리그, FIFA"
+ 사용자 고유명사 목록(설정)을 뒤에 붙임. 설정 화면에서 프리셋 선택.

## 순서
녹음 → VAD → Whisper(1의 설정 + 3의 힌트) → 2 환각 필터(버리면 끝) → 2 용어 교정 → cleanup(말버릇·자기수정) → 입력
