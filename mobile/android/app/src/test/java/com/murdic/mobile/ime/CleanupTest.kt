package com.murdic.mobile.ime

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized
import java.io.File

/**
 * 공유 예문(mobile/shared 폴더의 JSON, 단일 원본)과 Cleanup 결과를 대조한다.
 * 쌍 하나가 테스트 하나다: clean(raw) == expected, clean(expected) == expected.
 * cleanup_cases.json이 없으면 실패한다. 내장 예문으로 대체하지 않는다.
 */
@RunWith(Parameterized::class)
class CleanupTest(
    private val raw: String,
    private val expected: String,
    private val origin: String,
) {
    @Test
    fun matchesSharedPair() {
        assertEquals("clean(raw) [$origin] raw=[$raw]", expected, Cleanup.clean(raw))
        assertEquals("clean(expected) [$origin] expected=[$expected]", expected, Cleanup.clean(expected))
    }

    companion object {
        private const val SHARED_PROPERTY = "murdic.shared"

        @JvmStatic
        @Parameterized.Parameters(name = "{index}: {0}")
        fun sharedPairs(): List<Array<Any>> {
            val dirPath = System.getProperty(SHARED_PROPERTY)
                ?: throw AssertionError("시스템 프로퍼티 $SHARED_PROPERTY 없음 (app/build.gradle testOptions 확인)")
            val dir = File(dirPath)
            val rows = mutableListOf<Array<Any>>()
            loadPairs(File(dir, "cleanup_cases.json"), true, rows)
            loadPairs(File(dir, "cleanup_extra_cases.json"), false, rows)
            if (rows.isEmpty()) throw AssertionError("공유 예문이 0쌍: $dirPath")
            return rows
        }

        private fun loadPairs(file: File, required: Boolean, rows: MutableList<Array<Any>>) {
            if (!file.isFile) {
                if (required) throw AssertionError("공유 예문 없음: ${file.path} (내장 fallback 없음)")
                return
            }
            val cases = JSONObject(file.readText(Charsets.UTF_8)).getJSONArray("cases")
            for (i in 0 until cases.length()) {
                val c = cases.getJSONObject(i)
                rows += arrayOf<Any>(c.getString("raw"), c.getString("expected"), "${file.name}#$i")
            }
        }
    }
}
