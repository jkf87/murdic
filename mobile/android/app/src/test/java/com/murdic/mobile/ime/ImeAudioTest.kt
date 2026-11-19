package com.murdic.mobile.ime

import org.junit.Assert.assertEquals
import org.junit.Test

/** __tests__/audio.test.ts와 같은 예. (무음 판정은 Murmur 말소리 창으로 바꿔 PostprocessTest가 검사) */
class ImeAudioTest {
    @Test fun stripAnnotations() {
        assertEquals("", Cleanup.stripAnnotations(" [음악]"))
        assertEquals("오늘 만나요", Cleanup.stripAnnotations("[박수] 오늘  만나요 [웃음]"))
        assertEquals("API (v2) 응답", Cleanup.stripAnnotations("API (v2) 응답"))
    }
}
