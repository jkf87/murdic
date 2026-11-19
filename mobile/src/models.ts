// 온디바이스 Whisper 모델 목록과 저장 위치.
// 앱(JS)과 Android IME(Kotlin)가 같은 파일을 읽는다:
//   <filesDir>/models/ggml-<id>.bin, <filesDir>/murdic-settings.json
import {
  DocumentDirectoryPath,
  downloadFile,
  exists,
  mkdir,
  moveFile,
  readFile,
  stat,
  unlink,
  writeFile,
} from '@dr.pogodin/react-native-fs';

export type ModelId = 'base-q5_1' | 'base' | 'small-q5_1' | 'small';

export type ModelInfo = {
  id: ModelId;
  label: string;
  bytes: number;
  note: string;
};

export const MODELS: ModelInfo[] = [
  {id: 'base-q5_1', label: 'base (양자화)', bytes: 59707625, note: '가장 가벼움 · 힌트를 켜면 힌트 문구를 되풀이할 수 있음'},
  {id: 'base', label: 'base', bytes: 147951465, note: '빠름 · 힌트를 켜면 힌트 문구를 되풀이할 수 있음'},
  {id: 'small-q5_1', label: 'small (양자화)', bytes: 190085487, note: 'small을 절반 메모리로, 대신 느림'},
  {id: 'small', label: 'small', bytes: 487601967, note: '권장: Murmur와 같은 모델, 가장 정확'},
];

// 품질 기준은 Murmur(whisper small, docs/STT_TUNING.md). 실측(docs/mobile.md): base 계열은 도메인 힌트를
// 켜면 힌트 문구를 그대로 읊었고, small은 정확했다. fp16 지원 CPU에선 small(f16)이 small-q5_1보다 빨랐다.
export const DEFAULT_MODEL: ModelId = 'small';

const MODEL_DIR = `${DocumentDirectoryPath}/models`;
const SETTINGS = `${DocumentDirectoryPath}/murdic-settings.json`;

export const modelPath = (id: ModelId) => `${MODEL_DIR}/ggml-${id}.bin`;
const modelUrl = (id: ModelId) =>
  `https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-${id}.bin`;

export async function isDownloaded(id: ModelId): Promise<boolean> {
  const path = modelPath(id);
  if (!(await exists(path))) {
    return false;
  }
  const info = MODELS.find(m => m.id === id)!;
  return Number((await stat(path)).size) === info.bytes;
}

export async function download(
  id: ModelId,
  onProgress: (fraction: number) => void,
): Promise<void> {
  await mkdir(MODEL_DIR);
  const part = `${modelPath(id)}.part`;
  if (await exists(part)) {
    await unlink(part);
  }
  const {promise} = downloadFile({
    fromUrl: modelUrl(id),
    toFile: part,
    progressInterval: 250,
    progress: r => onProgress(r.contentLength > 0 ? r.bytesWritten / r.contentLength : 0),
  });
  const res = await promise;
  if (res.statusCode !== 200) {
    await unlink(part).catch(() => {});
    throw new Error(`다운로드 실패 (HTTP ${res.statusCode})`);
  }
  if (await exists(modelPath(id))) {
    await unlink(modelPath(id));
  }
  await moveFile(part, modelPath(id));
  if (!(await isDownloaded(id))) {
    throw new Error('받은 파일 크기가 맞지 않습니다. 다시 받아 주세요.');
  }
}

export async function remove(id: ModelId): Promise<void> {
  if (await exists(modelPath(id))) {
    await unlink(modelPath(id));
  }
}

/**
 * 앱과 Android IME가 같이 읽는 설정(<filesDir>/murdic-settings.json). 필드 이름은 docs/tasks/REQUESTS.md 합의.
 * - hintPreset: postprocess.ts DOMAIN_HINT_PRESETS의 id (initial_prompt 앞부분)
 * - properNouns: 사용자 고유명사, 프롬프트 뒤에 ", "로 붙는다
 * - termCorrections: 사용자 용어 사전 [틀린 말, 바른 말], Murmur 기본 사전 뒤에 적용
 */
export type Settings = {
  model: ModelId;
  hintPreset: string;
  properNouns: string[];
  termCorrections: [string, string][];
};

export const DEFAULT_SETTINGS: Settings = {
  model: DEFAULT_MODEL,
  hintPreset: 'none',
  properNouns: [],
  termCorrections: [],
};

/** 파일 내용을 검사해 Settings로. 깨진 필드는 기본값. (테스트용 export) */
export function parseSettings(json: string): Settings {
  let parsed: any = {};
  try {
    parsed = JSON.parse(json) ?? {};
  } catch {}
  const strings = (v: unknown) =>
    Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
  return {
    model: MODELS.some(m => m.id === parsed.model) ? parsed.model : DEFAULT_MODEL,
    hintPreset: typeof parsed.hintPreset === 'string' ? parsed.hintPreset : 'none',
    properNouns: strings(parsed.properNouns),
    termCorrections: Array.isArray(parsed.termCorrections)
      ? parsed.termCorrections.filter(
          (x: unknown): x is [string, string] =>
            Array.isArray(x) && typeof x[0] === 'string' && x[0] !== '' && typeof x[1] === 'string',
        )
      : [],
  };
}

export async function loadSettings(): Promise<Settings> {
  try {
    return parseSettings(await readFile(SETTINGS, 'utf8'));
  } catch {
    return {...DEFAULT_SETTINGS};
  }
}

export async function saveSettings(s: Settings): Promise<void> {
  await writeFile(SETTINGS, JSON.stringify(s), 'utf8');
}

export const samplePath = `${DocumentDirectoryPath}/sample.wav`;
