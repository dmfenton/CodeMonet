#!/usr/bin/env python3
"""Render a generate_svg-style study to PNG for visual iteration.

Runs sandbox code (same environment the agent's generate_svg tool uses),
renders the resulting paths with the paint-mode pipeline, and saves a PNG.

With --compare, the same paths are also rendered by the *web client's*
stamp pipeline (stamping.ts via the dev-only /replay route) and a labeled
side-by-side with a diff heatmap is produced — this is what users actually
see, so use it to verify painting.py / stamping.ts parity.

Usage (from server/ so uv picks up dependencies):
    uv run python ../scripts/render-study.py ../studies/monet_poplars.py
    uv run python ../scripts/render-study.py ../studies/monet_poplars.py -o out.png
    uv run python ../scripts/render-study.py ../studies/monet_poplars.py --compare

--compare prerequisites: Vite dev server running (make dev-web or make web)
and Playwright chromium installed (uv run playwright install chromium).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from io import BytesIO
from pathlib import Path as FilePath

sys.path.insert(0, str(FilePath(__file__).resolve().parent.parent / "server"))

from code_monet.rendering import RenderOptions, render_strokes  # noqa: E402
from code_monet.tools.python_sandbox import run_python_code  # noqa: E402
from code_monet.types import DrawingStyleType  # noqa: E402

LABEL_HEIGHT = 22
GUTTER = 8


def compact(value: object) -> object:
    """Round floats for a compact JSON export."""
    if isinstance(value, float):
        return round(value, 1)
    if isinstance(value, list):
        return [compact(v) for v in value]
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items()}
    return value


async def render_client(data: dict, vite_port: int) -> bytes:
    """Render paths through the web client's stamp pipeline via /replay."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright not installed. Run: cd server && uv sync --extra dev "
            "&& uv run playwright install chromium"
        ) from None

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": data["width"] + 40, "height": data["height"] + 40},
            device_scale_factor=1,
        )
        await page.add_init_script(f"window.__REPLAY_DATA__ = {json.dumps(data)};")
        url = f"http://localhost:{vite_port}/replay"
        try:
            await page.goto(url, wait_until="load", timeout=10000)
        except Exception as e:
            await browser.close()
            raise RuntimeError(
                f"Cannot load {url} — is the Vite dev server running? (make web)"
            ) from e
        try:
            await page.wait_for_selector(
                '[data-testid="replay-canvas"][data-replay-ready="true"]',
                timeout=15000,
            )
        except Exception:
            error_el = await page.query_selector('[data-testid="replay-error"]')
            detail = await error_el.inner_text() if error_el else "timeout waiting for paint"
            await browser.close()
            raise RuntimeError(f"/replay failed: {detail}") from None
        png = await page.locator('[data-testid="replay-canvas"]').screenshot()
        await browser.close()
    return png


def compose_compare(server_png: bytes, client_png: bytes, out: FilePath) -> float:
    """Write server | client | diff side-by-side. Returns mean abs diff (0-255)."""
    from PIL import Image, ImageChops, ImageDraw, ImageStat

    server = Image.open(BytesIO(server_png)).convert("RGB")
    client = Image.open(BytesIO(client_png)).convert("RGB")
    if client.size != server.size:
        client = client.resize(server.size)

    diff = ImageChops.difference(server, client)
    mean_diff = sum(ImageStat.Stat(diff).mean) / 3
    heat = diff.point(lambda v: min(255, v * 4))

    w, h = server.size
    sheet = Image.new("RGB", (w * 3 + GUTTER * 2, h + LABEL_HEIGHT), "#222222")
    draw = ImageDraw.Draw(sheet)
    panels = [
        (server, "server (painting.py)"),
        (client, "client (stamping.ts)"),
        (heat, f"diff x4 (mean {mean_diff:.2f})"),
    ]
    for i, (img, label) in enumerate(panels):
        x = i * (w + GUTTER)
        draw.text((x + 6, 5), label, fill="#ffffff")
        sheet.paste(img, (x, LABEL_HEIGHT))
    sheet.save(out)
    return mean_diff


async def main() -> int:
    parser = argparse.ArgumentParser(description="Render a sandbox study to PNG")
    parser.add_argument("study", help="Python file with generate_svg-style code")
    parser.add_argument("-o", "--output", help="Output PNG path")
    parser.add_argument("--json", help="Also export paths as JSON (for stroke replay)")
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=600)
    parser.add_argument(
        "--style",
        choices=["paint", "plotter"],
        default="paint",
        help="Drawing style (default: paint)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Also render via the web client (/replay) and write a side-by-side diff",
    )
    parser.add_argument("--vite-port", type=int, default=5173)
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
        drawing_style=DrawingStyleType(args.style),
        output_format="bytes",
    )
    t0 = time.monotonic()
    png = render_strokes(paths, options)
    t_render = time.monotonic() - t0
    assert isinstance(png, bytes)

    out_dir = FilePath(__file__).resolve().parent.parent / "screenshots" / "studies"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = FilePath(args.output) if args.output else out_dir / (
        FilePath(args.study).stem + ".png"
    )
    out.write_bytes(png)

    data = {
        "width": args.width,
        "height": args.height,
        "style": args.style,
        "paths": [compact(p.model_dump(exclude_none=True)) for p in paths],
    }

    if args.json:
        json_out = FilePath(args.json)
        json_out.write_text(json.dumps(data, separators=(",", ":")))
        print(f"exported {len(paths)} paths to {json_out}")

    print(f"{len(paths)} paths | exec {t_exec:.1f}s | render {t_render:.1f}s | {out}")

    if args.compare:
        try:
            client_png = await render_client(data, args.vite_port)
        except RuntimeError as e:
            print(f"compare failed: {e}", file=sys.stderr)
            return 1
        compare_out = out.with_name(out.stem + "-compare.png")
        mean_diff = compose_compare(png, client_png, compare_out)
        print(f"client/server mean diff {mean_diff:.2f}/255 | {compare_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
