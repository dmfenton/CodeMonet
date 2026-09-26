"""Subprocess entry point: execute a painting program and export the version.

    python -m code_monet.paintlib.runner --program P --out DIR --width W --height H --seed S

The program runs with a ready `cv` (paintlib.Canvas) and common modules in
scope. On success the version is in DIR (reveal.json is its record, which the
server reads) and a JSON summary with timings goes to stderr for people running
this by hand; stdout is the program's alone. On failure the traceback goes to
stderr and the exit code is 1.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from scipy import ndimage

from code_monet.paintlib import Canvas, cellular, fbm, mix, rgb, smoothstep, value_noise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--human", help="JSON file of human strokes in image pixels")
    args = parser.parse_args()

    human = json.loads(Path(args.human).read_text()) if args.human else []
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
    source = Path(args.program).read_text()
    t0 = time.monotonic()
    try:
        exec(compile(source, "studio/painting.py", "exec"), scope)
    except Exception:
        traceback.print_exc(limit=8)
        return 1
    t1 = time.monotonic()
    summary = cv.export(args.out)
    timings = {
        "paint_seconds": round(t1 - t0, 1),
        "export_seconds": round(time.monotonic() - t1, 1),
    }
    print(json.dumps({**summary, **timings}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
