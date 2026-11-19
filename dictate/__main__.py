import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import time


def main():
    if sys.platform == "win32":
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("serve")
    wav = modes.add_parser("wav")
    wav.add_argument("path", type=Path)
    wav.add_argument("--json", action="store_true")
    wav.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--config-dir", type=Path)
    args = parser.parse_args()
    output = sys.stdout
    start = time.perf_counter()
    # Murmur/MLX can print progress while loading and decoding.
    with redirect_stdout(sys.stderr):
        from .backend import CONFIG_DIR, Pipeline, serve
        pipeline = Pipeline(args.config_dir or CONFIG_DIR)
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
