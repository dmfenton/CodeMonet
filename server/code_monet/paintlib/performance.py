"""The performance: a live stream of the pixels each paint op changed, in paint order.

The canvas records every paint op right after it runs. The recorder diffs the
op's box against a shadow of the surface as it was before the op, and emits a
**patch**: the finished (lit, varnished) colour of the changed pixels plus each
pixel's draw order within the op (its position along a stroke's path, or along
the broad sweeps that lay an area op in). Clients paste patches in over time,
drawing each patch's pixels in order, so they watch the real paint arrive.

Timing is one hand. A stroke waits while the brush travels through the air
from the last stroke's end, then lasts its brush travel time; an area op holds
the brush for a time that grows with sqrt(area). Times are "hand time" in ms;
clients play them back at a chosen speed.

Stream format (performance.bin, append-only; readable while being written):

    frame := part(json) part(index) part(color) part(order);  part := u32 len | bytes

The first frame is the header, with empty images:
    {"kind": "header", "width": W, "height": H, "format": 1}
Chunk frames carry the patches painted in ~CHUNK_WALL_S of run time:
    json: {"kind": "chunk", "stage": label, "atlas": [aw, ah], "patches": n}
    index: n little-endian records of <f4 t_ms, <f4 dur_ms, then <u2 atlas_x,
      atlas_y, w, h, x, y (20 bytes each)
  color: lossy WebP atlas (RGB) of the patches' pixels;
  order: lossless WebP atlas (L) at 1/4 resolution (atlas coordinates / 4):
  per 4x4 block, 1..255 = draw order (the block appears at
  t + dur * (order - 1) / 254); 0 = nothing changed there (paste it at t + dur).
The last frame is {"kind": "end", "ms": total} or {"kind": "error"}.
"""

from __future__ import annotations

import io
import json
import math
import os
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, BinaryIO, NamedTuple

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from . import brushplan
from .brushplan import PlanKind

# Timing is a time-lapse of one hand: each stroke takes time for how much it
# visibly changes the picture (its summed colour change, in pixels of full
# change, to CHANGE_POWER), so playback time follows visible change: broad
# lay-ins and the subject's shapes take time, faint texture dabs go by quickly.
# The brush moves between strokes through the air.
MS_PER_CHANGE = float(os.environ.get("CM_PERF_MS_PER_CHANGE", "0.5"))
CHANGE_POWER = float(os.environ.get("CM_PERF_CHANGE_POWER", "0.85"))
MIN_STROKE_MS = 5.0
MAX_STROKE_MS = 2000.0
AIR_PX_PER_MS = 40.0
MAX_AIR_MS = 40.0

# A chunk is flushed after this much *run* (wall-clock) time, so a live viewer
# is never more than about this far behind the painting program.
CHUNK_WALL_S = 0.5
_CHUNK_MAX_PIXELS = 4_000_000
_ATLAS_W = 2048
_COLOR_QUALITY = int(os.environ.get("CM_PERF_QUALITY", "75"))
# Draw order within an op is quantized to this many steps along its path: at
# time-lapse speeds a stroke lands in a frame or two, and fewer distinct values
# compress the lossless order atlas several times smaller.
_ORDER_STEPS = int(os.environ.get("CM_PERF_STEPS", "16"))
# The order atlas is 1/_ORDER_SCALE resolution: colour is exact per pixel, and
# order varies slowly along a stroke (pasting a patch's unchanged pixels is
# harmless: its colour is the current picture).
_ORDER_SCALE = 4

# A change smaller than this (0..1 colour, relief) is not paint arriving.
_RGB_EPS = 1.5 / 255
_HEIGHT_EPS = 0.01
# Strokes affect a little beyond their footprint (pickup, streaks, taper).
_STROKE_PAD = 4
# Relief changes re-light neighbours this far away.
_LIGHT_HALO = 2

_INDEX = struct.Struct("<ff6H")

Box = tuple[int, int, int, int]
LitFn = Callable[[Box], np.ndarray]


@dataclass
class _Patch:
    t: float
    dur: float
    x: int
    y: int
    color: np.ndarray  # h x w x 3 uint8
    order: np.ndarray  # h x w uint8 (0 = not in patch)


@dataclass
class PerformanceStats:
    patches: int = 0
    pixels: int = 0
    chunks: int = 0
    bytes: int = 0
    encode_seconds: float = 0.0
    diff_seconds: float = 0.0
    ms: float = 0.0


@dataclass
class _Chunk:
    stage: str = ""
    wall0: float = 0.0
    pixels: int = 0
    patches: list[_Patch] = field(default_factory=list)


class Performance:
    """Shadow of the surface as of the last recorded op, and the live patch stream."""

    def __init__(self, rgb: np.ndarray, height: np.ndarray, lit: LitFn) -> None:
        h, w = height.shape
        self.W, self.H = w, h
        self.shadow_rgb = rgb.copy()
        self.shadow_height = height.copy()
        self._lit = lit
        self._sink: BinaryIO | None = None
        self._shown: np.ndarray | None = None  # what viewers see (u8), when streaming
        self._chunk = _Chunk()
        self.clock = 0.0
        self._pen = (w / 2, h / 2)
        # Footprints (ys, xs, position along the mark) of marks not yet recorded.
        self._marks: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        self.stats = PerformanceStats()

    # ------------------------------------------------------------------ stream

    def stream_to(self, sink: BinaryIO, first_frame: np.ndarray, revision: bool) -> None:
        """Start streaming; `first_frame` (u8) is what viewers see before any patch.

        revision: this run paints over the previous version's canvas, so
        `first_frame` is that version's final picture (header base "previous").
        """
        self._sink = sink
        self._shown = first_frame.copy()
        base = "previous" if revision else "blank"
        self._write(
            {"kind": "header", "width": self.W, "height": self.H, "format": 1, "base": base}
        )

    def finish(self, final: np.ndarray, stage: str) -> None:
        """Emit whatever still differs from the finished picture (varnish, lighting), end."""
        if self._sink is None or self._shown is None:
            return
        diff = np.abs(final.astype(np.int16) - self._shown.astype(np.int16)).max(axis=2) > 2
        if diff.any():
            ys, xs = np.nonzero(diff)
            p = brushplan.plan("lay", xs, ys, seed=self.stats.patches)
            self._emit(stage, len(p.strokes), ys, xs, p.labels, p.frac, final)
        self._flush()
        self.stats.ms = self.clock
        # Rounded up: no patch may end after the stream does.
        self._write({"kind": "end", "ms": math.ceil(self.clock * 10) / 10})

    def abort(self) -> None:
        if self._sink is not None:
            self._write({"kind": "error"})

    # ------------------------------------------------------------------ recording

    def record(
        self,
        op: list[Any],
        rgb: np.ndarray,
        height: np.ndarray,
        stage: str,
        kind: PlanKind = "lay",
    ) -> None:
        """Diff what `op` changed, update the shadow, and stream it with hand timing.

        A stroke op is one patch drawn along its path; an area op is laid in by
        a brush plan of `kind` (brushplan.py), one patch per planned stroke.
        """
        t_diff = time.perf_counter()
        if op[0] == "s":
            pts = np.asarray(op[2:], np.float32).reshape(-1, 2)
            box = _pad_box(_points_box(pts), op[1] / 2 + _STROKE_PAD, self.W, self.H)
        else:
            box = _clip_box((int(op[1]), int(op[2]), int(op[3]), int(op[4])), self.W, self.H)
        ys, xs = self._take_changes(box, rgb, height)
        self.stats.diff_seconds += time.perf_counter() - t_diff
        if len(xs) == 0 or self._sink is None:
            return
        if op[0] == "s":
            frac = _path_param(pts, xs.astype(np.float32) + 0.5, ys.astype(np.float32) + 0.5)
            self._emit(stage, 1, ys, xs, np.zeros(len(xs), np.int32), frac, None)
        else:
            p = brushplan.plan(kind, xs, ys, seed=self.stats.patches)
            self._emit(
                stage, len(p.strokes), ys, xs, p.labels, p.frac, None, instant=kind == "prime"
            )

    def add_mark(self, ys: np.ndarray, xs: np.ndarray, along: np.ndarray) -> None:
        """A brush mark's footprint: the pixels it touched and how far along it each is."""
        self._marks.append((ys, xs, along))

    @property
    def pending_marks(self) -> int:
        return len(self._marks)

    def record_marks(self, rgb: np.ndarray, height: np.ndarray, stage: str) -> None:
        """Record the pending marks with one diff: each changed pixel is painted by the
        last mark that touched it, along that mark (one patch per mark, in order).

        Per-op recording costs about as much as a small mark itself; a region's
        thousands of marks are recorded in groups instead.
        """
        marks, self._marks = self._marks, []
        if not marks:
            return
        t_diff = time.perf_counter()
        bx0 = min(int(m[1].min()) for m in marks)
        by0 = min(int(m[0].min()) for m in marks)
        bx1 = max(int(m[1].max()) for m in marks) + 1
        by1 = max(int(m[0].max()) for m in marks) + 1
        box = _pad_box((bx0, by0, bx1, by1), _STROKE_PAD, self.W, self.H)
        ys, xs = self._take_changes(box, rgb, height)
        self.stats.diff_seconds += time.perf_counter() - t_diff
        if len(xs) == 0 or self._sink is None:
            return
        x0, y0, x1, y1 = box
        lab = np.full((y1 - y0, x1 - x0), -1, np.int32)
        along = np.zeros((y1 - y0, x1 - x0), np.float32)
        for k, (my, mx, ma) in enumerate(marks):
            lab[my - y0, mx - x0] = k
            along[my - y0, mx - x0] = ma
        iy, ix = ys - y0, xs - x0
        self._emit(stage, len(marks), ys, xs, lab[iy, ix], along[iy, ix], None)

    def record_direct_edits(
        self, rgb: np.ndarray, height: np.ndarray, stage: str
    ) -> list[Any] | None:
        """Changes made outside any op (direct cv.rgb edits), recorded as one area op."""
        changed = self._changed((0, 0, self.W, self.H), rgb, height)
        if not changed.any():
            return None
        ys, xs = np.nonzero(changed)
        op: list[Any] = ["a", int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
        self.record(op, rgb, height, stage)
        return op

    # ------------------------------------------------------------------ timing

    def _time_stroke(
        self, sel: np.ndarray, delta: np.ndarray, x0: int, y0: int
    ) -> tuple[float, float]:
        """(start, duration) of the next stroke: travel to it, then paint it."""
        rows, cols = np.nonzero(sel)
        at = (x0 + float(cols.mean()), y0 + float(rows.mean()))
        air = math.hypot(at[0] - self._pen[0], at[1] - self._pen[1]) / AIR_PX_PER_MS
        change = float(delta[sel].sum()) / 255.0
        start = self.clock + min(MAX_AIR_MS, air)
        dur = min(MAX_STROKE_MS, max(MIN_STROKE_MS, MS_PER_CHANGE * change**CHANGE_POWER))
        self.clock = start + dur
        self._pen = at
        return start, dur

    # ------------------------------------------------------------------ patches

    def _emit(
        self,
        stage: str,
        n_strokes: int,
        ys: np.ndarray,
        xs: np.ndarray,
        labels: np.ndarray,
        frac: np.ndarray,
        final: np.ndarray | None,
        instant: bool = False,
    ) -> None:
        """Stream one op's changed pixels as one timed patch per stroke (labels 0..n-1).

        instant: the patch lands at once (canvas preparation, not painting).
        """
        assert self._shown is not None
        x0, y0 = max(0, int(xs.min()) - _LIGHT_HALO), max(0, int(ys.min()) - _LIGHT_HALO)
        x1 = min(self.W, int(xs.max()) + 1 + _LIGHT_HALO)
        y1 = min(self.H, int(ys.max()) + 1 + _LIGHT_HALO)
        lab = np.full((y1 - y0, x1 - x0), -1, np.int32)
        fr = np.zeros((y1 - y0, x1 - x0), np.float32)
        lab[ys - y0, xs - x0] = labels
        fr[ys - y0, xs - x0] = frac
        if final is None:
            # Relief re-lights a thin halo: those pixels land with their neighbours.
            size = 2 * _LIGHT_HALO + 1
            halo = lab < 0
            lab = np.where(halo, ndi.grey_dilation(lab, size=size), lab)
            fr = np.where(halo, ndi.grey_dilation(fr, size=size), fr)
            color = _to_u8(self._lit((x0, y0, x1, y1)))
        else:
            color = final[y0:y1, x0:x1]
        shown = self._shown[y0:y1, x0:x1]
        delta = np.abs(color.astype(np.int16) - shown.astype(np.int16)).max(axis=2)
        lab[delta == 0] = -1
        step = 254 // (_ORDER_STEPS - 1)
        # Each stroke's bounding rect in one pass (not a full-box scan per stroke).
        rects = ndi.find_objects(lab + 1, max_label=n_strokes)
        for k, rect in enumerate(rects):
            if rect is None:
                continue
            r0, r1, c0, c1 = rect[0].start, rect[0].stop, rect[1].start, rect[1].stop
            s_sel = lab[r0:r1, c0:c1] == k
            start, dur = (
                (self.clock, 0.0)
                if instant
                else self._time_stroke(s_sel, delta[r0:r1, c0:c1], x0 + c0, y0 + r0)
            )
            order = np.zeros(s_sel.shape, np.uint8)
            steps = np.round(fr[r0:r1, c0:c1][s_sel] * (_ORDER_STEPS - 1)).astype(np.uint8)
            order[s_sel] = 1 + steps * step
            s_shown = shown[r0:r1, c0:c1]
            # Pixels of the rect outside this stroke keep what viewers see now.
            patch_color = np.where(s_sel[..., None], color[r0:r1, c0:c1], s_shown)
            s_shown[:] = patch_color
            self._add(stage, _Patch(start, dur, x0 + c0, y0 + r0, patch_color, order))

    def _add(self, stage: str, patch: _Patch) -> None:
        ch = self._chunk
        if ch.patches and (
            stage != ch.stage
            or time.monotonic() - ch.wall0 >= CHUNK_WALL_S
            or ch.pixels + patch.order.size > _CHUNK_MAX_PIXELS
        ):
            self._flush()
            ch = self._chunk
        if not ch.patches:
            ch.stage, ch.wall0 = stage, time.monotonic()
        ch.patches.append(patch)
        ch.pixels += patch.order.size
        self.stats.patches += 1
        self.stats.pixels += int(np.count_nonzero(patch.order))

    def _flush(self) -> None:
        ch = self._chunk
        if not ch.patches:
            return
        t0 = time.perf_counter()
        k = _ORDER_SCALE
        sizes = [(-(-p.order.shape[1] // k) * k, -(-p.order.shape[0] // k) * k) for p in ch.patches]
        places, aw, ah = _shelf_pack(sizes)
        aw, ah = -(-aw // k) * k, -(-ah // k) * k
        color = np.zeros((ah, aw, 3), np.uint8)
        order = np.zeros((ah // k, aw // k), np.uint8)
        index = bytearray()
        for p, (ax, ay) in zip(ch.patches, places, strict=True):
            h, w = p.order.shape
            color[ay : ay + h, ax : ax + w] = p.color
            low = _block_max(p.order, k)
            order[ay // k : ay // k + low.shape[0], ax // k : ax // k + low.shape[1]] = low
            index += _INDEX.pack(p.t, p.dur, ax, ay, w, h, p.x, p.y)
        cbuf, obuf = io.BytesIO(), io.BytesIO()
        Image.fromarray(color).save(cbuf, "WEBP", quality=_COLOR_QUALITY, method=0)
        Image.fromarray(order).save(obuf, "WEBP", lossless=True, quality=0, method=0)
        self.stats.encode_seconds += time.perf_counter() - t0
        self.stats.chunks += 1
        meta = {"kind": "chunk", "stage": ch.stage, "atlas": [aw, ah], "patches": len(ch.patches)}
        self._write(meta, bytes(index), cbuf.getvalue(), obuf.getvalue())
        self._chunk = _Chunk()

    def _write(
        self, meta: dict[str, Any], index: bytes = b"", color: bytes = b"", order: bytes = b""
    ) -> None:
        if self._sink is None:
            return
        head = json.dumps(meta, separators=(",", ":")).encode()
        frame = b"".join(
            struct.pack("<I", len(part)) + part for part in (head, index, color, order)
        )
        self._sink.write(frame)
        self._sink.flush()
        self.stats.bytes += len(frame)

    # ------------------------------------------------------------------ diffing

    def _changed(self, box: Box, rgb: np.ndarray, height: np.ndarray) -> np.ndarray:
        x0, y0, x1, y1 = box
        d_rgb = np.abs(rgb[y0:y1, x0:x1] - self.shadow_rgb[y0:y1, x0:x1]).max(axis=2)
        d_h = np.abs(height[y0:y1, x0:x1] - self.shadow_height[y0:y1, x0:x1])
        return (d_rgb > _RGB_EPS) | (d_h > _HEIGHT_EPS)

    def _take_changes(
        self, box: Box, rgb: np.ndarray, height: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        x0, y0, x1, y1 = box
        if x1 <= x0 or y1 <= y0:
            return np.empty(0, np.intp), np.empty(0, np.intp)
        changed = self._changed(box, rgb, height)
        self.shadow_rgb[y0:y1, x0:x1] = rgb[y0:y1, x0:x1]
        self.shadow_height[y0:y1, x0:x1] = height[y0:y1, x0:x1]
        ys, xs = np.nonzero(changed)
        return ys + y0, xs + x0


class Frame(NamedTuple):
    meta: dict[str, Any]
    records: bytes
    color: bytes
    order: bytes

    def patches(self) -> list[tuple[float, float, int, int, int, int, int, int]]:
        recs = self.records
        return [_INDEX.unpack_from(recs, i) for i in range(0, len(recs), _INDEX.size)]


class FrameScanner:
    """Follows a growing stream's framing without decoding it: has it ended?"""

    def __init__(self) -> None:
        self._pending = b""
        self._part = 0
        self._head = b""
        self.ended = False

    def feed(self, data: bytes) -> None:
        buf = self._pending + data
        i = 0
        while not self.ended and i + 4 <= len(buf):
            (n,) = struct.unpack_from("<I", buf, i)
            if i + 4 + n > len(buf):
                break
            if self._part == 0:
                self._head = buf[i + 4 : i + 4 + n]
            i += 4 + n
            self._part = (self._part + 1) % 4
            if self._part == 0 and _terminal(self._head):
                self.ended = True
        self._pending = buf[i:]


def _terminal(head: bytes) -> bool:
    try:
        meta = json.loads(head)
    except ValueError:
        return True  # garbage: treat the stream as over
    return not isinstance(meta, dict) or meta.get("kind") in ("end", "error")


def read_frames(data: bytes) -> list[Frame]:
    """Parse a (possibly partial) stream into complete frames."""
    frames: list[Frame] = []
    i = 0
    while True:
        parts: list[bytes] = []
        j = i
        for _ in range(4):
            if j + 4 > len(data):
                return frames
            (n,) = struct.unpack_from("<I", data, j)
            if j + 4 + n > len(data):
                return frames
            parts.append(data[j + 4 : j + 4 + n])
            j += 4 + n
        frames.append(Frame(json.loads(parts[0]), parts[1], parts[2], parts[3]))
        i = j


def _block_max(order: np.ndarray, k: int) -> np.ndarray:
    """Draw order per k x k block (latest pixel in the block); 0 = nothing changed."""
    h, w = order.shape
    padded = np.zeros((-(-h // k) * k, -(-w // k) * k), np.uint8)
    padded[:h, :w] = order
    return padded.reshape(padded.shape[0] // k, k, padded.shape[1] // k, k).max(axis=(1, 3))


def _to_u8(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def _shelf_pack(sizes: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], int, int]:
    """Pack (w, h) rects into rows of a fixed-width atlas; returns places and atlas size."""
    aw = max(_ATLAS_W, max(w for w, _ in sizes))
    order = sorted(range(len(sizes)), key=lambda k: -sizes[k][1])
    places: list[tuple[int, int]] = [(0, 0)] * len(sizes)
    x = y = row_h = 0
    for k in order:
        w, h = sizes[k]
        if x + w > aw:
            x, y, row_h = 0, y + row_h, 0
        places[k] = (x, y)
        x += w
        row_h = max(row_h, h)
    return places, aw, y + row_h


def _points_box(pts: np.ndarray) -> tuple[float, float, float, float]:
    return (
        float(pts[:, 0].min()),
        float(pts[:, 1].min()),
        float(pts[:, 0].max()),
        float(pts[:, 1].max()),
    )


def _pad_box(box: tuple[float, float, float, float], pad: float, w: int, h: int) -> Box:
    x0, y0, x1, y1 = box
    return _clip_box(
        (math.floor(x0 - pad), math.floor(y0 - pad), math.ceil(x1 + pad), math.ceil(y1 + pad)),
        w,
        h,
    )


def _clip_box(box: Box, w: int, h: int) -> Box:
    x0, y0, x1, y1 = box
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1)


def _path_length(pts: np.ndarray) -> float:
    return float(np.hypot(*np.diff(pts, axis=0).T).sum()) if len(pts) > 1 else 0.0


def _path_param(pts: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """0..1 arc-length position of each pixel's nearest point on the polyline."""
    if len(pts) < 2:
        return np.zeros(len(xs), np.float32)
    seg = np.diff(pts, axis=0)
    seg_len = np.hypot(seg[:, 0], seg[:, 1])
    total = float(seg_len.sum())
    if total <= 1e-6:
        return np.zeros(len(xs), np.float32)
    cum = np.concatenate([[0.0], np.cumsum(seg_len)[:-1]]).astype(np.float32)
    best_d = np.full(len(xs), np.inf, np.float32)
    best_s = np.zeros(len(xs), np.float32)
    for (ax, ay), (dx, dy), seg_l, c in zip(pts[:-1], seg, seg_len, cum, strict=True):
        if seg_l <= 1e-6:
            continue
        t = np.clip(((xs - ax) * dx + (ys - ay) * dy) / (seg_l * seg_l), 0, 1)
        d = (xs - ax - t * dx) ** 2 + (ys - ay - t * dy) ** 2
        better = d < best_d
        best_d[better] = d[better]
        best_s[better] = c + t[better] * seg_l
    return best_s / np.float32(total)
