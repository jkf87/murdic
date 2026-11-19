/**
 * dictate/cleanup.py 의 TypeScript 포팅. 받아쓴 발화 한 줄을 보수적으로 다듬는다.
 *
 * Python re와 같은 결과를 내도록 맞춘 부분:
 * - Python \w → [\p{L}\p{N}_] (한글 포함 유니코드 단어 문자). JS \w는 ASCII만이라 쓰지 않는다.
 * - Python \s·\S → str.isspace() 집합. JS \s와 달리 \x1c-\x1f·\x85를 포함하고 \ufeff는 뺀다.
 * - 모든 정규식에 u 플래그. re.I → i, re.sub 전역 치환 → g.
 * - str.strip / rstrip(문자 집합)은 헬퍼로 구현한다.
 * - 명명 그룹·d·v 플래그는 쓰지 않는다 (Hermes).
 */

// Python str.isspace() 집합 (문자 클래스 안에 넣는 형태)
const WS =
  '\\t\\n\\v\\f\\r \\x1c-\\x1f\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';
const SPACE = `[${WS}]`; // \s
const NON_SPACE = `[^${WS}]`; // \S
const WORD = '[\\p{L}\\p{N}_]'; // \w

// 필러: 어 / 음 / 으음 / 아 (단어 경계 안에서만)
const FILLER = new RegExp(
  `(?<!${WORD})(?:어+|으?음+|아+)(?!${WORD})[${WS},，.…]*`,
  'gu',
);

// "아니, 그게 아니라" 류 정정 표지
const CORRECTION = new RegExp(
  `(?<!${WORD})(?:아니[, ]+그게${SPACE}*아니라|그게${SPACE}*아니라|다시${SPACE}*말할게요)` +
    `(?!${WORD})[${WS},，.…]*`,
  'u',
);

// 같은 말 반복: "오늘 오늘", "회의 자료 회의 자료" (최대 4어절)
const TOKEN = `[^${WS},.!?]`;
const REPEAT = new RegExp(
  `(?<!${NON_SPACE})(${TOKEN}+(?: ${TOKEN}+){0,3}?)(?:[,，]? \\1)+(?=[${WS},.!?]|$)`,
  'giu',
);

// 시간·요일 슬롯: "내일 세 시, 아니 네 시"처럼 앞의 값을 지운다
const CLOCK =
  '(?:[0-9]+|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열(?:한|두)?) ?시';
const SLOTS = [
  '[월화수목금토일]요일',
  `(?:오전|오후|저녁|아침) ${CLOCK}`,
  CLOCK,
];

// 고쳐 말한 구간에서 살릴 주제("A는 ...")와, 새 발화가 자체 주제를 가졌는지
const TOPIC = new RegExp(`^([^\\n]{1,45}?(?:은|는))${SPACE}+${NON_SPACE}`, 'u');
const NEW_TOPIC = new RegExp(`^${NON_SPACE}+(?:은|는)${SPACE}`, 'u');

const SPACE_BEFORE_PUNCT = new RegExp(`${SPACE}+([,.!?])`, 'gu');
const PUNCT_BEFORE_HANGUL = /([,!?])(?=[가-힣A-Za-z])/gu;
const ABILITY_SU = new RegExp(
  `([할갈볼될올줄쓸])${SPACE}*수${SPACE}*(있|없)`,
  'gu',
);

const LEADING_SPACE = new RegExp(`^${SPACE}+`, 'u');
const TRAILING_SPACE = new RegExp(`${SPACE}+$`, 'u');
const SPACE_RUN = new RegExp(`${SPACE}+`, 'u');
const HAS_WORD = new RegExp(WORD, 'u');
const ENDS_ALNUM = /[\p{L}\p{N}]$/u;
const QUESTION_END = /(?:까요|습니까|인가요)$/u;

/** Python str.strip(chars) / rstrip(chars) 대응. 지울 글자 집합으로 양끝을 깎는다. */
function stripChars(
  text: string,
  chars: string,
  left: boolean,
  right: boolean,
): string {
  let start = 0;
  let end = text.length;
  if (left) {
    while (start < end && chars.includes(text[start])) {
      start += 1;
    }
  }
  if (right) {
    while (end > start && chars.includes(text[end - 1])) {
      end -= 1;
    }
  }
  return text.slice(start, end);
}

/** Python str.strip() (인자 없음) 대응. 양끝의 Python 공백을 제거한다. */
function stripSpace(text: string): string {
  return text.replace(LEADING_SPACE, '').replace(TRAILING_SPACE, '');
}

/** Python " ".join(text.split()) 대응. 공백 연속을 한 칸으로 줄이고 양끝 공백을 없앤다. */
function collapseSpace(text: string): string {
  return text
    .split(SPACE_RUN)
    .filter(part => part !== '')
    .join(' ');
}

/** Python correct_restart 대응. "월요일 아니 그게 아니라 화요일"처럼 고쳐 말한 부분을 정리한다. */
export function correctRestart(text: string): string {
  let current = text;
  for (const slot of SLOTS) {
    current = current.replace(
      new RegExp(
        `(?<!${WORD})(?:${slot})(?:에|로)?[,，]?${SPACE}+아니[,，]?${SPACE}+` +
          `(?:그게${SPACE}*아니라[,，]?${SPACE}+)?(?=${slot})`,
        'gu',
      ),
      '',
    );
  }

  const parts = current.split(CORRECTION);
  let kept = parts[0];
  for (const replacement of parts.slice(1)) {
    if (stripSpace(replacement) === '') {
      continue;
    }
    // 마지막 문장(. ! ?)까지는 그대로 두고, 고쳐 말한 구간의 주제만 살린다.
    const before = stripChars(kept, ' ,，….!?', false, true);
    const end = Math.max(
      before.lastIndexOf('.'),
      before.lastIndexOf('!'),
      before.lastIndexOf('?'),
    );
    const prefix = before.slice(0, end + 1);
    const fragment = stripSpace(before.slice(end + 1));
    const topic = TOPIC.exec(fragment);
    const newTopic = NEW_TOPIC.test(replacement);
    const keptTopic = topic && !newTopic ? topic[1] : '';
    kept = [prefix, keptTopic, replacement]
      .filter(part => part !== '')
      .join(' ');
  }
  return kept;
}

/** Python clean 대응. 받아쓴 한 발화를 다듬는다. 말할 내용이 없으면 빈 문자열을 돌려준다. */
export function clean(text: string): string {
  let out = correctRestart(collapseSpace(text));
  out = stripChars(out.replace(FILLER, ''), ' ,，', true, true);
  out = out.replace(SPACE_BEFORE_PUNCT, '$1');
  out = out.replace(PUNCT_BEFORE_HANGUL, '$1 ');
  out = out.replace(ABILITY_SU, '$1 수 $2');
  for (;;) {
    const reduced = out.replace(REPEAT, '$1');
    if (reduced === out) {
      break;
    }
    out = reduced;
  }
  out = stripSpace(stripChars(stripSpace(out), ',，', false, true));
  if (!HAS_WORD.test(out)) {
    return '';
  }
  if (ENDS_ALNUM.test(out)) {
    out += QUESTION_END.test(out) ? '?' : '.';
  }
  return out;
}
