# murdic development notes

The Swift menu app sends a WAV path over JSON-lines to a resident Python worker. It imports Murmur's voice detector and Whisper wrapper and transcribes the complete recording on release. Both the GUI and CLI use `dictate/backend.py`. Tests for cleanup examples are in `tests/test_cleanup.py`.

## Test from the repository root

```sh
make sample
.venv/bin/python -m dictate wav build/sample.wav --json
make test
make benchmark
```

The benchmark checks cursor insertion in an isolated AppKit text view, restoration of multiple clipboard items, and preservation of a subsequent copy. The five-second fixture includes trailing silence. To repeat the English-only check with an empty settings directory:

```sh
mkdir -p build/en-test-settings
say -v Samantha -r 175 -o build/english.wav --data-format=LEI16@16000 'Please send the meeting notes to the design team tomorrow morning.'
.venv/bin/python -m dictate --config-dir build/en-test-settings wav build/english.wav --json
```

## Physical microphone check

Run `make sample build/microphone-tests`. The optional command below selects the named **physical input** and plays the Korean fixture through the current speakers. Use the exact microphone name from the app. The calling terminal needs microphone access. Put the speakers within earshot of the mic.

```sh
./build/microphone-tests --record 'MacBook Air 마이크' build/mic-builtin.wav
.venv/bin/python -m dictate wav build/mic-builtin.wav --json
```

The recorder reports its highest buffer RMS in dBFS and time to finish the WAV after stop. The app’s three-second settings test uses the same capture path without writing a file. At the end of a take, a maximum buffer RMS below −65 dBFS triggers the quiet-input notice.

On an M5 MacBook Air (2026-11-19), the built-in mic captured the speaker-played fixture as 6.186 seconds of 16 kHz mono PCM16, including time around playback. Peak buffer RMS was −30.15 dBFS and the WAV closed in 54 ms. Both sentences transcribed correctly. Five warm runs on that recorded WAV took 1,864–3,072 ms to insert into the benchmark text view (median 2,328 ms). A separate run on the standard five-second fixture took 483–1,375 ms (median 944 ms). These WAV-to-text-view measurements exclude microphone stop and external-app paste handling.

## Local signing

The default installation uses one path in the user's Applications directory and reuses a certificate named `murdic Local Code Signing` from the login keychain. Keep this signing identity across updates. Quit murdic before rebuilding. `make install` installs the app and `make run` opens it. The build prefers the checkout's `.venv/bin/python`. Override it with `make PYTHON=/absolute/path/to/python run` for a fresh build using another environment.

## Release DMG

`make dmg` builds the self-contained app and `build/release/murdic-<version>-arm64.dmg`. It bundles its own Python and packages, leaves the development build unchanged, and does not install anything into `~/Applications`. See [RELEASE.md](RELEASE.md) for signing, first-run steps, and the outside-bundle checks (`scripts/verify-release.py`).

## Optional LLM hook

Put an executable named `llm-cleanup` in `~/Library/Application Support/murdic/` and set `MURMUR_LLM_KEY` in the app's environment. The hook receives locally cleaned text on stdin and returns its edit on stdout. Missing credentials, an empty result, or a failure falls back to local cleanup. The timeout is four seconds. The [example](../examples/llm-cleanup) also reads `MURMUR_LLM_URL` and `MURMUR_LLM_MODEL`. Quit the menu app and run its installed executable from the configured shell to pass these variables to the worker.

## Preview the website

Run `python3 -m http.server 8000 --directory site` and open `http://localhost:8000/` or `http://localhost:8000/en/`. Both pages use the same demo assets. Netlify publishes `site/` directly.
