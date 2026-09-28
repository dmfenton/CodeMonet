"""Render a painting performance (performance.bin) to a video, as viewers see it.

Same semantics as the web PerformancePlayer: patches are pasted in stream order
at hand time x speed; an in-flight patch shows the 4x4 blocks whose draw order
has been reached. Writes an mp4 plus a contact sheet next to it.

    cd server && uv run python ../scripts/performance-video.py PERF.bin --out OUT.mp4 \\
        [--seconds 90 | --speed 20] [--fps 30] [--width 960]

Or paint and render in one go (runs the paint program through the runner):

    cd server && uv run python ../scripts/performance-video.py --program painting.py \\
        --out OUT.mp4 --seconds 90
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from code_monet.paintlib.performance import Frame, read_frames

ORDER_SCALE = 4


def load(path: Path) -> tuple[dict, list[tuple], float]:
    """Header, patches as (t, dur, color_crop, order_crop, x, y, stage), end ms."""
    frames: list[Frame] = read_frames(path.read_bytes())
    head = frames[0].meta
    patches: list[tuple] = []
    end = 0.0
    for f in frames[1:]:
        if f.meta["kind"] == "end":
            end = float(f.meta["ms"])
            continue
        if f.meta["kind"] != "chunk":
            continue
        color = np.asarray(Image.open(io.BytesIO(f.color)).convert("RGB"))
        order = np.asarray(Image.open(io.BytesIO(f.order)).convert("L"))
        for t, dur, ax, ay, w, h, x, y in f.patches():
            crop = color[ay : ay + h, ax : ax + w]
            o = order[ay // ORDER_SCALE : (ay + h - 1) // ORDER_SCALE + 1,
                      ax // ORDER_SCALE : (ax + w - 1) // ORDER_SCALE + 1]
            o = np.repeat(np.repeat(o, ORDER_SCALE, 0), ORDER_SCALE, 1)[:h, :w]
            o = np.where(o == 0, 255, o).astype(np.float32)
            patches.append((t, dur, crop, o, x, y, f.meta["stage"]))
    if not end and patches:
        end = patches[-1][0] + patches[-1][1]
    return head, patches, end


def render(perf: Path, out: Path, seconds: float | None, speed: float | None, fps: int,
           width: int, base: Path | None = None) -> None:
    head, patches, end = load(perf)
    W, H = head["width"], head["height"]
    speed = speed or (end / 1000 / seconds if seconds else 20.0)
    n_frames = int(end / speed / 1000 * fps) + 1
    step = speed * 1000 / fps
    pic = (
        np.asarray(Image.open(base).convert("RGB")).copy()
        if base
        else np.full((H, W, 3), 255, np.uint8)
    )
    scale = width / W
    size = (width, round(H * scale) // 2 * 2)
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", "-movflags", "+faststart",
         str(out)],
        stdin=subprocess.PIPE,
    )
    assert proc.stdin
    sheet_frames: list[Image.Image] = []
    sheet_every = max(1, n_frames // 24)
    cursor = 0
    for i in range(n_frames + fps):  # hold the final picture for a second
        now = min(end, i * step)
        j = cursor
        while j < len(patches) and patches[j][0] <= now:
            t, dur, crop, order, x, y, _stage = patches[j]
            h, w = order.shape
            region = pic[y : y + h, x : x + w]
            if now >= t + dur:
                region[:] = crop
                if j == cursor:
                    cursor += 1
            else:
                thr = 1 + (now - t) / dur * 254 if dur > 0 else 256
                np.copyto(region, crop, where=(order <= thr)[..., None])
            j += 1
        frame = Image.fromarray(pic).resize(size, Image.Resampling.BILINEAR)
        proc.stdin.write(frame.tobytes())
        if i % sheet_every == 0 and len(sheet_frames) < 24:
            sheet_frames.append(frame.copy())
    proc.stdin.close()
    proc.wait()
    tw, th = size[0] // 3, size[1] // 3
    sheet = Image.new("RGB", (tw * 6, (th + 14) * 4), "white")
    d = ImageDraw.Draw(sheet)
    for k, im in enumerate(sheet_frames):
        x0, y0 = (k % 6) * tw, (k // 6) * (th + 14)
        sheet.paste(im.resize((tw, th)), (x0, y0 + 14))
        d.text((x0 + 3, y0 + 1), f"{k * sheet_every / fps:.0f}s", fill="black")
    sheet.save(out.with_suffix(".jpg"), quality=85)
    print(f"{out}: {n_frames / fps:.0f}s at {speed:.1f}x ({len(patches)} patches, "
          f"{end / 60000:.1f} min hand time)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("perf", nargs="?", type=Path)
    ap.add_argument("--program", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--speed", type=float)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--base", type=Path, help="picture before the performance (a revision's "
                    "previous final.png)")
    ap.add_argument("--previous", type=Path, help="with --program: the last version's "
                    "directory; paint as its revision (also sets --base)")
    args = ap.parse_args()
    if args.program:
        # The version's assets land next to the video (<out>-run/), for inspection.
        run = args.out.parent / f"{args.out.stem}-run"
        run.mkdir(parents=True, exist_ok=True)
        res = subprocess.run(
            [sys.executable, "-m", "code_monet.paint_runner", "--program",
             str(args.program), "--out", str(run), "--width", "1600", "--height", "1200",
             *(["--previous", str(args.previous)] if args.previous else [])],
            capture_output=True, text=True,
        )
        if res.returncode:
            print(res.stderr[-2000:], file=sys.stderr)
            return 1
        print(res.stderr.strip().splitlines()[-1][:400])
        args.perf = run / "performance.bin"
        if args.previous and not args.base:
            args.base = args.previous / "final.png"
    if not args.perf:
        ap.error("give PERF.bin or --program")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    render(args.perf, args.out, args.seconds, args.speed, args.fps, args.width, args.base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
