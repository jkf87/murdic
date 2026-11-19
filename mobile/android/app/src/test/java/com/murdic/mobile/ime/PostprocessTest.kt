package com.murdic.mobile.ime

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Postprocess를 공유 예문(mobile/shared/postprocess_cases.json, 원본 Python이 만든 기대값)과 대조한다.
 * 묶음(hallucination · terms · filter · speechWindows)마다 @Test 하나가 전부 검사하고, 불일치는 모아서 보여 준다.
 * Parameterized 러너는 같은 클래스의 다른 @Test까지 행마다 다시 돌리므로 쓰지 않는다.
 * 공유 파일이 없거나 묶음이 비면 실패한다. 내장 예문으로 대체하지 않는다.
 */
class PostprocessTest {
    private val cases: JSONObject by lazy { loadCases() }

    @Test
    fun hallucinationGroup() {
        val rows = group("hallucination")
        val bad = mutableListOf<String>()
        for (i in 0 until rows.length()) {
            val r = rows.getJSONObject(i)
            val input = r.nullableString("input")
            val expected = r.getBoolean("expected")
            val got = Postprocess.isHallucination(input)
            if (got != expected) bad += "#$i input=${quote(input)} expected=$expected got=$got"
        }
        assertGroup("hallucination", rows.length(), bad)
    }

    @Test
    fun termsGroup() {
        val rows = group("terms")
        val bad = mutableListOf<String>()
        for (i in 0 until rows.length()) {
            val r = rows.getJSONObject(i)
            val input = r.getString("input")
            val expected = r.getString("expected")
            val got = Postprocess.applyTermCorrections(input)
            if (got != expected) bad += "#$i input=${quote(input)} expected=${quote(expected)} got=${quote(got)}"
        }
        assertGroup("terms", rows.length(), bad)
    }

    @Test
    fun filterGroup() {
        val rows = group("filter")
        val bad = mutableListOf<String>()
        for (i in 0 until rows.length()) {
            val r = rows.getJSONObject(i)
            val input = r.nullableString("input")
            val windows = r.getInt("speechWindows")
            val expected = r.getString("expected")
            val got = Postprocess.filterTranscript(input, windows)
            if (got != expected) {
                bad += "#$i input=${quote(input)} windows=$windows expected=${quote(expected)} got=${quote(got)}"
            }
        }
        assertGroup("filter", rows.length(), bad)
    }

    @Test
    fun speechWindowsGroup() {
        val rows = group("speechWindows")
        val bad = mutableListOf<String>()
        for (i in 0 until rows.length()) {
            val r = rows.getJSONObject(i)
            val name = r.getString("name")
            val bytes = pcmBytes(r.getJSONArray("pcm"))
            val expected = r.getInt("expected")
            val got = Postprocess.countSpeechWindows(PcmRecorder.pcm16ToFloat(bytes, 0, bytes.size))
            if (got != expected) bad += "#$i name=$name expected=$expected got=$got"
        }
        assertGroup("speechWindows", rows.length(), bad)
    }

    @Test
    fun buildPromptNoneWithoutTermsIsNull() {
        assertNull(Postprocess.buildPrompt("none", emptyList()))
    }

    @Test
    fun buildPromptItPresetOnly() {
        assertEquals("Claude Code, HWPX, GitHub, API, SDK", Postprocess.buildPrompt("it", emptyList()))
    }

    @Test
    fun buildPromptTrimsAndDropsBlankUserTerms() {
        assertEquals(
            "트럼프, 나토, NATO, 관세, 대통령, 머딕",
            Postprocess.buildPrompt("news", listOf(" 머딕 ", "")),
        )
    }

    @Test
    fun userDictionaryRunsAfterDefaults() {
        assertEquals(
            "Claude로 Murdic 앱을 연다",
            Postprocess.applyTermCorrections("클로드로 머딕 앱을 연다", listOf("머딕" to "Murdic")),
        )
        // 빈 wrong은 건너뛴다. Python str.replace("", x)는 글자 사이마다 x를 끼우므로 그대로 옮기지 않는다.
        assertEquals("그냥 문장", Postprocess.applyTermCorrections("그냥 문장", listOf("" to "X")))
    }

    private fun group(name: String): JSONArray {
        val rows = cases.getJSONArray(name)
        assertTrue("공유 예문 묶음이 비었다: $name", rows.length() > 0)
        return rows
    }

    private fun assertGroup(name: String, total: Int, bad: List<String>) {
        assertTrue(
            "$name ${total - bad.size}/$total 통과, 불일치 ${bad.size}건:\n" + bad.joinToString("\n"),
            bad.isEmpty(),
        )
    }

    private fun JSONObject.nullableString(key: String): String? = if (isNull(key)) null else getString(key)

    private fun quote(s: String?): String = if (s == null) "null" else "\"$s\""

    /**
     * gen_postprocess_cases.py build_pcm과 같은 int16 리틀엔디언 샘플.
     * const는 값 하나를 n개, square는 +v와 -v를 period/2개씩 번갈아 n개.
     */
    private fun pcmBytes(spec: JSONArray): ByteArray {
        val segs = (0 until spec.length()).map { spec.getJSONObject(it) }
        val bb = ByteBuffer.allocate(segs.sumOf { it.getInt("n") } * 2).order(ByteOrder.LITTLE_ENDIAN)
        for (seg in segs) {
            val n = seg.getInt("n")
            if (seg.has("const")) {
                val v = seg.getInt("const").toShort()
                repeat(n) { bb.putShort(v) }
            } else {
                val v = seg.getInt("square")
                val half = seg.getInt("period") / 2
                for (idx in 0 until n) {
                    bb.putShort((if ((idx / half) % 2 == 0) v else -v).toShort())
                }
            }
        }
        return bb.array()
    }

    private fun loadCases(): JSONObject {
        val dirPath = System.getProperty(SHARED_PROPERTY)
            ?: throw AssertionError("시스템 프로퍼티 $SHARED_PROPERTY 없음 (app/build.gradle testOptions 확인)")
        val file = File(dirPath, "postprocess_cases.json")
        if (!file.isFile) throw AssertionError("공유 예문 없음: ${file.path} (내장 fallback 없음)")
        return JSONObject(file.readText(Charsets.UTF_8))
    }

    companion object {
        private const val SHARED_PROPERTY = "murdic.shared"
    }
}
