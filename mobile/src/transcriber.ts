// whisper.rn 컨텍스트를 하나만 들고 한국어로 전사한다. 순서는 맥판 backend.run과 같다(docs/STT_TUNING.md):
// 말소리 창 0개면 전사 안 함 → Whisper(Murmur 디코딩 설정 + 도메인 힌트) → 대괄호 표기 제거
// → filterTranscript(환각이면 '' = 입력 없음, 용어 교정 포함) → cleanup.
// Android IME(Kotlin MurdicImeService)도 같은 순서·같은 예문 JSON으로 검사한다.
import {Platform} from 'react-native';
import {initWhisper, type WhisperContext} from 'whisper.rn/index';
import {clean} from './cleanup';
import {modelPath, type ModelId, type Settings} from './models';
import {
  REAL_SPEECH_WINDOWS,
  STT_DECODE_OPTIONS,
  buildPrompt,
  countSpeechWindows,
  filterTranscript,
} from './postprocess';

export type Result = {
  /** whisper 원문(대괄호 표기만 지움) */
  raw: string;
  /** 입력할 글. 빈 문자열이면 아무것도 넣지 않는다(말소리 없음·환각). */
  text: string;
  ms: number;
  speechWindows: number;
  /** 말소리가 없어 전사하지 않았거나 환각으로 버렸으면 그 이유 */
  dropped?: 'silence' | 'hallucination';
};

let current: {id: ModelId; ctx: WhisperContext} | null = null;

export async function load(id: ModelId): Promise<number> {
  if (current?.id === id) {
    return 0;
  }
  await unload();
  const t0 = Date.now();
  const ctx = await initWhisper({
    filePath: modelPath(id),
    // GPU(Metal)는 iOS만 지원. Android는 CPU.
    useGpu: Platform.OS === 'ios',
  });
  current = {id, ctx};
  return Date.now() - t0;
}

export async function unload(): Promise<void> {
  const prev = current;
  current = null;
  await prev?.ctx.release();
}

/**
 * Murmur 디코딩 설정(language ko, temperature 0, temperatureInc 0 = 폴백 없음) + 힌트 프롬프트.
 * greedy 유지: beamSize를 넘기면(1이어도) whisper.rn이 빔 서치로 바꿔 2~4배 느려졌다.
 */
export function decodeOptions(settings: Pick<Settings, 'hintPreset' | 'properNouns'>) {
  const prompt = buildPrompt(settings.hintPreset, settings.properNouns);
  return {...STT_DECODE_OPTIONS, maxThreads: 4, ...(prompt ? {prompt} : {})};
}

/** "[음악]"·"[박수]" 같은 whisper의 대괄호 비음성 표기를 지운다(Android Cleanup.stripAnnotations와 같음). */
export function stripAnnotations(raw: string): string {
  return raw.replace(/\[[^\]]*\]/g, ' ').replace(/\s+/g, ' ').trim();
}

/** whisper 원문 → 입력할 글. 앱과 테스트가 같이 쓴다. */
export function postprocess(
  whisperText: string,
  speechWindows: number,
  settings: Pick<Settings, 'termCorrections'>,
): Pick<Result, 'raw' | 'text' | 'dropped'> {
  const raw = stripAnnotations(whisperText);
  const filtered = filterTranscript(raw, speechWindows, settings.termCorrections);
  if (!filtered) {
    return {raw, text: '', dropped: 'hallucination'};
  }
  return {raw, text: clean(filtered)};
}

function context(): WhisperContext {
  if (!current) {
    throw new Error('모델이 준비되지 않았습니다.');
  }
  return current.ctx;
}

export async function transcribePcm(pcm: ArrayBuffer, settings: Settings): Promise<Result> {
  const speechWindows = countSpeechWindows(pcm);
  if (speechWindows === 0) {
    // 맥판 `if speech_windows:` — 무음에 whisper가 "[음악]" 같은 환각을 내므로 아예 돌리지 않는다.
    return {raw: '', text: '', ms: 0, speechWindows, dropped: 'silence'};
  }
  const t0 = Date.now();
  const {promise} = context().transcribeData(pcm, decodeOptions(settings));
  const whisperText = (await promise).result;
  return {...postprocess(whisperText, speechWindows, settings), ms: Date.now() - t0, speechWindows};
}

/** 개발·실측용 파일 전사. 파일의 말소리 창은 세지 않고 말소리가 충분하다고 본다. */
export async function transcribeFile(path: string, settings: Settings): Promise<Result> {
  const t0 = Date.now();
  const {promise} = context().transcribe(path, decodeOptions(settings));
  const whisperText = (await promise).result;
  return {
    ...postprocess(whisperText, REAL_SPEECH_WINDOWS, settings),
    ms: Date.now() - t0,
    speechWindows: REAL_SPEECH_WINDOWS,
  };
}
