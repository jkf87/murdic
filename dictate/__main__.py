import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("serve")
    wav = modes.add_parser("wav")
    wav.add_argument("path", type=Path)
    wav.add_argument("--json", action="store_true")
    wav.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--config-dir", type=Path)
    parser.add_argument("--refetch-model", action="store_true", help="discard the murdic model copy and download again")
    args = parser.parse_args()
    output = sys.stdout
    start = time.perf_counter()

    def progress(fraction):
        # The menu app reads these events; the CLI keeps stdout for its result only.
        if args.mode == "serve":
            print(json.dumps({"event": "progress", "fraction": round(fraction, 3)}), file=output, flush=True)

    # Murmur/MLX can print progress while loading and decoding.
    with redirect_stdout(sys.stderr):
        from .backend import CONFIG_DIR, Pipeline, serve
        from .model import ModelError
        try:
            pipeline = Pipeline(args.config_dir or CONFIG_DIR, progress, args.refetch_model)
        except ModelError as error:
            if args.mode != "serve":
                raise SystemExit(str(error))
            print(json.dumps({"event": "model_error", "message": str(error)}, ensure_ascii=False),
                  file=output, flush=True)
            return
        warmup = round((time.perf_counter() - start) * 1000, 1)
        if args.mode == "serve":
            serve(pipeline, output)
        else:
            for _ in range(args.repeat):
                result = pipeline.run(args.path)
                print(json.dumps(dict(warmup_ms=warmup, **result), ensure_ascii=False)
                      if args.json else result["text"], file=output, flush=True)


if __name__ == "__main__":
    main()
