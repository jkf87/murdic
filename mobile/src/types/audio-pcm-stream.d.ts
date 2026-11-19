// 패키지의 index.d.ts가 옛 이름(react-native-live-audio-stream)으로 선언돼 있어 바로잡는다.
declare module '@fugood/react-native-audio-pcm-stream' {
  export interface Options {
    sampleRate: number;
    channels: 1 | 2;
    bitsPerSample: 8 | 16;
    /** Android MediaRecorder.AudioSource, 6 = VOICE_RECOGNITION */
    audioSource?: number;
    wavFile: string;
    bufferSize?: number;
  }
  const AudioRecord: {
    init(options: Options): void;
    start(): void;
    stop(): Promise<string>;
    on(event: 'data', callback: (base64Pcm: string) => void): {remove(): void};
  };
  export default AudioRecord;
}
