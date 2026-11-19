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
  {id: 'base-q5_1', label: 'base (양자화)', bytes: 59707625, note: '가장 가볍고 빠름'},
  {id: 'base', label: 'base', bytes: 147951465, note: '보급형 기기'},
  {id: 'small-q5_1', label: 'small (양자화)', bytes: 190085487, note: '권장: 정확도와 속도 균형'},
  {id: 'small', label: 'small', bytes: 487601967, note: '가장 정확, 메모리 많이 씀'},
];

export const DEFAULT_MODEL: ModelId = 'small-q5_1';

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

export type Settings = {model: ModelId};

export async function loadSettings(): Promise<Settings> {
  try {
    const parsed = JSON.parse(await readFile(SETTINGS, 'utf8'));
    if (MODELS.some(m => m.id === parsed.model)) {
      return {model: parsed.model};
    }
  } catch {}
  return {model: DEFAULT_MODEL};
}

export async function saveSettings(s: Settings): Promise<void> {
  await writeFile(SETTINGS, JSON.stringify(s), 'utf8');
}

export const samplePath = `${DocumentDirectoryPath}/sample.wav`;
