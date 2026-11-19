package com.murdic.mobile.ime

import android.util.Log
import java.io.File

/** IME 전용 whisper.cpp JNI (app/src/main/cpp). CPU 기능에 맞는 변형을 고른다. */
object WhisperNative {
    private const val TAG = "MurdicWhisper"
    @Volatile private var loaded = false

    @Synchronized
    fun ensureLoaded() {
        if (loaded) return
        val abi = android.os.Build.SUPPORTED_ABIS.firstOrNull() ?: ""
        val candidates = when (abi) {
            "arm64-v8a" -> {
                val cpu = runCatching { File("/proc/cpuinfo").readText() }.getOrDefault("")
                val fp16 = Regex("\\b(fphp|fp16)\\b").containsMatchIn(cpu)
                if (fp16) listOf("murdicwhisper_v8fp16", "murdicwhisper_v8") else listOf("murdicwhisper_v8")
            }
            "x86_64" -> listOf("murdicwhisper_x86_64")
            else -> listOf("murdicwhisper")
        }
        for (name in candidates) {
            try {
                System.loadLibrary(name)
                Log.i(TAG, "loaded $name")
                loaded = true
                return
            } catch (e: UnsatisfiedLinkError) {
                Log.w(TAG, "load $name failed", e)
            }
        }
        throw IllegalStateException("whisper 네이티브 라이브러리를 불러오지 못했습니다 ($abi)")
    }

    @JvmStatic external fun init(modelPath: String): Long
    @JvmStatic private external fun transcribe(handle: Long, audio: FloatArray, threads: Int, prompt: String?): ByteArray
    @JvmStatic external fun free(handle: Long)

    /** prompt = 도메인 힌트(initial_prompt), null이면 없음. 디코딩 설정은 cpp에 고정(Murmur와 같음). */
    fun transcribeText(handle: Long, audio: FloatArray, prompt: String?, threads: Int = 0): String =
        String(transcribe(handle, audio, threads, prompt), Charsets.UTF_8)
}
