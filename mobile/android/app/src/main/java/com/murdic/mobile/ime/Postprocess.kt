package com.murdic.mobile.ime

import kotlin.math.sqrt

/**
 * Murmur 후처리 Kotlin 이식 (IME 전용). 동작은 원본 Python과 같아야 한다.
 *
 * 원본(정답)
 *  - ~/.murmur/core/src/murmur/postprocess.py  is_hallucination, apply_term_corrections, TERM_CORRECTIONS
 *  - ~/.murmur/core/src/murmur/vad.py          _rms_check (맥판은 webrtcvad가 없어 RMS 경로)
 *  - 맥판 main dictate/backend.py              filter_transcript, REAL_SPEECH_WINDOWS
 * 같은 것의 TS 참고 구현: mobile/src/postprocess.ts (상수·프리셋·API 이름을 맞춘다)
 * 기대값 단일 원본: mobile/shared/postprocess_cases.json (PostprocessTest가 읽는다)
 *
 * Python → Kotlin 대응
 * - len·슬라이스: 코드포인트 단위(codePoints). 이모지 한 개는 1칸이다(UTF-16 2칸으로 세지 않는다).
 * - strip()·split(): isPySpace(Python str.isspace() 집합). 이 집합의 문자는 모두 BMP라 UTF-16 단위로 봐도 안전하다.
 * - 정규식은 쓰지 않는다. 패턴 3의 허용 문자 집합은 코드포인트 판정 함수다.
 *   java.util.regex의 UNICODE_CHARACTER_CLASS는 Android에서 지원하지 않는다(IllegalArgumentException).
 * - str.replace: Kotlin String.replace(문자열 그대로). 빈 wrong은 건너뛴다(Python은 글자 사이마다 끼워 넣는다).
 */
object Postprocess {
    data class DomainHintPreset(val id: String, val label: String, val hint: String)

    /** 도메인 힌트 프리셋(initial_prompt). postprocess.ts DOMAIN_HINT_PRESETS와 글자까지 같다. */
    val DOMAIN_HINT_PRESETS: List<DomainHintPreset> = listOf(
        DomainHintPreset("none", "(없음)", ""),
        DomainHintPreset("news", "뉴스·시사", "트럼프, 나토, NATO, 관세, 대통령"),
        DomainHintPreset("space", "우주·NASA", "아르테미스, NASA, SLS, 스타십, 오리온"),
        DomainHintPreset("it", "IT·개발", "Claude Code, HWPX, GitHub, API, SDK"),
        DomainHintPreset("medical", "의학·건강", "혈압, 당뇨, MRI, CT, 항생제"),
        DomainHintPreset("finance", "경제·금융", "GDP, 금리, 인플레이션, 연준, 코스피"),
        DomainHintPreset("sports", "스포츠", "손흥민, 토트넘, 프리미어리그, FIFA"),
    )

    /**
     * initial_prompt를 만든다. 프리셋 힌트 뒤에 사용자 고유명사를 ", "로 잇는다(trim, 빈 것 제외).
     * 비면 null. 원본도 힌트가 비면 initial_prompt를 넘기지 않는다.
     */
    fun buildPrompt(presetId: String, userTerms: List<String>): String? {
        val preset = DOMAIN_HINT_PRESETS.firstOrNull { it.id == presetId }?.hint ?: ""
        val terms = userTerms.map { it.trim() }.filter { it.isNotEmpty() }
        return (listOf(preset) + terms).filter { it.isNotEmpty() }.joinToString(", ").ifEmpty { null }
    }

    /** Murmur 환각 문구(패턴 4). filter_transcript의 _PHRASES와 같은 집합. */
    val HALLUCINATION_PHRASES: List<String> = listOf(
        "도움이 되었습니다",
        "감사합니다",
        "구독과 좋아요",
        "날씨였습니다",
        "시청해 주셔서 감사합니다",
        "시청해주셔서 감사합니다",
        "좋아요와 구독",
    )

    /** Murmur is_hallucination 그대로. */
    fun isHallucination(text: String?): Boolean {
        if (text.isNullOrEmpty()) return true
        val stripped = pyStrip(text)
        val cps = codePointsOf(stripped)
        val n = cps.size
        if (n < 2) return true
        val words = pySplit(stripped)
        if (words.isEmpty()) return true

        // 패턴 1: 단어 3개 이상인데 고유 단어(소문자, 끝 .,!? 제거)가 2개 이하
        if (words.size >= 3) {
            val unique = words.map { stripChars(it.lowercase(), ".,!?") }.toSet()
            if (unique.size <= 2) return true
        }

        // 패턴 2: range(5, min(n // 3, 50)) 길이의 덩어리가 3번 연속
        for (len in 5 until minOf(n / 3, 50)) {
            for (start in 0..(n - len * 3)) {
                var same = true
                var k = 0
                while (same && k < len) {
                    val c = cps[start + k]
                    same = c == cps[start + len + k] && c == cps[start + 2 * len + k]
                    k++
                }
                if (same) return true
            }
        }

        // 패턴 3: 허용 문자 밖이 15% 초과
        val garbage = cps.count { !isAllowedCp(it) }
        if (garbage > n * 0.15) return true

        // 패턴 4: 알려진 환각 문구(끝 마침표를 떼고 정확히 일치)
        if (rstripChars(stripped, ".") in HALLUCINATION_PHRASES) return true

        // 패턴 5: "..."가 5번 이상(겹치지 않게 센다)
        if (countNonOverlapping(stripped, "...") >= 5) return true

        return false
    }

    /** Murmur TERM_CORRECTIONS. 순서가 의미 있다(원본 dict 삽입 순서). */
    val TERM_CORRECTIONS: List<Pair<String, String>> = listOf(
        "클드" to "Claude",
        "클로드" to "Claude",
        "클라우드 코드" to "Claude Code",
        "클드 코드" to "Claude Code",
        "쉬프트" to "시프트",
        "코덱스" to "Codex",
    )

    /**
     * Murmur apply_term_corrections. 기본 사전 뒤에 사용자 사전을 같은 방식으로 잇는다.
     * 빈 wrong은 건너뛴다.
     */
    fun applyTermCorrections(text: String, user: List<Pair<String, String>> = emptyList()): String {
        var out = text
        for ((wrong, correct) in TERM_CORRECTIONS + user) {
            if (wrong.isNotEmpty()) out = out.replace(wrong, correct)
        }
        return out
    }

    /** 0.3초(4800샘플) 말소리 창. */
    const val SPEECH_WINDOW_SAMPLES = 4800

    /** Murmur vad.py DEFAULT_RMS_THRESHOLD. 맥판은 webrtcvad 없이 이 RMS 판정을 쓴다. */
    const val VAD_RMS_THRESHOLD = 0.005

    /** 맥판 REAL_SPEECH_WINDOWS: 말소리 창 3개(약 0.9초) 이상이면 환각 문구 규칙만 믿지 않는다. */
    const val REAL_SPEECH_WINDOWS = 3

    /**
     * 0.3초 창마다 RMS ≥ VAD_RMS_THRESHOLD인 창 수. 마지막 짧은 창도 센다.
     * 맥판: audio = int16/32768, sum(vad.has_speech(audio[i:i+4800]) for i in range(0, len, 4800)).
     * audio는 PcmRecorder.pcm16ToFloat 결과(int16/32768)다.
     */
    fun countSpeechWindows(audio: FloatArray): Int {
        var count = 0
        var i = 0
        while (i < audio.size) {
            val end = minOf(audio.size, i + SPEECH_WINDOW_SAMPLES)
            var sum = 0.0
            for (j in i until end) {
                val v = audio[j].toDouble()
                sum += v * v
            }
            if (sqrt(sum / (end - i)) >= VAD_RMS_THRESHOLD) count++
            i = end
        }
        return count
    }

    /**
     * 맥판 filter_transcript. 환각이면 "" (아무것도 입력하지 않음). 단, 결과가 환각 문구 하나뿐이고
     * 말소리 창이 REAL_SPEECH_WINDOWS개 이상이면 살린다. 그 뒤 용어 교정.
     */
    fun filterTranscript(raw: String?, speechWindows: Int, user: List<Pair<String, String>> = emptyList()): String {
        val text = pyStrip(raw ?: "")
        if (text.isEmpty()) return ""
        if (isHallucination(text)) {
            val phraseOnly =
                rstripChars(text, ".") in HALLUCINATION_PHRASES && speechWindows >= REAL_SPEECH_WINDOWS
            if (!phraseOnly) return ""
        }
        return applyTermCorrections(text, user)
    }

    // ---- Python 문자열 의미 맞추기 ----

    /**
     * 원본 허용 문자 집합(패턴 3): 한글 · 히라가나 · 가타카나 · 한자(통합·확장 A) · ASCII 영숫자 ·
     * Python \s(isPySpace) · 지정 문장부호.
     */
    private fun isAllowedCp(cp: Int): Boolean =
        cp in 0xAC00..0xD7A3 ||
            cp in 0x3040..0x309F ||
            cp in 0x30A0..0x30FF ||
            cp in 0x4E00..0x9FFF ||
            cp in 0x3400..0x4DBF ||
            cp in 0x41..0x5A || cp in 0x61..0x7A || cp in 0x30..0x39 ||
            isPySpace(cp) ||
            cp in PUNCT_CODE_POINTS

    /** . , ! ? … · - ( ) " ' % : ; ~ 、 。 「 」 『 』 （ ） */
    private val PUNCT_CODE_POINTS: Set<Int> =
        ".,!?…·-()\"'%:;~、。「」『』（）".codePoints().toArray().toSet()

    /** Python str.isspace() 집합(str.strip()·split()·\s). Java의 isWhitespace와 다르다(U+0085, U+00A0, U+202F 등). */
    private fun isPySpace(cp: Int): Boolean = when (cp) {
        in 0x09..0x0D, in 0x1C..0x20, 0x85, 0xA0, 0x1680, in 0x2000..0x200A,
        0x2028, 0x2029, 0x202F, 0x205F, 0x3000 -> true
        else -> false
    }

    private fun codePointsOf(s: String): IntArray = s.codePoints().toArray()

    /** Python str.strip() (인자 없음). */
    private fun pyStrip(s: String): String {
        var a = 0
        var b = s.length
        while (a < b && isPySpace(s[a].code)) a++
        while (b > a && isPySpace(s[b - 1].code)) b--
        return s.substring(a, b)
    }

    /** Python str.split() (인자 없음): 공백 덩어리로 나누고 빈 조각은 버린다. */
    private fun pySplit(s: String): List<String> {
        val out = ArrayList<String>()
        var i = 0
        while (i < s.length) {
            while (i < s.length && isPySpace(s[i].code)) i++
            val start = i
            while (i < s.length && !isPySpace(s[i].code)) i++
            if (i > start) out.add(s.substring(start, i))
        }
        return out
    }

    /** Python str.strip(chars): 양끝에서 chars에 속한 문자만 뗀다. */
    private fun stripChars(s: String, chars: String): String {
        var a = 0
        var b = s.length
        while (a < b && chars.indexOf(s[a]) >= 0) a++
        while (b > a && chars.indexOf(s[b - 1]) >= 0) b--
        return s.substring(a, b)
    }

    /** Python str.rstrip(chars): 오른쪽 끝에서 chars에 속한 문자만 뗀다. */
    private fun rstripChars(s: String, chars: String): String {
        var b = s.length
        while (b > 0 && chars.indexOf(s[b - 1]) >= 0) b--
        return s.substring(0, b)
    }

    /** Python str.count(sub): 겹치지 않게 센다. */
    private fun countNonOverlapping(s: String, sub: String): Int {
        var count = 0
        var i = s.indexOf(sub)
        while (i >= 0) {
            count++
            i = s.indexOf(sub, i + sub.length)
        }
        return count
    }
}
