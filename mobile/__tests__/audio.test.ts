import {parseCorrections, parseNouns} from '../App';
import {DEFAULT_SETTINGS, parseSettings} from '../src/models';
import {decodeOptions, postprocess, stripAnnotations} from '../src/transcriber';

const none = {termCorrections: [] as [string, string][]};

test('whisper 대괄호 비음성 표기를 지운다', () => {
  expect(stripAnnotations(' [음악]')).toBe('');
  expect(stripAnnotations('[박수] 오늘  만나요 [웃음]')).toBe('오늘 만나요');
  expect(stripAnnotations('API (v2) 응답')).toBe('API (v2) 응답');
});

test('전사 뒤 순서: 대괄호 → 환각 필터 → 용어 교정 → cleanup', () => {
  // 맥판 예외: 말소리 창 3개 이상이면 "감사합니다"는 실제 말로 본다.
  expect(postprocess('감사합니다', 3, none)).toEqual({raw: '감사합니다', text: '감사합니다.'});
  expect(postprocess('감사합니다', 2, none)).toEqual({raw: '감사합니다', text: '', dropped: 'hallucination'});
  // 문구 규칙 말고 다른 규칙에 걸리면 말소리가 길어도 버린다.
  expect(postprocess('네 네 네 네', 9, none).text).toBe('');
  expect(postprocess('[음악]', 9, none).dropped).toBe('hallucination');
  // 원본 순서상 "클로드 코드"는 "Claude 코드" (docs/STT_TUNING.md)
  expect(postprocess('어 클로드 코드 열어 줘', 5, none).text).toBe('Claude 코드 열어 줘.');
  // 사용자 사전은 기본 사전 뒤에
  expect(postprocess('머디 앱을 열어요', 5, {termCorrections: [['머디', '머딕']]}).text).toBe('머딕 앱을 열어요.');
});

test('디코딩 옵션: Murmur 설정 + 힌트 프롬프트, 빔 서치 없음', () => {
  const none_ = decodeOptions({hintPreset: 'none', properNouns: []});
  expect(none_).toEqual({language: 'ko', temperature: 0, temperatureInc: 0, maxThreads: 4});
  expect(decodeOptions({hintPreset: 'it', properNouns: ['머딕']}).prompt).toBe(
    'Claude Code, HWPX, GitHub, API, SDK, 머딕',
  );
  expect('beamSize' in none_).toBe(false);
});

test('설정 화면 입력 파싱', () => {
  expect(parseNouns('머딕, 코난쌤\n 판교 ,,')).toEqual(['머딕', '코난쌤', '판교']);
  expect(parseCorrections('머디 = 머딕\n깃헙→GitHub\n잘못된 줄\n = 빈말')).toEqual([
    ['머디', '머딕'],
    ['깃헙', 'GitHub'],
  ]);
});

test('설정 파일: 예전 형식·깨진 값은 기본값으로', () => {
  expect(parseSettings('{"model":"small"}')).toEqual({...DEFAULT_SETTINGS, model: 'small'});
  expect(parseSettings('not json')).toEqual(DEFAULT_SETTINGS);
  expect(
    parseSettings(
      '{"model":"x","hintPreset":"news","properNouns":["a",1],"termCorrections":[["a","b"],["",""],"z"]}',
    ),
  ).toEqual({model: DEFAULT_SETTINGS.model, hintPreset: 'news', properNouns: ['a'], termCorrections: [['a', 'b']]});
});
