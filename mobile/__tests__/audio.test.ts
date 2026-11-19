import {SILENCE_LEVEL, speechLevel} from '../src/recorder';
import {stripAnnotations} from '../src/transcriber';

const pcm = (amp: number, seconds = 1) => {
  const n = 16000 * seconds;
  const v = new DataView(new ArrayBuffer(n * 2));
  for (let i = 0; i < n; i++) {
    v.setInt16(i * 2, Math.round(Math.sin(i / 8) * amp * 32767), true);
  }
  return v.buffer;
};

test('무음·아주 작은 소리는 기준 아래, 말소리 크기는 위', () => {
  expect(speechLevel(pcm(0))).toBe(0);
  expect(speechLevel(pcm(0.005))).toBeLessThan(SILENCE_LEVEL);
  expect(speechLevel(pcm(0.1))).toBeGreaterThan(SILENCE_LEVEL);
});

test('whisper 대괄호 비음성 표기를 지운다', () => {
  expect(stripAnnotations(' [음악]')).toBe('');
  expect(stripAnnotations('[박수] 오늘  만나요 [웃음]')).toBe('오늘 만나요');
  expect(stripAnnotations('API (v2) 응답')).toBe('API (v2) 응답');
});
