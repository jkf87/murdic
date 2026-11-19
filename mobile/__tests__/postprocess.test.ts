/**
 * postprocess.ts가 Murmur 원본 파이썬과 같은 결과를 내는지 본다.
 * 기대값: mobile/scripts/gen_postprocess_cases.py 가 원본 코드로 만든 shared/postprocess_cases.json
 */
import cases from '../shared/postprocess_cases.json';
import {
  applyTermCorrections,
  buildPrompt,
  countSpeechWindows,
  filterTranscript,
  isHallucination,
  STT_DECODE_OPTIONS,
  TERM_CORRECTIONS,
} from '../src/postprocess';

type Seg = {const?: number; square?: number; period?: number; n: number};

function buildPcm(spec: Seg[]): Int16Array {
  const total = spec.reduce((a, s) => a + s.n, 0);
  const out = new Int16Array(total);
  let o = 0;
  for (const seg of spec) {
    for (let i = 0; i < seg.n; i++) {
      if (seg.const !== undefined) {
        out[o++] = seg.const;
      } else {
        const half = seg.period! / 2;
        out[o++] = Math.floor(i / half) % 2 === 0 ? seg.square! : -seg.square!;
      }
    }
  }
  return out;
}

describe('원본 파이썬과 같은 결과', () => {
  test.each(cases.hallucination.map(c => [JSON.stringify(c.input), c.input, c.expected] as const))(
    'is_hallucination(%s)',
    (_label, input, expected) => {
      expect(isHallucination(input)).toBe(expected);
    },
  );

  test.each(cases.terms.map(c => [c.input, c.expected] as const))('apply_term_corrections(%j)', (input, expected) => {
    expect(applyTermCorrections(input)).toBe(expected);
  });

  test.each(cases.filter.map(c => [c.input, c.speechWindows, c.expected] as const))(
    'filter_transcript(%j, %i)',
    (input, windows, expected) => {
      expect(filterTranscript(input, windows)).toBe(expected);
    },
  );

  test.each(cases.speechWindows.map(c => [c.name, c.pcm as Seg[], c.expected] as const))(
    '말소리 창 %s',
    (_name, spec, expected) => {
      const pcm = buildPcm(spec);
      expect(countSpeechWindows(pcm)).toBe(expected);
      expect(countSpeechWindows(pcm.buffer)).toBe(expected); // transcribeData에 넘기는 ArrayBuffer 그대로
    },
  );

  test('용어 사전이 원본과 같다(순서 포함)', () => {
    expect(TERM_CORRECTIONS.map(([w, c]) => [w, c])).toEqual(Object.entries(cases._source.term_corrections));
  });

  test('기대값을 RMS VAD(맥판 실제 동작)로 만들었다', () => {
    expect(cases._source.vad_backend).toBe('rms');
    expect(cases._source.rms_threshold).toBe(0.005);
  });
});

describe('맥판 tests/test_postprocess.py 예문', () => {
  test('말소리가 적으면 환각을 버린다', () => {
    expect(filterTranscript('시청해 주셔서 감사합니다.', 1)).toBe('');
    expect(filterTranscript('감사합니다', 0)).toBe('');
    expect(filterTranscript('네 네 네 네', 5)).toBe('');
    expect(filterTranscript('ㅁ', 5)).toBe('');
  });
  test('말소리가 들렸으면 진짜 감사 인사는 남긴다', () => {
    expect(filterTranscript('감사합니다.', 4)).toBe('감사합니다.');
  });
  test('Murmur 용어 교정', () => {
    expect(filterTranscript('코덱스랑 클로드로 작업해요', 6)).toBe('Codex랑 Claude로 작업해요');
  });
});

describe('설정', () => {
  test('사용자 용어 사전은 기본 사전 뒤에 적용', () => {
    expect(applyTermCorrections('머딕 클로드', {머딕: 'murdic'})).toBe('murdic Claude');
    expect(applyTermCorrections('Claude 코드', [['Claude 코드', 'Claude Code']])).toBe('Claude Code');
    expect(filterTranscript('클로드 코드 열어', 5, {'Claude 코드': 'Claude Code'})).toBe('Claude Code 열어');
  });

  test('도메인 힌트 프리셋 + 사용자 고유명사', () => {
    expect(buildPrompt('none')).toBeUndefined();
    expect(buildPrompt('none', [' ', ''])).toBeUndefined();
    expect(buildPrompt('it')).toBe('Claude Code, HWPX, GitHub, API, SDK');
    expect(buildPrompt('news', ['머딕', ' 코난쌤 '])).toBe('트럼프, 나토, NATO, 관세, 대통령, 머딕, 코난쌤');
    expect(buildPrompt('none', ['머딕'])).toBe('머딕');
    expect(buildPrompt('unknown-id', ['머딕'])).toBe('머딕');
  });

  test('디코딩: 한국어 고정, 온도 0, 폴백 없음', () => {
    expect(STT_DECODE_OPTIONS).toEqual({language: 'ko', temperature: 0, temperatureInc: 0});
  });
});
