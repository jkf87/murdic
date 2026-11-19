/* eslint-disable no-bitwise -- base64·PCM 디코딩 */
// 누르는 동안 16 kHz 모노 16bit PCM을 모아 ArrayBuffer로 돌려준다.
import AudioRecord from '@fugood/react-native-audio-pcm-stream';

const SAMPLE_RATE = 16000;
const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
const LOOKUP = new Uint8Array(256);
for (let i = 0; i < B64.length; i++) {
  LOOKUP[B64.charCodeAt(i)] = i;
}

export function base64ToBytes(b64: string): Uint8Array {
  const clean = b64.replace(/[^A-Za-z0-9+/]/g, '');
  const out = new Uint8Array(Math.floor((clean.length * 3) / 4));
  let o = 0;
  for (let i = 0; i < clean.length; i += 4) {
    const a = LOOKUP[clean.charCodeAt(i)];
    const b = LOOKUP[clean.charCodeAt(i + 1)];
    const c = LOOKUP[clean.charCodeAt(i + 2)];
    const d = LOOKUP[clean.charCodeAt(i + 3)];
    out[o++] = (a << 2) | (b >> 4);
    if (i + 2 < clean.length) {
      out[o++] = ((b & 15) << 4) | (c >> 2);
    }
    if (i + 3 < clean.length) {
      out[o++] = ((c & 3) << 6) | d;
    }
  }
  return out.subarray(0, o);
}

/** 16bit PCM 조각의 RMS 레벨(0~1). */
function level(bytes: Uint8Array): number {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let sum = 0;
  const n = Math.floor(bytes.byteLength / 2);
  for (let i = 0; i < n; i++) {
    const s = view.getInt16(i * 2, true) / 32768;
    sum += s * s;
  }
  return n ? Math.min(1, Math.sqrt(sum / n) * 4) : 0;
}

/** 이보다 조용하면 말이 없다고 본다. Android PcmRecorder.SILENCE_LEVEL과 같은 값. */
export const SILENCE_LEVEL = 0.01;

/** 0.1초 창 RMS의 최댓값(0~1, 증폭 없음). */
export function speechLevel(pcm: ArrayBuffer): number {
  const view = new DataView(pcm);
  const n = Math.floor(pcm.byteLength / 2);
  const win = SAMPLE_RATE / 10;
  let best = 0;
  for (let i = 0; i < n; i += win) {
    const end = Math.min(n, i + win);
    let sum = 0;
    for (let j = i; j < end; j++) {
      const s = view.getInt16(j * 2, true) / 32768;
      sum += s * s;
    }
    best = Math.max(best, Math.sqrt(sum / (end - i)));
  }
  return best;
}

export type Recording = {pcm: ArrayBuffer; seconds: number};

export class Recorder {
  private chunks: Uint8Array[] = [];
  private sub?: {remove: () => void};
  private ready = false;

  async start(onLevel: (v: number) => void): Promise<void> {
    if (!this.ready) {
      AudioRecord.init({
        sampleRate: SAMPLE_RATE,
        channels: 1,
        bitsPerSample: 16,
        audioSource: 6, // VOICE_RECOGNITION
        bufferSize: 4096,
        wavFile: '',
      });
      this.ready = true;
    }
    this.chunks = [];
    this.sub = AudioRecord.on('data', (data: string) => {
      const bytes = base64ToBytes(data);
      this.chunks.push(bytes);
      onLevel(level(bytes));
    }) as unknown as {remove: () => void};
    AudioRecord.start();
  }

  async stop(): Promise<Recording> {
    await AudioRecord.stop();
    this.sub?.remove();
    const total = this.chunks.reduce((n, c) => n + c.byteLength, 0);
    const pcm = new Uint8Array(total);
    let o = 0;
    for (const c of this.chunks) {
      pcm.set(c, o);
      o += c.byteLength;
    }
    this.chunks = [];
    return {pcm: pcm.buffer, seconds: total / 2 / SAMPLE_RATE};
  }
}
