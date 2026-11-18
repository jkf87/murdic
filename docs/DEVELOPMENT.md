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

## Local signing

The default installation uses one path in the user's Applications directory and reuses a certificate named `murdic Local Code Signing` from the login keychain. Keep this signing identity across updates. Quit murdic before rebuilding. `make install` installs the app and `make run` opens it. The build prefers the checkout's `.venv/bin/python`. Override it with `make PYTHON=/absolute/path/to/python run` for a fresh build using another environment.

## Optional LLM hook

Put an executable named `llm-cleanup` in `~/Library/Application Support/murdic/` and set `MURMUR_LLM_KEY` in the app's environment. The hook receives locally cleaned text on stdin and returns its edit on stdout. Missing credentials, an empty result, or a failure falls back to local cleanup. The timeout is four seconds. The [example](../examples/llm-cleanup) also reads `MURMUR_LLM_URL` and `MURMUR_LLM_MODEL`. Quit the menu app and run its installed executable from the configured shell to pass these variables to the worker.

## Preview the website

Run `python3 -m http.server 8000 --directory site` and open `http://localhost:8000/` or `http://localhost:8000/en/`. Both pages use the same demo assets. Netlify publishes `site/` directly.
