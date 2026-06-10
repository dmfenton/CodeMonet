#!/usr/bin/env python3
"""Render a generate_svg-style study to PNG for visual iteration.

Runs sandbox code (same environment the agent's generate_svg tool uses),
renders the resulting paths with the paint-mode pipeline, and saves a PNG.

Usage (from server/ so uv picks up dependencies):
    uv run python ../scripts/render-study.py ../studies/monet_poplars.py
    uv run python ../scripts/render-study.py ../studies/monet_poplars.py -o out.png
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path as FilePath

sys.path.insert(0, str(FilePath(__file__).resolve().parent.parent / "server"))

from code_monet.rendering import RenderOptions, render_strokes  # noqa: E402
from code_monet.tools.python_sandbox import run_python_code  # noqa: E402
from code_monet.types import DrawingStyleType  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="Render a sandbox study to PNG")
    parser.add_argument("study", help="Python file with generate_svg-style code")
    parser.add_argument("-o", "--output", help="Output PNG path")
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=600)
    args = parser.parse_args()

    code = FilePath(args.study).read_text()
    t0 = time.monotonic()
    result = await run_python_code(code, args.width, args.height)
    t_exec = time.monotonic() - t0

    if result["return_code"] != 0:
        print(f"Sandbox error:\n{result['stderr']}", file=sys.stderr)
        return 1
    paths = result["paths"]
    if not paths:
        print(f"No paths generated. stdout:\n{result['stdout'][:2000]}", file=sys.stderr)
        return 1

    options = RenderOptions(
        width=args.width,
        height=args.height,
        drawing_style=DrawingStyleType.PAINT,
        output_format="bytes",
    )
    t0 = time.monotonic()
    png = render_strokes(paths, options)
    t_render = time.monotonic() - t0

    out_dir = FilePath(__file__).resolve().parent.parent / "screenshots" / "studies"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = FilePath(args.output) if args.output else out_dir / (
        FilePath(args.study).stem + ".png"
    )
    assert isinstance(png, bytes)
    out.write_bytes(png)
    print(f"{len(paths)} paths | exec {t_exec:.1f}s | render {t_render:.1f}s | {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
