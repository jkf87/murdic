// whisper.rn 컨텍스트를 하나만 들고 한국어로 전사한 뒤 cleanup 규칙을 적용한다.
import {Platform} from 'react-native';
import {initWhisper, type WhisperContext} from 'whisper.rn/index';
import {clean} from './cleanup';
import {modelPath, type ModelId} from './models';

export type Result = {raw: string; text: string; ms: number};

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

// greedy. beamSize를 넘기면 whisper.rn이 빔 서치로 바꿔 에뮬레이터에서 3~5배 느려졌다(1이어도).
const OPTIONS = {language: 'ko', maxThreads: 4} as const;

/** "[음악]"·"[박수]" 같은 whisper의 대괄호 비음성 표기를 지운다(Android Cleanup.stripAnnotations와 같음). */
export function stripAnnotations(raw: string): string {
  return raw.replace(/\[[^\]]*\]/g, ' ').replace(/\s+/g, ' ').trim();
}

function finish(raw: string, t0: number): Result {
  const text = stripAnnotations(raw);
  return {raw: text, text: clean(text), ms: Date.now() - t0};
}

export async function transcribePcm(pcm: ArrayBuffer): Promise<Result> {
  if (!current) {
    throw new Error('모델이 준비되지 않았습니다.');
  }
  const t0 = Date.now();
  const {promise} = current.ctx.transcribeData(pcm, OPTIONS);
  return finish((await promise).result, t0);
}

export async function transcribeFile(path: string): Promise<Result> {
  if (!current) {
    throw new Error('모델이 준비되지 않았습니다.');
  }
  const t0 = Date.now();
  const {promise} = current.ctx.transcribe(path, OPTIONS);
  return finish((await promise).result, t0);
}
