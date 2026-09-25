#!/usr/bin/env python3
"""Run a fixed set of painting prompts through the live agent and collect results.

Drives a running dev server (DEV_MODE=true) over WebSocket, one prompt at a
time: new_canvas -> acknowledge stroke batches -> wait for piece completion ->
save the server render. Produces a labeled contact sheet so runs with
different models/prompts/renderers can be compared side by side.

Usage (from server/):
    uv run python ../scripts/art-benchmark.py --label baseline
    uv run python ../scripts/art-benchmark.py --label opus55 --only storm,pool

Output: screenshots/benchmarks/<label>-<timestamp>/
    <key>.png          final server render
    <key>-batchN.png   progress render after each stroke batch (vector modes)
    <key>-vNN.jpg      preview of each program-painting version (paint mode)
    <key>.events.jsonl every WebSocket event (full trace)
    sheet.png          labeled contact sheet
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import httpx
import websockets
from PIL import Image, ImageDraw

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"
WS_MAX_SIZE = 64 * 1024 * 1024

PROMPTS: dict[str, str] = {
    "storm": "A small steamship caught in a violent storm at sea, in the style of J.M.W. Turner",
    "pool": "A modernist house beside a swimming pool with a diving board under a bright "
    "California sky, in the style of David Hockney",
    "cezanne": "Mont Sainte-Victoire seen across the valley, framed by a pine tree, "
    "in the style of Paul Cézanne",
    "bruegel": "A winter village with skaters on a frozen pond, in the style of "
    "Pieter Bruegel the Elder",
}


async def get_token(client: httpx.AsyncClient) -> str:
    resp = await client.get(f"{BASE_URL}/auth/dev-token")
    resp.raise_for_status()
    return str(resp.json()["access_token"])


async def save_canvas(client: httpx.AsyncClient, token: str, path: Path) -> bool:
    try:
        resp = await client.get(
            f"{BASE_URL}/canvas.png", headers={"Authorization": f"Bearer {token}"}
        )
    except httpx.TimeoutException:
        return False
    if resp.status_code != 200:
        return False
    path.write_bytes(resp.content)
    return True


async def run_prompt(key: str, prompt: str, out: Path, timeout: float) -> dict:
    async with httpx.AsyncClient(timeout=180.0) as client:
        token = await get_token(client)
        events_path = out / f"{key}.events.jsonl"
        started = time.monotonic()
        batches = 0
        completed = False
        sent_canvas = False
        with events_path.open("w") as log:
            # The server can stall its event loop while rendering large batches,
            # so keepalive pings are disabled and dropped connections reconnect.
            while not completed and time.monotonic() - started < timeout:
                try:
                    async with websockets.connect(
                        f"{WS_URL}?token={token}", max_size=WS_MAX_SIZE, ping_interval=None
                    ) as ws:
                        if not sent_canvas:
                            await ws.send(
                                json.dumps(
                                    {"type": "new_canvas", "direction": prompt, "drawing_style": "paint"}
                                )
                            )
                            await ws.send(json.dumps({"type": "resume"}))
                            sent_canvas = True
                        while time.monotonic() - started < timeout:
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                            except TimeoutError:
                                continue
                            msg = json.loads(raw)
                            t = round(time.monotonic() - started, 2)
                            log.write(json.dumps({"t": t, **msg}) + "\n")
                            kind = msg.get("type")
                            if kind == "agent_strokes_ready":
                                # Acknowledge immediately; the server render is the artifact.
                                with suppress(httpx.TimeoutException):
                                    await client.get(
                                        f"{BASE_URL}/strokes/pending",
                                        headers={"Authorization": f"Bearer {token}"},
                                    )
                                await ws.send(
                                    json.dumps(
                                        {"type": "animation_done", "batch_id": msg.get("batch_id")}
                                    )
                                )
                                batches += 1
                                await save_canvas(
                                    client, token, out / f"{key}-batch{batches:02d}.png"
                                )
                            elif kind == "painting_version":
                                # Program painting: keep every version's preview, and
                                # the latest full-resolution final as the result.
                                base = f"{BASE_URL}{msg['asset_base']}"
                                with suppress(httpx.HTTPError):
                                    prev = await client.get(f"{base}preview.jpg")
                                    (out / f"{key}-v{msg['version']:02d}.jpg").write_bytes(
                                        prev.content
                                    )
                                    final = await client.get(f"{base}final.png")
                                    (out / f"{key}.png").write_bytes(final.content)
                                batches += 1
                            elif kind == "piece_state" and msg.get("completed"):
                                completed = True
                                break
                        if not (out / f"{key}.png").exists():
                            await save_canvas(client, token, out / f"{key}.png")
                        await ws.send(json.dumps({"type": "pause"}))
                except websockets.exceptions.ConnectionClosed as exc:
                    log.write(json.dumps({"t": round(time.monotonic() - started, 2), "type": "harness_reconnect", "reason": str(exc)}) + "\n")
                    await asyncio.sleep(2)
        if not (out / f"{key}.png").exists():
            await save_canvas(client, token, out / f"{key}.png")
        elapsed = time.monotonic() - started
        print(f"[{key}] completed={completed} batches={batches} {elapsed:.0f}s")
        return {"key": key, "completed": completed, "batches": batches, "seconds": round(elapsed)}


def contact_sheet(out: Path, keys: list[str], label: str) -> None:
    tiles = [(k, Image.open(out / f"{k}.png").convert("RGB")) for k in keys if (out / f"{k}.png").exists()]
    if not tiles:
        return
    w, h = 800, 600
    cols = 2
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w + (cols - 1) * 10, rows * (h + 28) + 30), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 8), label, fill="black")
    for i, (key, img) in enumerate(tiles):
        x, y = (i % cols) * (w + 10), 30 + (i // cols) * (h + 28)
        sheet.paste(img.resize((w, h)), (x, y))
        draw.text((x + 4, y + h + 6), key, fill="black")
    sheet.save(out / "sheet.png")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--label", required=True, help="Run label, e.g. baseline or opus55")
    parser.add_argument("--only", help="Comma-separated prompt keys to run")
    parser.add_argument("--timeout", type=float, default=1800, help="Seconds per prompt")
    parser.add_argument("--out", help="Existing output dir to continue a run into")
    args = parser.parse_args()

    keys = args.only.split(",") if args.only else list(PROMPTS)
    if args.out:
        out = Path(args.out)
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        root = Path(__file__).resolve().parent.parent / "screenshots" / "benchmarks"
        out = root / f"{args.label}-{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    results_path = out / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else []
    for key in keys:
        results.append(await run_prompt(key, PROMPTS[key], out, args.timeout))
        results_path.write_text(json.dumps(results, indent=2))
    contact_sheet(out, list(PROMPTS), args.label)
    print(f"Output: {out}")


if __name__ == "__main__":
    asyncio.run(main())
