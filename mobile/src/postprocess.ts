/**
 * Murmur 전사 튜닝 이식(docs/STT_TUNING.md) — 디코딩 설정 · 환각 필터 · 용어 교정 · 도메인 힌트.
 *
 * 원본과 1:1:
 *   ~/.murmur/core/src/murmur/postprocess.py  is_hallucination, apply_term_corrections, TERM_CORRECTIONS
 *   ~/.murmur/core/src/murmur/vad.py          RMS 판정(맥판은 webrtcvad가 없어 이 경로를 씀)
 *   맥판 main dictate/backend.py              filter_transcript, 0.3초 말소리 창, REAL_SPEECH_WINDOWS
 * 기대값은 원본 파이썬이 만든다: mobile/scripts/gen_postprocess_cases.py → shared/postprocess_cases.json
 *
 * 순서: 녹음 → Whisper(STT_DECODE_OPTIONS + buildPrompt) → filterTranscript(환각이면 '') → cleanup → 입력
 */

// ---------------------------------------------------------------------------
// 1. 디코딩 설정 (Murmur stt.py: temperature 0.0 단일, condition_on_previous_text False,
//    no_speech 0.6, logprob -1.0, compression_ratio 1.8)
// ---------------------------------------------------------------------------

/**
 * whisper.rn `transcribe`/`transcribeData` 옵션.
 * - temperatureInc 0: whisper.rn(=whisper.cpp) 기본은 0.2라 폴백이 켜져 있다. 원본은 0.0 하나만 쓴다.
 * - condition_on_previous_text False: whisper.rn JSI가 항상 no_context = true로 둔다(옵션 없음).
 * - no_speech 0.6 · logprob -1.0: whisper.cpp 기본값이 같고(whisper_full_default_params),
 *   "no_speech_prob > 0.6 이고 avg_logprob < -1.0 이면 무음으로 건너뜀" 판정도 mlx_whisper와 같다.
 * - compression_ratio 1.8: mlx_whisper에서 이 값은 "더 높은 온도로 다시 디코딩할지"만 정한다.
 *   온도가 0.0 하나뿐이면 다시 할 온도가 없어 결과에 영향이 없다. 그래서 entropy_thold로 근사할 필요가 없다
 *   (whisper.cpp entropy_thold도 폴백 판정에만 쓰인다). 근거: mlx_whisper/transcribe.py decode_with_fallback.
 */
export const STT_DECODE_OPTIONS = {
  language: 'ko',
  temperature: 0,
  temperatureInc: 0,
} as const;

// ---------------------------------------------------------------------------
// 3. 도메인 힌트 프리셋(initial_prompt)
// ---------------------------------------------------------------------------

export const DOMAIN_HINT_PRESETS = [
  {id: 'none', label: '(없음)', hint: ''},
  {id: 'news', label: '뉴스·시사', hint: '트럼프, 나토, NATO, 관세, 대통령'},
  {id: 'space', label: '우주·NASA', hint: '아르테미스, NASA, SLS, 스타십, 오리온'},
  {id: 'it', label: 'IT·개발', hint: 'Claude Code, HWPX, GitHub, API, SDK'},
  {id: 'medical', label: '의학·건강', hint: '혈압, 당뇨, MRI, CT, 항생제'},
  {id: 'finance', label: '경제·금융', hint: 'GDP, 금리, 인플레이션, 연준, 코스피'},
  {id: 'sports', label: '스포츠', hint: '손흥민, 토트넘, 프리미어리그, FIFA'},
] as const;

export type DomainHintPresetId = (typeof DOMAIN_HINT_PRESETS)[number]['id'];

/**
 * initial_prompt를 만든다. 프리셋 힌트 뒤에 사용자 고유명사를 붙인다(맥판 hints.txt처럼 ", "로 잇기).
 * 비면 undefined — 원본도 빈 힌트면 initial_prompt를 넘기지 않는다.
 */
export function buildPrompt(presetId: DomainHintPresetId | string = 'none', userTerms: readonly string[] = []): string | undefined {
  const preset = DOMAIN_HINT_PRESETS.find(p => p.id === presetId)?.hint ?? '';
  const terms = userTerms.map(t => t.trim()).filter(Boolean);
  const prompt = [preset, ...terms].filter(Boolean).join(', ');
  return prompt || undefined;
}

// ---------------------------------------------------------------------------
// 파이썬 문자열 의미 맞추기
// ---------------------------------------------------------------------------

// Python str.isspace()와 같은 공백 집합(str.strip()/split() 기준). JS \s와는 \x1c-\x1f, \x85, ﻿가 다르다.
const PY_WS = '\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';
const PY_WS_RUN = new RegExp(`[${PY_WS}]+`, 'u');
const PY_WS_EDGE = new RegExp(`^[${PY_WS}]+|[${PY_WS}]+$`, 'gu');

const pyStrip = (s: string) => s.replace(PY_WS_EDGE, '');
const pySplit = (s: string) => pyStrip(s).split(PY_WS_RUN).filter(w => w.length > 0);
/** 코드포인트 배열(파이썬 len·인덱스와 같게). */
const cps = (s: string) => Array.from(s);

function stripChars(s: string, chars: string): string {
  const a = cps(s);
  let i = 0;
  let j = a.length;
  while (i < j && chars.includes(a[i])) i++;
  while (j > i && chars.includes(a[j - 1])) j--;
  return a.slice(i, j).join('');
}

function rstripChars(s: string, chars: string): string {
  const a = cps(s);
  let j = a.length;
  while (j > 0 && chars.includes(a[j - 1])) j--;
  return a.slice(0, j).join('');
}

// 원본: [가-힣぀-ゟ゠-ヿ一-鿿㐀-䶿a-zA-Z0-9\s.,!?…·\-\(\)\"\'%:;~、。「」『』（）]
const ALLOWED = new RegExp(
  `[가-힣\\u3040-\\u309F\\u30A0-\\u30FF\\u4E00-\\u9FFF\\u3400-\\u4DBFa-zA-Z0-9${PY_WS}.,!?…·\\-()"'%:;~、。「」『』（）]`,
  'gu',
);

// ---------------------------------------------------------------------------
// 2. 환각 필터 · 용어 교정
// ---------------------------------------------------------------------------

export const HALLUCINATION_PHRASES = [
  '도움이 되었습니다',
  '감사합니다',
  '구독과 좋아요',
  '날씨였습니다',
  '시청해 주셔서 감사합니다',
  '시청해주셔서 감사합니다',
  '좋아요와 구독',
] as const;

/** Murmur is_hallucination 그대로. */
export function isHallucination(text: string | null | undefined): boolean {
  if (!text) return true;
  const stripped = pyStrip(text);
  const chars = cps(stripped);
  const n = chars.length;
  if (n < 2) return true;
  const words = pySplit(stripped);
  if (words.length === 0) return true;

  // 단어 3개 이상인데 고유 단어 ≤ 2
  if (words.length >= 3) {
    const unique = new Set(words.map(w => stripChars(w.toLowerCase(), '.,!?')));
    if (unique.size <= 2) return true;
  }

  // 5~49자 덩어리가 3번 연속 반복 (range(5, min(n // 3, 50)))
  const maxLen = Math.min(Math.floor(n / 3), 50);
  for (let len = 5; len < maxLen; len++) {
    for (let start = 0; start <= n - len * 3; start++) {
      let same = true;
      for (let k = 0; k < len && same; k++) {
        const c = chars[start + k];
        same = c === chars[start + len + k] && c === chars[start + 2 * len + k];
      }
      if (same) return true;
    }
  }

  // 허용 문자 외 15% 초과
  const garbage = cps(stripped.replace(ALLOWED, '')).length;
  if (garbage > n * 0.15) return true;

  // 알려진 환각 문구(끝 마침표 제거 후 정확히 일치)
  if ((HALLUCINATION_PHRASES as readonly string[]).includes(rstripChars(stripped, '.'))) return true;

  // "..." 5회 이상(겹치지 않게 셈 — str.count와 같음)
  if (stripped.split('...').length - 1 >= 5) return true;

  return false;
}

/** Murmur TERM_CORRECTIONS — 순서가 의미 있다("클로드 코드"는 "Claude 코드"가 된다. 원본 동작 유지). */
export const TERM_CORRECTIONS: ReadonlyArray<readonly [string, string]> = [
  ['클드', 'Claude'],
  ['클로드', 'Claude'],
  ['클라우드 코드', 'Claude Code'],
  ['클드 코드', 'Claude Code'],
  ['쉬프트', '시프트'],
  ['코덱스', 'Codex'],
];

/**
 * Murmur apply_term_corrections. 기본 사전 뒤에 사용자 사전(설정 파일)을 같은 방식으로 이어 적용한다.
 * str.replace처럼 모두 바꾼다(split/join — 정규식 특수문자 걱정 없음).
 */
export function applyTermCorrections(
  text: string,
  userCorrections: ReadonlyArray<readonly [string, string]> | Readonly<Record<string, string>> = [],
): string {
  const extra = Array.isArray(userCorrections)
    ? (userCorrections as ReadonlyArray<readonly [string, string]>)
    : Object.entries(userCorrections);
  let out = text;
  for (const [wrong, correct] of [...TERM_CORRECTIONS, ...extra]) {
    if (wrong) out = out.split(wrong).join(correct);
  }
  return out;
}

// ---------------------------------------------------------------------------
// 말소리 창(맥판 예외) — 실제로 받아쓰는 "감사합니다"를 살린다
// ---------------------------------------------------------------------------

export const SAMPLE_RATE = 16000;
/** 0.3초 = 4800샘플 창. */
export const SPEECH_WINDOW_SAMPLES = 4800;
/** Murmur vad.py DEFAULT_RMS_THRESHOLD(맥판은 webrtcvad 없이 이 RMS 판정을 쓴다). */
export const VAD_RMS_THRESHOLD = 0.005;
/** 맥판 REAL_SPEECH_WINDOWS: 말소리 창이 3개(약 0.9초) 이상이면 환각 "문구" 규칙만 믿지 않는다. */
export const REAL_SPEECH_WINDOWS = 3;

/**
 * 16 kHz 모노 16bit PCM에서 RMS ≥ 0.005인 0.3초 창 개수(마지막 짧은 창 포함).
 * 맥판: audio = int16 / 32768, sum(vad.has_speech(audio[i:i+4800]) for i in range(0, len, 4800)).
 */
export function countSpeechWindows(pcm: Int16Array | ArrayBufferLike): number {
  const s = pcm instanceof Int16Array ? pcm : new Int16Array(pcm);
  let count = 0;
  for (let i = 0; i < s.length; i += SPEECH_WINDOW_SAMPLES) {
    const end = Math.min(i + SPEECH_WINDOW_SAMPLES, s.length);
    let sum = 0;
    for (let j = i; j < end; j++) {
      const v = s[j] / 32768;
      sum += v * v;
    }
    if (Math.sqrt(sum / (end - i)) >= VAD_RMS_THRESHOLD) count++;
  }
  return count;
}

/**
 * 맥판 filter_transcript: 환각이면 '' (아무것도 입력하지 않음). 단, 결과가 환각 문구 하나뿐이고
 * 말소리 창이 3개 이상이면 살린다. 그 뒤 용어 교정.
 */
export function filterTranscript(
  raw: string | null | undefined,
  speechWindows: number,
  userCorrections?: Parameters<typeof applyTermCorrections>[1],
): string {
  const text = pyStrip(raw ?? '');
  if (!text) return '';
  if (isHallucination(text)) {
    const phraseOnly =
      (HALLUCINATION_PHRASES as readonly string[]).includes(rstripChars(text, '.')) &&
      speechWindows >= REAL_SPEECH_WINDOWS;
    if (!phraseOnly) return '';
  }
  return applyTermCorrections(text, userCorrections);
}
