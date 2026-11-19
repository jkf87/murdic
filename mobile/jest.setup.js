// 네이티브 모듈 목(jest는 기기 없이 JS만 돈다).
jest.mock('whisper.rn/index', () => ({
  initWhisper: jest.fn(async () => ({
    transcribeData: () => ({stop: async () => {}, promise: Promise.resolve({result: ' 음, 내일 만나요'})}),
    transcribe: () => ({stop: async () => {}, promise: Promise.resolve({result: ' 음, 내일 만나요'})}),
    release: async () => {},
  })),
}));
jest.mock('@dr.pogodin/react-native-fs', () => ({
  DocumentDirectoryPath: '/data/files',
  downloadFile: jest.fn(),
  exists: jest.fn(async () => false),
  mkdir: jest.fn(async () => {}),
  moveFile: jest.fn(async () => {}),
  readFile: jest.fn(async () => {
    throw new Error('none');
  }),
  stat: jest.fn(async () => ({size: 0})),
  unlink: jest.fn(async () => {}),
  writeFile: jest.fn(async () => {}),
}));
jest.mock('@fugood/react-native-audio-pcm-stream', () => ({
  __esModule: true,
  default: {init: jest.fn(), start: jest.fn(), stop: jest.fn(async () => ''), on: jest.fn(() => ({remove() {}}))},
}));
jest.mock('@react-native-clipboard/clipboard', () => ({__esModule: true, default: {setString: jest.fn()}}));
