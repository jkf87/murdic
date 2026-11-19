import {keyboardRequest} from '../App';

test('키보드 왕복 딥링크에서 req를 읽는다', () => {
  expect(keyboardRequest('murdic://dictate?req=abc-123&src=keyboard')).toBe('abc-123');
  expect(keyboardRequest('murdic://dictate?src=keyboard&req=a%2Fb')).toBe('a/b');
  expect(keyboardRequest('murdic://dictate/?req=x&src=keyboard#top')).toBe('x');
});

test('키보드 요청이 아니면 null', () => {
  expect(keyboardRequest(null)).toBeNull();
  expect(keyboardRequest('murdic://dictate')).toBeNull();
  expect(keyboardRequest('murdic://dictate?req=abc')).toBeNull();
  expect(keyboardRequest('murdic://dictate?src=keyboard')).toBeNull();
  expect(keyboardRequest('murdic://dictatex?req=a&src=keyboard')).toBeNull();
  expect(keyboardRequest('https://example.com/dictate?req=a&src=keyboard')).toBeNull();
});
