package com.murdic.mobile.ime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.sin

/** __tests__/audio.test.ts와 같은 예: 앱과 IME가 같은 기준으로 무음·주석을 처리하는지. */
class ImeAudioTest {
    private fun tone(amp: Float) = FloatArray(PcmRecorder.RATE) { (sin(it / 8.0) * amp).toFloat() }

    @Test fun silenceGate() {
        assertEquals(0f, PcmRecorder.speechLevel(FloatArray(PcmRecorder.RATE)))
        assertTrue(PcmRecorder.speechLevel(tone(0.005f)) < PcmRecorder.SILENCE_LEVEL)
        assertTrue(PcmRecorder.speechLevel(tone(0.1f)) > PcmRecorder.SILENCE_LEVEL)
    }

    @Test fun stripAnnotations() {
        assertEquals("", Cleanup.stripAnnotations(" [음악]"))
        assertEquals("오늘 만나요", Cleanup.stripAnnotations("[박수] 오늘  만나요 [웃음]"))
        assertEquals("API (v2) 응답", Cleanup.stripAnnotations("API (v2) 응답"))
    }
}
