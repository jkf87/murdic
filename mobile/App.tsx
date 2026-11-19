/**
 * 머딕 모바일 — 누르고 말하면 내 폰에서 한국어를 받아 적고 정리한다.
 */
import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  ActivityIndicator,
  Linking,
  NativeModules,
  PermissionsAndroid,
  Platform,
  Pressable,
  ScrollView,
  Share,
  StatusBar,
  StyleSheet,
  Text,
  View,
  useColorScheme,
} from 'react-native';
import {SafeAreaProvider, SafeAreaView} from 'react-native-safe-area-context';
import Clipboard from '@react-native-clipboard/clipboard';
import {exists} from '@dr.pogodin/react-native-fs';
import {
  MODELS,
  download,
  isDownloaded,
  loadSettings,
  samplePath,
  saveSettings,
  type ModelId,
} from './src/models';
import {Recorder, SILENCE_LEVEL, speechLevel} from './src/recorder';
import {load, transcribeFile, transcribePcm, type Result} from './src/transcriber';

type Phase = 'idle' | 'loading' | 'recording' | 'transcribing';

// iOS 키보드 왕복(docs/ios-keyboard.md 3절). 네이티브 모듈은 IOS 작업자가 mobile/ios/에 만든다.
type SharedModule = {
  writeResult(req: string, text: string): Promise<void>;
  readPending(): Promise<{req: string; createdAt: number} | null>;
};
const shared: SharedModule | undefined = Platform.OS === 'ios' ? NativeModules.MurdicShared : undefined;
const PENDING_MAX_MS = 5 * 60 * 1000;

/** murdic://dictate?req=<id>&src=keyboard → req (RN의 URL.searchParams는 불완전해 직접 파싱). */
export function keyboardRequest(url: string | null): string | null {
  if (!url || !/^murdic:\/\/dictate(?:[/?#]|$)/.test(url)) {
    return null;
  }
  const query = url.split('?')[1]?.split('#')[0] ?? '';
  const params: Record<string, string> = {};
  for (const pair of query.split('&')) {
    const [k, v = ''] = pair.split('=');
    if (k) {
      params[decodeURIComponent(k)] = decodeURIComponent(v.replace(/\+/g, ' '));
    }
  }
  return params.src === 'keyboard' && params.req ? params.req : null;
}

const palette = (dark: boolean) => ({
  bg: dark ? '#111214' : '#f6f5f1',
  card: dark ? '#1c1d21' : '#ffffff',
  text: dark ? '#f2f2f2' : '#17181a',
  sub: dark ? '#a0a3a8' : '#5d6168',
  accent: '#127c74',
  rec: '#d64545',
  line: dark ? '#2c2e33' : '#e3e1da',
});

async function askMic(): Promise<boolean> {
  if (Platform.OS !== 'android') {
    return true;
  }
  const r = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.RECORD_AUDIO, {
    title: '마이크 권한',
    message: '말한 내용을 이 기기 안에서 받아 적으려면 마이크가 필요합니다. 녹음은 기기 밖으로 나가지 않습니다.',
    buttonPositive: '허용',
  });
  return r === PermissionsAndroid.RESULTS.GRANTED;
}

function App(): React.JSX.Element {
  const dark = useColorScheme() === 'dark';
  return (
    <SafeAreaProvider>
      <StatusBar barStyle={dark ? 'light-content' : 'dark-content'} />
      <Main dark={dark} />
    </SafeAreaProvider>
  );
}

function Main({dark}: {dark: boolean}) {
  const c = palette(dark);
  const recorder = useRef(new Recorder());
  const [model, setModel] = useState<ModelId | null>(null);
  const [have, setHave] = useState<Record<string, boolean>>({});
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [phase, setPhase] = useState<Phase>('idle');
  const [lvl, setLvl] = useState(0);
  const [result, setResult] = useState<(Result & {seconds?: number; loadMs?: number}) | null>(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [hasSample, setHasSample] = useState(false);
  // 키보드에서 열린 요청 id(iOS). 있으면 탭으로 시작/멈춤, 결과는 App Group에 기록.
  const [req, setReq] = useState<string | null>(null);
  const [delivered, setDelivered] = useState(false);
  const autoStart = useRef(false);

  useEffect(() => {
    const open = (url: string | null) => {
      const id = keyboardRequest(url);
      if (id) {
        setReq(id);
        setDelivered(false);
        autoStart.current = true;
      }
    };
    Linking.getInitialURL().then(async url => {
      open(url);
      if (!keyboardRequest(url) && shared) {
        const pending = await shared.readPending().catch(() => null);
        if (pending && Date.now() - pending.createdAt < PENDING_MAX_MS) {
          open(`murdic://dictate?req=${encodeURIComponent(pending.req)}&src=keyboard`);
        }
      }
    });
    const sub = Linking.addEventListener('url', e => open(e.url));
    return () => sub.remove();
  }, []);

  const refresh = useCallback(async () => {
    const entries = await Promise.all(MODELS.map(async m => [m.id, await isDownloaded(m.id)] as const));
    setHave(Object.fromEntries(entries));
    setHasSample(await exists(samplePath));
  }, []);

  useEffect(() => {
    loadSettings().then(s => setModel(s.model));
    refresh();
  }, [refresh]);

  const choose = async (id: ModelId) => {
    setModel(id);
    await saveSettings({model: id});
  };

  const fetchModel = async (id: ModelId) => {
    setError('');
    setProgress(p => ({...p, [id]: 0}));
    try {
      await download(id, f => setProgress(p => ({...p, [id]: f})));
      await choose(id);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setProgress(p => {
        const rest = {...p};
        delete rest[id];
        return rest;
      });
      refresh();
    }
  };

  const ready = model != null && have[model];

  const ensureModel = async (): Promise<number> => {
    setPhase('loading');
    return load(model!);
  };

  const startRec = async () => {
    if (!ready || phase !== 'idle') {
      return;
    }
    setError('');
    if (!(await askMic())) {
      setError('마이크 권한이 없어 녹음할 수 없습니다. 설정에서 허용해 주세요.');
      return;
    }
    try {
      await ensureModel();
      await recorder.current.start(setLvl);
      setPhase('recording');
    } catch (e: any) {
      setPhase('idle');
      setError(String(e?.message ?? e));
    }
  };

  const stopRec = async () => {
    if (phase !== 'recording') {
      return;
    }
    setPhase('transcribing');
    setLvl(0);
    try {
      const rec = await recorder.current.stop();
      if (rec.seconds < 0.3) {
        setError('너무 짧아요. 버튼을 누른 채로 말해 주세요.');
        return;
      }
      if (speechLevel(rec.pcm) < SILENCE_LEVEL) {
        setError('소리가 거의 들리지 않았어요. 마이크를 확인하고 다시 말해 주세요.');
        return;
      }
      const r = await transcribePcm(rec.pcm);
      setResult({...r, seconds: rec.seconds});
      setCopied(false);
      if (req && shared && r.text) {
        await shared.writeResult(req, r.text);
        setDelivered(true);
      }
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setPhase('idle');
    }
  };

  // 키보드에서 열리면 모델이 준비되는 대로 바로 녹음한다.
  useEffect(() => {
    if (autoStart.current && ready && phase === 'idle') {
      autoStart.current = false;
      startRec();
    }
  });

  const press = req
    ? {onPress: () => (phase === 'recording' ? stopRec() : startRec())}
    : {onPressIn: startRec, onPressOut: stopRec};

  // 개발·실측용: adb로 넣은 <filesDir>/sample.wav를 전사한다.
  const runSample = async () => {
    setError('');
    try {
      const loadMs = await ensureModel();
      setPhase('transcribing');
      const r = await transcribeFile(samplePath);
      setResult({...r, loadMs});
      console.log(`[murdic] sample model=${model} load=${loadMs}ms transcribe=${r.ms}ms text=${r.text}`);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setPhase('idle');
    }
  };

  const copy = () => {
    if (result?.text) {
      Clipboard.setString(result.text);
      setCopied(true);
    }
  };

  const btnLabel = {
    idle: ready ? (req ? '눌러서 말하기' : '누르고 말하기') : '먼저 모델을 받으세요',
    loading: '모델 여는 중…',
    recording: req ? '듣는 중 — 누르면 받아 적기' : '듣는 중 — 떼면 받아 적기',
    transcribing: '받아 적는 중…',
  }[phase];

  return (
    <SafeAreaView style={[s.fill, {backgroundColor: c.bg}]} edges={['top', 'bottom']}>
      <ScrollView contentContainerStyle={s.pad}>
        <Text style={[s.title, {color: c.text}]}>머딕</Text>
        <Text style={[s.sub, {color: c.sub}]}>누르고 말하면, 이 기기 안에서 한국어를 받아 적고 정리합니다.</Text>

        <Pressable
          testID="talk"
          accessibilityRole="button"
          accessibilityLabel={btnLabel}
          {...press}
          disabled={!ready}
          style={[
            s.talk,
            {backgroundColor: phase === 'recording' ? c.rec : ready ? c.accent : c.line},
          ]}>
          {phase === 'loading' || phase === 'transcribing' ? <ActivityIndicator color="#fff" /> : null}
          <Text style={s.talkText}>{btnLabel}</Text>
          {phase === 'recording' ? (
            <View style={s.meterTrack}>
              <View style={[s.meter, {width: `${Math.round(lvl * 100)}%`}]} />
            </View>
          ) : null}
        </Pressable>

        {req ? (
          <Text testID="keyboard-mode" style={[s.banner, {color: c.accent, borderColor: c.accent}]}>
            {delivered ? '원래 앱으로 돌아가면 입력됩니다' : '키보드에서 열었습니다 — 말한 뒤 원래 앱으로 돌아가세요'}
          </Text>
        ) : null}

        {error ? <Text style={[s.error, {color: c.rec}]}>{error}</Text> : null}

        {result ? (
          <View style={[s.card, {backgroundColor: c.card, borderColor: c.line}]}>
            <Text selectable testID="result" style={[s.result, {color: c.text}]}>
              {result.text || '(인식된 말이 없습니다)'}
            </Text>
            <Text style={[s.meta, {color: c.sub}]}>
              {result.seconds != null ? `음성 ${result.seconds.toFixed(1)}초 · ` : ''}
              {result.loadMs ? `모델 열기 ${result.loadMs} ms · ` : ''}전사 {result.ms} ms
              {result.raw !== result.text ? `\n원문: ${result.raw}` : ''}
            </Text>
            <View style={s.row}>
              <Pressable onPress={copy} style={[s.small, {borderColor: c.accent}]}>
                <Text style={{color: c.accent}}>{copied ? '복사됨' : '복사'}</Text>
              </Pressable>
              <Pressable
                onPress={() => result.text && Share.share({message: result.text})}
                style={[s.small, {borderColor: c.accent}]}>
                <Text style={{color: c.accent}}>공유</Text>
              </Pressable>
            </View>
          </View>
        ) : null}

        <Text style={[s.h2, {color: c.text}]}>모델</Text>
        {MODELS.map(m => {
          const p = progress[m.id];
          const on = model === m.id;
          return (
            <Pressable
              key={m.id}
              testID={`model-${m.id}`}
              onPress={() => (have[m.id] ? choose(m.id) : p == null && fetchModel(m.id))}
              style={[s.card, s.modelRow, {backgroundColor: c.card, borderColor: on ? c.accent : c.line}]}>
              <View style={s.fill}>
                <Text style={{color: c.text, fontWeight: on ? '700' : '500'}}>
                  {on ? '● ' : ''}
                  {m.label} · {Math.round(m.bytes / 1e6)} MB
                </Text>
                <Text style={{color: c.sub}}>{m.note}</Text>
              </View>
              <Text style={{color: have[m.id] ? c.accent : c.sub}}>
                {p != null ? `${Math.round(p * 100)}%` : have[m.id] ? (on ? '사용 중' : '선택') : '받기'}
              </Text>
            </Pressable>
          );
        })}

        {Platform.OS === 'android' ? (
          <>
            <Text style={[s.h2, {color: c.text}]}>어디서든 입력 — 머딕 키보드</Text>
            <Text style={{color: c.sub, marginBottom: 8}}>
              1) 아래 버튼으로 ‘머딕 받아쓰기’ 키보드를 켜세요. 2) 아무 입력란에서 키보드 전환 버튼으로 머딕을
              고르고, 마이크를 누른 채 말하세요. 키보드는 위에서 고른 모델을 씁니다.
            </Text>
            <View style={s.row}>
              <Pressable
                onPress={() => Linking.sendIntent('android.settings.INPUT_METHOD_SETTINGS')}
                style={[s.small, {borderColor: c.accent}]}>
                <Text style={{color: c.accent}}>키보드 설정 열기</Text>
              </Pressable>
              <Pressable onPress={askMic} style={[s.small, {borderColor: c.accent}]}>
                <Text style={{color: c.accent}}>마이크 권한 확인</Text>
              </Pressable>
            </View>
          </>
        ) : (
          <>
            <Text style={[s.h2, {color: c.text}]}>어디서든 입력 — 머딕 키보드</Text>
            <Text style={{color: c.sub, marginBottom: 8, lineHeight: 21}}>
              1) 첫 녹음 때 마이크 권한을 허용하세요.{'\n'}
              2) 설정 › 일반 › 키보드 › 키보드 › 새로운 키보드 추가 › 머딕.{'\n'}
              3) 머딕 › 전체 접근 허용을 켜세요. 키보드가 이 앱과 받아쓴 글을 주고받는 데 필요합니다. 머딕은
              네트워크를 쓰지 않고, 키 입력을 기록하거나 보내지 않습니다.{'\n'}
              4) 메모 앱에서 🌐로 머딕 키보드로 바꾸고 🎤를 눌러 시험하세요.
            </Text>
            <View style={s.row}>
              <Pressable onPress={() => Linking.openSettings()} style={[s.small, {borderColor: c.accent}]}>
                <Text style={{color: c.accent}}>설정 열기</Text>
              </Pressable>
            </View>
          </>
        )}

        {hasSample && ready ? (
          <Pressable testID="sample" onPress={runSample} style={[s.small, s.dev, {borderColor: c.line}]}>
            <Text style={{color: c.sub}}>개발용: sample.wav 전사 측정</Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  fill: {flex: 1},
  pad: {padding: 20, paddingBottom: 48},
  title: {fontSize: 32, fontWeight: '800'},
  sub: {fontSize: 15, marginTop: 4, marginBottom: 20, lineHeight: 21},
  talk: {
    borderRadius: 24,
    minHeight: 140,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
    gap: 10,
  },
  talkText: {color: '#fff', fontSize: 20, fontWeight: '700'},
  meterTrack: {width: '70%', height: 6, borderRadius: 3, backgroundColor: 'rgba(255,255,255,0.3)'},
  meter: {height: 6, borderRadius: 3, backgroundColor: '#fff'},
  error: {marginTop: 12, fontSize: 15},
  banner: {marginTop: 12, fontSize: 15, borderWidth: 1, borderRadius: 10, padding: 10},
  card: {borderWidth: 1, borderRadius: 14, padding: 14, marginTop: 12},
  result: {fontSize: 20, lineHeight: 28},
  meta: {fontSize: 12, marginTop: 8},
  row: {flexDirection: 'row', gap: 10, marginTop: 10, flexWrap: 'wrap'},
  small: {borderWidth: 1, borderRadius: 10, paddingVertical: 8, paddingHorizontal: 14},
  h2: {fontSize: 18, fontWeight: '700', marginTop: 28},
  modelRow: {flexDirection: 'row', alignItems: 'center', gap: 10},
  dev: {marginTop: 28, alignSelf: 'flex-start'},
});

export default App;
