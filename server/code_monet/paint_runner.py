"""Subprocess entry point: execute a painting program and export the version.

    python -I -m code_monet.paint_runner --program P --out DIR --width W --height H --seed S \
        [--human FILE] [--previous VERSION_DIR]

The program runs with a ready `cv` (paintlib.Canvas) and common modules in
scope; with --previous it paints over that version's canvas. While it runs, its
performance streams to DIR/performance.bin. On success the version is in DIR
(reveal.json is its record, which the server reads) and a JSON summary with timings goes to stderr for people running
this by hand; stdout is the program's alone. On failure the traceback goes to
stderr and the exit code is 1.

On Linux the process confines itself (code_monet.sandbox) before importing
anything else or running the program: it can read Python and its libraries,
write only the output and working directories, open no network sockets, start
no processes, and not signal its parent. Elsewhere (macOS development) it runs
unconfined.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import random
import sys
import time
import traceback
from pathlib import Path

from code_monet import sandbox


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--human", help="JSON file of human strokes in image pixels")
    parser.add_argument(
        "--previous", help="the last version's directory: this run paints over its canvas"
    )
    args = parser.parse_args()

    human = json.loads(Path(args.human).read_text()) if args.human else []
    source = Path(args.program).read_text()
    # Read before confinement: the previous version lies outside what the run may read.
    previous = (Path(args.previous) / "canvas.npz").read_bytes() if args.previous else None
    if sandbox.available():
        sandbox.confine(sandbox.python_policy(args.out, os.getcwd()))

    import numpy as np
    from scipy import ndimage

    from code_monet.paintlib import Canvas, cellular, fbm, mix, rgb, smoothstep, value_noise

    cv = Canvas(args.width, args.height, seed=args.seed)
    scope = {
        "__name__": "__painting__",
        "cv": cv,
        "W": cv.W,
        "H": cv.H,
        "np": np,
        "ndi": ndimage,
        "math": math,
        "random": random,
        "rgb": rgb,
        "fbm": fbm,
        "mix": mix,
        "smoothstep": smoothstep,
        "value_noise": value_noise,
        "cellular": cellular,
        "HUMAN_STROKES": human,
    }
    random.seed(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "performance.bin").open("wb") as stream:
        if previous is not None:
            cv.load_state(io.BytesIO(previous))
        cv.stream_to(stream)
        t0 = time.monotonic()
        try:
            exec(compile(source, "studio/painting.py", "exec"), scope)
        except Exception:
            cv.abort_stream()
            traceback.print_exc(limit=8)
            return 1
        t1 = time.monotonic()
        summary = cv.export(out)
    perf = cv._performance.stats
    timings = {
        "paint_seconds": round(t1 - t0, 1),
        "export_seconds": round(time.monotonic() - t1, 1),
        "performance": {
            "bytes": perf.bytes,
            "chunks": perf.chunks,
            "patches": perf.patches,
            "pixels": perf.pixels,
            "hand_ms": round(perf.ms),
            "encode_seconds": round(perf.encode_seconds, 2),
            "diff_seconds": round(perf.diff_seconds, 2),
        },
    }
    print(json.dumps({**summary, **timings}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
