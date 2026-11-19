package com.murdic.mobile.ime

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.sqrt

/** 누르는 동안 16 kHz 모노 PCM을 모은다. 권한 확인은 호출하는 쪽에서. */
class PcmRecorder(private val onLevel: (Float) -> Unit) {
    private var record: AudioRecord? = null
    private var thread: Thread? = null
    @Volatile private var running = false
    private val buffer = ByteArrayOutputStream()

    @SuppressLint("MissingPermission")
    fun start() {
        val min = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val size = maxOf(min, RATE / 5 * 2)
        val r = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION, RATE,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, size,
        )
        check(r.state == AudioRecord.STATE_INITIALIZED) { "마이크를 열지 못했습니다" }
        buffer.reset()
        record = r
        running = true
        r.startRecording()
        thread = Thread {
            val chunk = ByteArray(size)
            while (running) {
                val n = r.read(chunk, 0, chunk.size)
                if (n > 0) {
                    synchronized(buffer) { buffer.write(chunk, 0, n) }
                    onLevel(rms(chunk, n))
                }
            }
        }.apply { name = "murdic-mic"; start() }
    }

    /** 녹음을 멈추고 whisper 입력(float, -1..1)을 돌려준다. */
    fun stop(): FloatArray {
        running = false
        thread?.join(500)
        record?.run { runCatching { stop() }; release() }
        record = null
        val bytes = synchronized(buffer) { buffer.toByteArray() }
        return pcm16ToFloat(bytes, 0, bytes.size)
    }

    fun cancel() {
        stop()
        buffer.reset()
    }

    companion object {
        const val RATE = 16000
        fun pcm16ToFloat(bytes: ByteArray, offset: Int, length: Int): FloatArray {
            val bb = ByteBuffer.wrap(bytes, offset, length).order(ByteOrder.LITTLE_ENDIAN)
            val out = FloatArray(length / 2)
            for (i in out.indices) out[i] = bb.short / 32768f
            return out
        }

        /** 16 kHz 모노 16bit PCM WAV 읽기(개발용 파일 전사). */
        fun readWav(file: File): FloatArray {
            val b = file.readBytes()
            require(String(b, 0, 4) == "RIFF" && String(b, 8, 4) == "WAVE") { "WAV가 아닙니다" }
            var p = 12
            var fmtOk = false
            while (p + 8 <= b.size) {
                val id = String(b, p, 4)
                val len = ByteBuffer.wrap(b, p + 4, 4).order(ByteOrder.LITTLE_ENDIAN).int
                if (id == "fmt ") {
                    val f = ByteBuffer.wrap(b, p + 8, 16).order(ByteOrder.LITTLE_ENDIAN)
                    val format = f.short.toInt(); val ch = f.short.toInt(); val rate = f.int
                    f.int; f.short; val bits = f.short.toInt()
                    require(format == 1 && ch == 1 && rate == RATE && bits == 16) { "16 kHz 모노 16bit PCM만 지원" }
                    fmtOk = true
                } else if (id == "data" && fmtOk) {
                    return pcm16ToFloat(b, p + 8, minOf(len, b.size - p - 8))
                }
                p += 8 + len + (len and 1)
            }
            error("data 청크가 없습니다")
        }

        private fun rms(b: ByteArray, n: Int): Float {
            var sum = 0.0
            var i = 0
            while (i + 1 < n) {
                val s = ((b[i + 1].toInt() shl 8) or (b[i].toInt() and 0xff)).toShort() / 32768.0
                sum += s * s
                i += 2
            }
            return minOf(1f, (sqrt(sum / maxOf(1, n / 2)) * 4).toFloat())
        }
    }
}
