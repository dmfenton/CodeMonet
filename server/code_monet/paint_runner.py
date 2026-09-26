"""Subprocess entry point: execute a painting program and export the version.

    python -I -m code_monet.paint_runner --program P --out DIR --width W --height H --seed S

The program runs with a ready `cv` (paintlib.Canvas) and common modules in
scope. On success the last stdout line is a JSON summary; on failure the
traceback goes to stderr and the exit code is 1.

On Linux the process confines itself (code_monet.sandbox) before importing
anything else or running the program: it can read Python and its libraries,
write only the output and working directories, open no network sockets, start
no processes, and not signal its parent. Elsewhere (macOS development) it runs
unconfined.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
import traceback
from pathlib import Path

from code_monet import sandbox


def paint_policy(out_dir: str, work_dir: str) -> sandbox.Policy:
    """Read Python and shared libraries; write the version's output and scratch dirs."""
    python = {sys.prefix, sys.base_prefix, sys.exec_prefix, *filter(os.path.isdir, sys.path)}
    return sandbox.Policy(
        read=(*sorted(python), "/lib", "/usr/lib"),
        write=(out_dir, work_dir),
        network=False,
        subprocesses=False,
        protected_pids=(1, os.getppid()),
    )


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
    source = Path(args.program).read_text()
    if sandbox.available():
        sandbox.confine(paint_policy(args.out, os.getcwd()))

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
    t0 = time.monotonic()
    try:
        exec(compile(source, "studio/painting.py", "exec"), scope)
    except Exception:
        traceback.print_exc(limit=8)
        return 1
    t1 = time.monotonic()
    summary = cv.export(args.out)
    summary["paint_seconds"] = round(t1 - t0, 1)
    summary["export_seconds"] = round(time.monotonic() - t1, 1)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
