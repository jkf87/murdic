package com.murdic.mobile.ime

import android.Manifest
import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.inputmethodservice.InputMethodService
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import android.view.HapticFeedbackConstants
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.TextView
import com.murdic.mobile.MainActivity
import com.murdic.mobile.R
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors

/**
 * 머딕 받아쓰기 키보드: 마이크를 누른 채 말하고 떼면 기기 안에서 전사 → 정리 → commitText.
 * 모델과 모델 선택은 앱이 받아 둔 <filesDir>/models, <filesDir>/murdic-settings.json 을 같이 쓴다.
 */
class MurdicImeService : InputMethodService() {
    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()
    private var handle = 0L
    private var handleModel: String? = null
    private var recorder: PcmRecorder? = null
    private var status: TextView? = null
    private var mic: Button? = null
    private var busy = false
    private var debugReceiver: BroadcastReceiver? = null

    override fun onCreate() {
        super.onCreate()
        if (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0) registerDebugHook()
    }

    @SuppressLint("ClickableViewAccessibility", "InflateParams")
    override fun onCreateInputView(): View {
        val v = layoutInflater.inflate(R.layout.ime_view, null)
        status = v.findViewById(R.id.status)
        mic = v.findViewById<Button>(R.id.mic).apply {
            setOnTouchListener { view, e ->
                when (e.actionMasked) {
                    MotionEvent.ACTION_DOWN -> { view.isPressed = true; startTalk(view) }
                    MotionEvent.ACTION_UP -> { view.isPressed = false; stopTalk(cancel = false) }
                    MotionEvent.ACTION_CANCEL -> { view.isPressed = false; stopTalk(cancel = true) }
                }
                true
            }
        }
        v.findViewById<Button>(R.id.switchIme).setOnClickListener {
            if (Build.VERSION.SDK_INT >= 28) switchToNextInputMethod(false)
        }
        v.findViewById<Button>(R.id.backspace).setOnClickListener {
            currentInputConnection?.let { ic ->
                if (ic.getSelectedText(0).isNullOrEmpty()) ic.deleteSurroundingText(1, 0) else ic.commitText("", 1)
            }
        }
        v.findViewById<Button>(R.id.enter).setOnClickListener { sendEnter() }
        status?.setOnClickListener { openApp() }
        return v
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        showIdle()
    }

    private fun showIdle() {
        val model = selectedModel()
        status?.text = when {
            !hasMicPermission() -> "마이크 권한이 필요합니다 — 여기를 눌러 머딕 앱에서 허용하세요"
            !File(modelPath(model)).exists() -> "모델이 없습니다 — 여기를 눌러 머딕 앱에서 모델을 받으세요"
            else -> "마이크를 누른 채 말하세요 · $model"
        }
    }

    private fun hasMicPermission() =
        checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun startTalk(view: View) {
        if (busy) return
        if (!hasMicPermission() || !File(modelPath(selectedModel())).exists()) {
            showIdle()
            return
        }
        view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
        warmUp()
        try {
            lateinit var rec: PcmRecorder
            // 뗀 뒤 큐에 남은 레벨 갱신이 결과 문구를 덮지 않게, 지금 녹음 중인 recorder일 때만 그린다.
            rec = PcmRecorder { lvl -> main.post { if (recorder === rec) status?.text = "듣는 중 " + bar(lvl) } }
            recorder = rec.also { it.start() }
            status?.text = "듣는 중…"
        } catch (e: Exception) {
            recorder = null
            status?.text = e.message ?: "마이크를 열지 못했습니다"
        }
    }

    private fun stopTalk(cancel: Boolean) {
        val r = recorder ?: return
        recorder = null
        if (cancel) {
            r.cancel(); showIdle(); return
        }
        val audio = r.stop()
        if (audio.size < PcmRecorder.RATE * 3 / 10) {
            status?.text = "너무 짧아요. 누른 채로 말해 주세요."
            return
        }
        transcribeAndCommit(audio, "음성 %.1f초".format(audio.size / PcmRecorder.RATE.toFloat()))
    }

    /**
     * 맥판 backend.run과 같은 순서(docs/STT_TUNING.md): 말소리 창 0개면 전사하지 않음 → Whisper(힌트 프롬프트)
     * → 대괄호 표기 제거 → filterTranscript(환각이면 '' = 입력 없음, 말소리 창 3개 이상이면 문구 규칙만 예외)
     * → 용어 교정(filterTranscript 안) → cleanup → commitText.
     */
    private fun transcribeAndCommit(audio: FloatArray, label: String) {
        val windows = Postprocess.countSpeechWindows(audio)
        Log.i(TAG, "recorded $label speechWindows=$windows")
        if (windows == 0) {
            status?.text = "소리가 거의 들리지 않았어요. 마이크를 확인하고 다시 말해 주세요."
            return
        }
        busy = true
        mic?.isEnabled = false
        status?.text = "받아 적는 중…"
        worker.execute {
            val result = runCatching {
                val settings = readSettings()
                val loadMs = ensureModel()
                val t0 = SystemClock.elapsedRealtime()
                val prompt = Postprocess.buildPrompt(settings.hintPreset, settings.properNouns)
                val raw = Cleanup.stripAnnotations(WhisperNative.transcribeText(handle, audio, prompt))
                val filtered = Postprocess.filterTranscript(raw, windows, settings.termCorrections)
                val text = if (filtered.isEmpty()) "" else Cleanup.clean(filtered)
                val ms = SystemClock.elapsedRealtime() - t0
                Log.i(TAG, "transcribed model=$handleModel load=${loadMs}ms transcribe=${ms}ms $label windows=$windows prompt=$prompt raw=$raw text=$text")
                Triple(text, ms, raw)
            }
            main.post {
                busy = false
                mic?.isEnabled = true
                result.onSuccess { (text, ms, raw) ->
                    if (text.isEmpty()) {
                        status?.text = if (raw.isEmpty()) "인식된 말이 없습니다" else "잡음으로 보고 넣지 않았어요 · 다시 말해 주세요"
                    } else {
                        commit(text)
                        status?.text = "입력함 · $label · ${ms} ms"
                    }
                }.onFailure {
                    Log.e(TAG, "transcribe failed", it)
                    status?.text = "전사 실패: ${it.message}"
                }
            }
        }
    }

    private fun commit(text: String) {
        val ic = currentInputConnection ?: return
        val before = ic.getTextBeforeCursor(1, 0)?.toString() ?: ""
        val spaced = if (before.isNotEmpty() && !before.last().isWhitespace()) " $text" else text
        ic.commitText(spaced, 1)
    }

    private fun sendEnter() {
        val ic = currentInputConnection ?: return
        val info = currentInputEditorInfo
        val action = info?.imeOptions?.and(EditorInfo.IME_MASK_ACTION) ?: EditorInfo.IME_ACTION_NONE
        val multiLine = info != null && (info.inputType and android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE) != 0
        val noEnterAction = info != null && (info.imeOptions and EditorInfo.IME_FLAG_NO_ENTER_ACTION) != 0
        if (!multiLine && !noEnterAction && action != EditorInfo.IME_ACTION_NONE && action != EditorInfo.IME_ACTION_UNSPECIFIED) {
            ic.performEditorAction(action)
        } else {
            ic.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER))
            ic.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_ENTER))
        }
    }

    /** 누르는 순간 모델을 미리 연다(떼기 전 로드를 겹치기). */
    private fun warmUp() = worker.execute { runCatching { ensureModel() } }

    /** 워커 스레드에서만 호출. 연 데 걸린 ms(이미 열려 있으면 0). */
    private fun ensureModel(): Long {
        val model = selectedModel()
        if (handle != 0L && handleModel == model) return 0
        WhisperNative.ensureLoaded()
        if (handle != 0L) { WhisperNative.free(handle); handle = 0 }
        val t0 = SystemClock.elapsedRealtime()
        val h = WhisperNative.init(modelPath(model))
        check(h != 0L) { "모델을 열지 못했습니다 ($model)" }
        handle = h
        handleModel = model
        return SystemClock.elapsedRealtime() - t0
    }

    /** 앱(src/models.ts Settings)과 같은 파일·같은 필드. 없거나 깨졌으면 기본값. */
    private data class Settings(
        val model: String = DEFAULT_MODEL,
        val hintPreset: String = "none",
        val properNouns: List<String> = emptyList(),
        val termCorrections: List<Pair<String, String>> = emptyList(),
    )

    private fun readSettings(): Settings = runCatching {
        val j = JSONObject(File(filesDir, "murdic-settings.json").readText())
        val nouns = j.optJSONArray("properNouns")
        val terms = j.optJSONArray("termCorrections")
        Settings(
            model = j.optString("model", DEFAULT_MODEL),
            hintPreset = j.optString("hintPreset", "none"),
            properNouns = List(nouns?.length() ?: 0) { nouns!!.optString(it) },
            termCorrections = List(terms?.length() ?: 0) {
                val pair = terms!!.optJSONArray(it)
                (pair?.optString(0) ?: "") to (pair?.optString(1) ?: "")
            }.filter { it.first.isNotEmpty() },
        )
    }.getOrDefault(Settings())

    private fun selectedModel(): String = readSettings().model

    private fun modelPath(model: String) = File(filesDir, "models/ggml-$model.bin").absolutePath

    private fun openApp() {
        startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    /** 디버그 빌드 전용: 에뮬레이터에서 말 대신 WAV 파일로 같은 입력 경로를 검증한다. */
    private fun registerDebugHook() {
        val r = object : BroadcastReceiver() {
            override fun onReceive(c: Context, i: Intent) {
                val path = i.getStringExtra("path") ?: File(filesDir, "sample.wav").absolutePath
                val audio = runCatching { PcmRecorder.readWav(File(path)) }
                    .getOrElse { status?.text = "WAV 읽기 실패: ${it.message}"; return }
                transcribeAndCommit(audio, "파일 %.1f초".format(audio.size / PcmRecorder.RATE.toFloat()))
            }
        }
        val filter = IntentFilter(DEBUG_ACTION)
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(r, filter, RECEIVER_EXPORTED) else registerReceiver(r, filter)
        debugReceiver = r
    }

    override fun onDestroy() {
        recorder?.cancel()
        debugReceiver?.let { unregisterReceiver(it) }
        worker.execute { if (handle != 0L) WhisperNative.free(handle); handle = 0 }
        worker.shutdown()
        super.onDestroy()
    }

    private fun bar(v: Float) = "▮".repeat((v * 10).toInt().coerceIn(1, 10))

    companion object {
        private const val TAG = "MurdicIme"
        const val DEFAULT_MODEL = "small" // src/models.ts DEFAULT_MODEL과 같게(Murmur 기준 모델)
        const val DEBUG_ACTION = "com.murdic.mobile.DEBUG_TRANSCRIBE_FILE"
    }
}
