/**
 * src/cleanup.ts 가 Python dictate/cleanup.py 와 같은 결과를 내는지 확인한다.
 * - shared/cleanup_cases.json: tests/test_cleanup.py 예문 (scripts/export_cleanup_cases.py가 생성)
 * - shared/cleanup_extra_cases.json: 추가 예문 (Python clean() 출력이 정답)
 */

import { clean } from '../src/cleanup';
import sharedCases from '../shared/cleanup_cases.json';
import extraCases from '../shared/cleanup_extra_cases.json';

type CleanupCase = { raw: string; expected: string };
type CaseFile = { source: string; cases: CleanupCase[] };

const files: Array<[string, CaseFile]> = [
  ['cleanup_cases.json', sharedCases],
  ['cleanup_extra_cases.json', extraCases],
];

describe.each(files)('clean() 이 Python 결과와 같다 (%s)', (_name, file) => {
  test('예문이 비어 있지 않다', () => {
    expect(file.cases.length).toBeGreaterThan(0);
  });

  test.each(file.cases)('$raw', ({ raw, expected }) => {
    expect(clean(raw)).toBe(expected);
    expect(clean(expected)).toBe(expected);
  });
});
