package com.murdic.mobile.ime

import java.util.regex.Pattern

/**
 * dictate/cleanup.py 포팅 (IME 전용). 동작은 Python과 같아야 한다.
 * 예문 단일 원본: mobile/shared/cleanup_cases.json (CleanupTest가 읽는다).
 *
 * Python → Java 대응
 * - `\s`·`\S`: Python isspace() 집합을 직접 풀어 씀(아래 WS). `\w`: `[\p{L}\p{N}_]` (Python 정의 그대로. UNICODE_CHARACTER_CLASS의 \w는
 *   No(①·²·½)가 빠지고 Mn·Mc·Me·Pc·ZWJ가 들어가서 Python과 달라진다). `.`, `$`: UNIX_LINES (Python처럼 \n만 줄바꿈으로 본다).
 * - `re.sub` 역참조 `\1` → 치환문자열 `$1`. `re.split`(캡처 그룹 없음) → `Pattern.split(s, -1)`.
 * - `str.split()`, `strip()`/`rstrip(문자집합)`, `isalnum()`은 아래 헬퍼가 Python 정의를 그대로 옮긴다.
 */
object Cleanup {
    // 프로퍼티는 선언 순서대로 초기화된다. BASE·WS가 compile()보다 먼저여야 한다.
    // Android의 java.util.regex(ICU)는 UNICODE_CHARACTER_CLASS를 지원하지 않는다(IllegalArgumentException).
    // 그래서 \s·\S를 Python str.isspace() 집합으로 직접 풀어 쓴다(cleanup.ts와 같은 방식). JDK·Android 공통.
    private val BASE: Int = Pattern.UNIX_LINES
    private const val WS = "\\t\\n\\u000B\\f\\r \\u001C-\\u001F\\u0085\\u00A0\\u1680\\u2000-\\u200A\\u2028\\u2029\\u202F\\u205F\\u3000"

    private fun expandSpaces(regex: String): String = regex
        .replace("[^\\s", "[^$WS")
        .replace("[\\s", "[$WS")
        .replace("\\S", "[^$WS]")
        .replace("\\s", "[$WS]")

    private fun compile(regex: String, extraFlags: Int = 0): Pattern =
        Pattern.compile(expandSpaces(regex), BASE or extraFlags)

    // Python \w (str 패턴) = isalnum() 이거나 '_'. Java \w는 정의가 달라서 쓰지 않는다.
    private const val W = """[\p{L}\p{N}_]"""

    private val FILLER = compile("""(?<!$W)(?:어+|으?음+|아+)(?!$W)[\s,，.…]*""")
    private val REPEAT = compile(
        """(?<!\S)([^\s,.!?]+(?: [^\s,.!?]+){0,3}?)(?:[,，]? \1)+(?=[\s,.!?]|$)""",
        Pattern.CASE_INSENSITIVE or Pattern.UNICODE_CASE,
    )
    private val CORRECTION = compile(
        """(?<!$W)(?:아니[, ]+그게\s*아니라|그게\s*아니라|다시\s*말할게요)(?!$W)[\s,，.…]*""",
    )
    private val SPACE_BEFORE_PUNCT = compile("""\s+([,.!?])""")
    private val COMMA_BEFORE_HANGUL = compile("""([,!?])(?=[가-힣A-Za-z])""")
    private val BOUND_SU = compile("""([할갈볼될올줄쓸])\s*수\s*(있|없)""")
    private val QUESTION_END = compile("""(?:까요|습니까|인가요)$""")
    private val WORD = compile(W)
    private val TOPIC = compile("""^(.{1,45}?(?:은|는))\s+\S""")
    private val NEW_TOPIC = compile("""^\S+(?:은|는)\s""")

    // 교정 슬롯. CLOCK은 SLOTS보다 먼저 선언해야 한다.
    private val CLOCK = """(?:[0-9]+|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열(?:한|두)?) ?시"""
    private val SLOTS = listOf(
        """[월화수목금토일]요일""",
        """(?:오전|오후|저녁|아침) $CLOCK""",
        CLOCK,
    )
    private val RESTART = SLOTS.map { slot ->
        compile("""(?<!$W)(?:$slot)(?:에|로)?[,，]?\s+아니[,，]?\s+(?:그게\s*아니라[,，]?\s+)?(?=$slot)""")
    }

    /** cleanup.py `clean()`. */
    fun clean(text: String): String {
        var s = correctRestart(collapseSpaces(text))
        s = stripChars(FILLER.matcher(s).replaceAll(""), " ,，")
        s = SPACE_BEFORE_PUNCT.matcher(s).replaceAll("\$1")
        s = COMMA_BEFORE_HANGUL.matcher(s).replaceAll("\$1 ")
        s = BOUND_SU.matcher(s).replaceAll("\$1 수 \$2")
        while (true) {
            val reduced = REPEAT.matcher(s).replaceAll("\$1")
            if (reduced == s) break
            s = reduced
        }
        s = pyStrip(rstripChars(pyStrip(s), ",，"))
        if (!WORD.matcher(s).find()) return ""
        if (isPyAlnum(Character.codePointBefore(s, s.length))) {
            s += if (QUESTION_END.matcher(s).find()) "?" else "."
        }
        return s
    }

    /** cleanup.py `correct_restart()`. 공백 정규화는 하지 않는다(clean()이 먼저 정규화한다). */
    fun correctRestart(text: String): String {
        var s = text
        for (pattern in RESTART) {
            s = pattern.matcher(s).replaceAll("")
        }
        val parts = CORRECTION.split(s, -1)
        var kept = parts[0]
        for (replacement in parts.drop(1)) {
            if (replacement.all { isPySpace(it) }) continue
            // 앞 완결 문장은 유지한다. 끊긴 절에서 새 값만 말했으면 그 절의 주어(…은/는)를 살린다.
            val before = rstripChars(kept, " ,，….!?")
            val end = maxOf(before.lastIndexOf('.'), before.lastIndexOf('!'), before.lastIndexOf('?'))
            val prefix = before.substring(0, end + 1)
            val fragment = pyStrip(before.substring(end + 1))
            val topicMatcher = TOPIC.matcher(fragment)
            val topic = if (topicMatcher.lookingAt() && !NEW_TOPIC.matcher(replacement).lookingAt()) {
                topicMatcher.group(1)
            } else {
                ""
            }
            kept = listOf(prefix, topic, replacement).filter { it.isNotEmpty() }.joinToString(" ")
        }
        return kept
    }

    /** Python str.isspace()와 같은 집합 (U+0085, U+001C~U+001F 포함). */
    private fun isPySpace(c: Char): Boolean =
        c == '\u0085' || Character.isWhitespace(c) || Character.isSpaceChar(c)

    /** Python `" ".join(s.split())`: 앞뒤 공백 제거, 공백 덩어리는 한 칸으로. */
    private fun collapseSpaces(s: String): String {
        val sb = StringBuilder(s.length)
        var pending = false
        for (c in s) {
            if (isPySpace(c)) {
                if (sb.isNotEmpty()) pending = true
            } else {
                if (pending) {
                    sb.append(' ')
                    pending = false
                }
                sb.append(c)
            }
        }
        return sb.toString()
    }

    /** Python `str.strip()` (인자 없음): 앞뒤 공백 문자 제거. */
    private fun pyStrip(s: String): String {
        var a = 0
        var b = s.length
        while (a < b && isPySpace(s[a])) a++
        while (b > a && isPySpace(s[b - 1])) b--
        return s.substring(a, b)
    }

    /** Python `str.rstrip(chars)`: 오른쪽에서 chars에 속한 문자만 제거. */
    private fun rstripChars(s: String, chars: String): String {
        var b = s.length
        while (b > 0 && chars.indexOf(s[b - 1]) >= 0) b--
        return s.substring(0, b)
    }

    /** Python `str.strip(chars)`: 양쪽에서 chars에 속한 문자만 제거. */
    private fun stripChars(s: String, chars: String): String {
        var a = 0
        var b = s.length
        while (a < b && chars.indexOf(s[a]) >= 0) a++
        while (b > a && chars.indexOf(s[b - 1]) >= 0) b--
        return s.substring(a, b)
    }

    /**
     * Python `str.isalnum()`: 글자(L*)이거나 숫자(Nd·Nl·No).
     * Character.isLetterOrDigit은 Nl·No(예: ², ①, ½)를 빠뜨리므로 쓰지 않는다.
     */
    private fun isPyAlnum(codePoint: Int): Boolean {
        if (Character.isLetter(codePoint)) return true
        val type = Character.getType(codePoint)
        return type == Character.DECIMAL_DIGIT_NUMBER.toInt() ||
            type == Character.LETTER_NUMBER.toInt() ||
            type == Character.OTHER_NUMBER.toInt()
    }

    /**
     * whisper 원문 정리: "[음악]"·"[박수]" 같은 대괄호 비음성 표기를 지우고 공백을 한 칸으로.
     * 받아쓰기에서 사람이 대괄호를 말할 일은 없다. src/transcriber.ts의 stripAnnotations와 같다.
     */
    fun stripAnnotations(raw: String): String =
        raw.replace(Regex("\\[[^\\]]*\\]"), " ").replace(Regex("\\s+"), " ").trim()
}
