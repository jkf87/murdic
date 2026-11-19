// IME에서 쓰는 최소 JNI: 모델 열기 / 16 kHz float PCM 전사 / 닫기.
#include <jni.h>
#include <android/log.h>
#include <string>
#include <thread>
#include <algorithm>
#include "whisper.h"

#define TAG "MurdicWhisper"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, TAG, __VA_ARGS__)

extern "C" JNIEXPORT jlong JNICALL
Java_com_murdic_mobile_ime_WhisperNative_init(JNIEnv *env, jclass, jstring jpath) {
    const char *path = env->GetStringUTFChars(jpath, nullptr);
    whisper_context_params cparams = whisper_context_default_params();
    cparams.use_gpu = false;
    whisper_context *ctx = whisper_init_from_file_with_params(path, cparams);
    LOGI("init %s -> %p", path, ctx);
    env->ReleaseStringUTFChars(jpath, path);
    return reinterpret_cast<jlong>(ctx);
}

// UTF-8 바이트로 돌려준다(NewStringUTF는 깨진 UTF-8·4바이트 문자에서 크래시할 수 있음).
extern "C" JNIEXPORT jbyteArray JNICALL
Java_com_murdic_mobile_ime_WhisperNative_transcribe(JNIEnv *env, jclass, jlong handle, jfloatArray jaudio,
                                                    jint threads) {
    auto *ctx = reinterpret_cast<whisper_context *>(handle);
    if (!ctx) {
        return env->NewByteArray(0);
    }
    jsize n = env->GetArrayLength(jaudio);
    jfloat *audio = env->GetFloatArrayElements(jaudio, nullptr);

    whisper_full_params p = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    p.language = "ko";
    p.translate = false;
    p.n_threads = threads > 0 ? threads : std::max(1, std::min(4, (int) std::thread::hardware_concurrency()));
    p.print_progress = false;
    p.print_realtime = false;
    p.print_special = false;
    p.print_timestamps = false;
    p.no_context = true;
    p.single_segment = false;
    p.suppress_blank = true;

    std::string out;
    if (whisper_full(ctx, p, audio, n) == 0) {
        int segments = whisper_full_n_segments(ctx);
        for (int i = 0; i < segments; i++) {
            out += whisper_full_get_segment_text(ctx, i);
        }
    }
    env->ReleaseFloatArrayElements(jaudio, audio, JNI_ABORT);
    jbyteArray bytes = env->NewByteArray((jsize) out.size());
    env->SetByteArrayRegion(bytes, 0, (jsize) out.size(), reinterpret_cast<const jbyte *>(out.data()));
    return bytes;
}

extern "C" JNIEXPORT void JNICALL
Java_com_murdic_mobile_ime_WhisperNative_free(JNIEnv *, jclass, jlong handle) {
    auto *ctx = reinterpret_cast<whisper_context *>(handle);
    if (ctx) {
        whisper_free(ctx);
    }
}
