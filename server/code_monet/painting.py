"""Stamp-based painterly stroke rasterization for paint mode.

Renders brush strokes as sequences of textured, oriented dabs ("stamps")
instead of uniform-width vector lines. This produces the cues that make
marks read as paint: width that tapers and swells along the stroke,
bristle streaks, dry-brush breakup over canvas tooth, broken color within
a stroke, and impasto lighting from accumulated paint height.

The module exposes `PaintSurface`, which owns the working image plus the
paint height map, and renders strokes/fills onto it. `finish()` applies
impasto lighting and canvas grain and returns the final RGB image.
"""

from __future__ import annotations

import colorsys
import math
import random
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

# ---------------------------------------------------------------------------
# Brush dynamics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrushDynamics:
    """How a brush behaves when stamped along a path."""

    spacing: float = 0.35  # stamp spacing as fraction of width
    aspect: float = 1.7  # stamp length / stamp width
    streaks: int = 5  # bristle streak rows in the sprite
    streak_contrast: float = 0.45  # 0 = smooth dab, 1 = strong bristle rails
    edge_rough: float = 0.35  # raggedness of the sprite outline
    dryness: float = 0.12  # tooth-driven alpha breakup (0-1)
    load_fade: float = 0.25  # paint depletion toward stroke end (0-1)
    hue_jitter: float = 0.012  # per-stamp hue wobble (fraction of wheel)
    sat_jitter: float = 0.10
    val_jitter: float = 0.08
    taper: float = 0.6  # end taper strength
    width_wobble: float = 0.22  # low-frequency width variation
    blur: float = 0.0  # post blur radius on the stroke layer
    impasto: float = 0.5  # height-map contribution
    wet_edge: float = 0.0  # watercolor-style edge darkening (0-1)
    opacity_scale: float = 1.0  # multiplier on requested opacity


_DYNAMICS: dict[str, BrushDynamics] = {
    "oil_round": BrushDynamics(
        spacing=0.32,
        aspect=1.5,
        streaks=6,
        streak_contrast=0.42,
        edge_rough=0.3,
        dryness=0.10,
        hue_jitter=0.012,
        taper=0.65,
        width_wobble=0.22,
        impasto=0.8,
    ),
    "oil_flat": BrushDynamics(
        spacing=0.30,
        aspect=1.25,
        streaks=8,
        streak_contrast=0.75,
        edge_rough=0.22,
        dryness=0.14,
        hue_jitter=0.010,
        taper=0.3,
        width_wobble=0.14,
        impasto=0.9,
    ),
    "oil_filbert": BrushDynamics(
        spacing=0.34,
        aspect=1.8,
        streaks=6,
        streak_contrast=0.5,
        edge_rough=0.35,
        dryness=0.12,
        hue_jitter=0.014,
        taper=0.55,
        width_wobble=0.24,
        impasto=0.85,
    ),
    "dry_brush": BrushDynamics(
        spacing=0.30,
        aspect=1.9,
        streaks=9,
        streak_contrast=0.95,
        edge_rough=0.6,
        dryness=0.55,
        load_fade=0.5,
        hue_jitter=0.010,
        taper=0.5,
        width_wobble=0.3,
        impasto=0.35,
    ),
    "palette_knife": BrushDynamics(
        spacing=0.42,
        aspect=2.6,
        streaks=3,
        streak_contrast=0.35,
        edge_rough=0.5,
        dryness=0.20,
        load_fade=0.45,
        hue_jitter=0.008,
        sat_jitter=0.06,
        val_jitter=0.12,
        taper=0.15,
        width_wobble=0.10,
        impasto=1.6,
        opacity_scale=1.0,
    ),
    "watercolor": BrushDynamics(
        spacing=0.40,
        aspect=1.6,
        streaks=0,
        streak_contrast=0.0,
        edge_rough=0.45,
        dryness=0.05,
        load_fade=0.15,
        hue_jitter=0.010,
        sat_jitter=0.12,
        val_jitter=0.05,
        taper=0.5,
        width_wobble=0.28,
        blur=1.1,
        impasto=0.0,
        wet_edge=0.55,
    ),
    "airbrush": BrushDynamics(
        spacing=0.45,
        aspect=1.0,
        streaks=0,
        streak_contrast=0.0,
        edge_rough=0.0,
        dryness=0.0,
        load_fade=0.0,
        hue_jitter=0.004,
        sat_jitter=0.04,
        val_jitter=0.03,
        taper=0.0,
        width_wobble=0.05,
        blur=2.6,
        impasto=0.0,
    ),
    "charcoal": BrushDynamics(
        spacing=0.32,
        aspect=1.4,
        streaks=5,
        streak_contrast=0.55,
        edge_rough=0.5,
        dryness=0.45,
        load_fade=0.3,
        hue_jitter=0.0,
        sat_jitter=0.04,
        val_jitter=0.10,
        taper=0.4,
        width_wobble=0.25,
        impasto=0.0,
    ),
    "ink": BrushDynamics(
        spacing=0.28,
        aspect=1.4,
        streaks=0,
        streak_contrast=0.0,
        edge_rough=0.15,
        dryness=0.06,
        load_fade=0.2,
        hue_jitter=0.0,
        sat_jitter=0.02,
        val_jitter=0.04,
        taper=0.9,
        width_wobble=0.18,
        impasto=0.1,
    ),
    "pencil": BrushDynamics(
        spacing=0.30,
        aspect=1.2,
        streaks=2,
        streak_contrast=0.4,
        edge_rough=0.3,
        dryness=0.35,
        load_fade=0.1,
        hue_jitter=0.0,
        sat_jitter=0.02,
        val_jitter=0.06,
        taper=0.25,
        width_wobble=0.12,
        impasto=0.0,
    ),
    "marker": BrushDynamics(
        spacing=0.30,
        aspect=1.3,
        streaks=0,
        streak_contrast=0.0,
        edge_rough=0.12,
        dryness=0.04,
        load_fade=0.08,
        hue_jitter=0.004,
        sat_jitter=0.03,
        val_jitter=0.03,
        taper=0.15,
        width_wobble=0.06,
        blur=0.4,
        impasto=0.0,
    ),
    "splatter": BrushDynamics(
        spacing=1.6,
        aspect=0.9,
        streaks=0,
        streak_contrast=0.0,
        edge_rough=0.7,
        dryness=0.3,
        load_fade=0.2,
        hue_jitter=0.02,
        sat_jitter=0.12,
        val_jitter=0.12,
        taper=0.2,
        width_wobble=0.8,
        impasto=0.4,
    ),
}

_DEFAULT_DYNAMICS = BrushDynamics()


def get_dynamics(brush: str | None) -> BrushDynamics:
    """Dynamics for a brush name (default oil-like behavior)."""
    return _DYNAMICS.get(brush or "", _DEFAULT_DYNAMICS)


# ---------------------------------------------------------------------------
# Sprites (dab textures)
# ---------------------------------------------------------------------------

_SPRITE_BASE_W = 48  # sprite height (across stroke) in px before scaling
_SPRITE_VARIANTS = 4
_ANGLE_BIN = 12.0  # degrees per cached rotation bin
_sprite_cache: dict[tuple, np.ndarray] = {}


def _base_sprite(brush: str, variant: int) -> np.ndarray:
    """Horizontal dab alpha texture in [0,1], shape (W, L)."""
    key = ("base", brush, variant)
    cached = _sprite_cache.get(key)
    if cached is not None:
        return cached

    dyn = get_dynamics(brush)
    rng = np.random.default_rng(hash((brush, variant)) & 0xFFFFFFFF)
    width = _SPRITE_BASE_W
    length = max(8, int(width * dyn.aspect))
    ys = (np.linspace(-1, 1, width))[:, None]
    xs = (np.linspace(-1, 1, length))[None, :]

    # Elliptical body with a broad plateau and soft falloff.
    r2 = xs**2 + ys**2
    body = np.clip(2.2 * (1.0 - r2), 0.0, 1.0) ** 0.6

    # Ragged edge: radial noise pushes the rim in and out.
    if dyn.edge_rough > 0:
        coarse = rng.standard_normal((6, 8))
        noise = (
            np.asarray(
                Image.fromarray(
                    ((coarse - coarse.min()) / (np.ptp(coarse) + 1e-6) * 255).astype("uint8")
                ).resize((length, width), Image.Resampling.BILINEAR),
                dtype=np.float32,
            )
            / 255.0
        )
        rim = np.clip((r2 - (1.0 - dyn.edge_rough * 0.9)) / (dyn.edge_rough * 0.9 + 1e-6), 0, 1)
        body *= 1.0 - rim * (0.3 + 0.7 * noise)

    # Bristle streaks: per-row gain with gaps, smoothed slightly.
    if dyn.streaks > 0 and dyn.streak_contrast > 0:
        rows = rng.random(dyn.streaks)
        row_gain = (
            np.asarray(
                Image.fromarray((rows * 255).astype("uint8")[:, None]).resize(
                    (1, width), Image.Resampling.BILINEAR
                ),
                dtype=np.float32,
            )[:, 0]
            / 255.0
        )
        gain = 1.0 - dyn.streak_contrast + dyn.streak_contrast * (0.35 + 0.9 * row_gain)
        # Streaks fade in/out along the dab so rails do not look ruled.
        run = 0.6 + 0.4 * np.clip(1.2 - np.abs(xs), 0, 1)
        body *= np.clip(gain[:, None] * run, 0.0, 1.3)

    # Fine speckle so flats are never airbrush-smooth.
    speck = rng.random((width, length)).astype(np.float32)
    body *= 0.92 + 0.08 * speck

    sprite = np.clip(body, 0.0, 1.0).astype(np.float32)
    _sprite_cache[key] = sprite
    return sprite


def _stamp_sprite(
    brush: str, variant: int, length: int, width: int, angle_deg: float
) -> np.ndarray:
    """Rotated, scaled sprite alpha in [0,1]; cached by quantized size/angle."""
    length = max(2, length)
    width = max(1, width)
    angle_bin = int(round(angle_deg / _ANGLE_BIN)) % int(360 / _ANGLE_BIN)
    key = (brush, variant, length, width, angle_bin)
    cached = _sprite_cache.get(key)
    if cached is not None:
        return cached

    base = _base_sprite(brush, variant)
    img = Image.fromarray((base * 255).astype("uint8"))
    img = img.resize((length, width), Image.Resampling.BILINEAR)
    rot = img.rotate(angle_bin * _ANGLE_BIN, expand=True, resample=Image.Resampling.BILINEAR)
    sprite = np.asarray(rot, dtype=np.float32) / 255.0
    if len(_sprite_cache) > 4096:
        _sprite_cache.clear()
    _sprite_cache[key] = sprite
    return sprite


# ---------------------------------------------------------------------------
# Canvas tooth / grain
# ---------------------------------------------------------------------------

_tooth_cache: dict[tuple[int, int], np.ndarray] = {}


def canvas_tooth(width: int, height: int) -> np.ndarray:
    """Multi-octave canvas texture in [0,1], shape (height, width)."""
    key = (width, height)
    cached = _tooth_cache.get(key)
    if cached is not None:
        return cached

    rng = np.random.default_rng(2718)
    tooth = np.zeros((height, width), dtype=np.float32)
    for cell, weight in ((3, 0.5), (7, 0.3), (17, 0.2)):
        coarse = rng.random((max(2, height // cell), max(2, width // cell)))
        layer = (
            np.asarray(
                Image.fromarray((coarse * 255).astype("uint8")).resize(
                    (width, height), Image.Resampling.BILINEAR
                ),
                dtype=np.float32,
            )
            / 255.0
        )
        tooth += weight * layer

    # Woven thread pattern, very subtle.
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    weave = 0.5 + 0.25 * np.sin(xx * (2 * math.pi / 4.3)) + 0.25 * np.sin(yy * (2 * math.pi / 4.7))
    tooth = 0.82 * tooth + 0.18 * weave

    tooth -= tooth.min()
    tooth /= max(1e-6, float(tooth.max()))
    _tooth_cache[key] = tooth.astype(np.float32)
    return tooth


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _resample(
    points: list[tuple[float, float]], spacing: float, max_stamps: int = 700
) -> list[tuple[float, float, float]]:
    """Resample a polyline to (x, y, angle_deg) stamps at even arc length."""
    if len(points) < 2:
        if points:
            x, y = points[0]
            return [(x, y, 0.0)]
        return []
    pts = np.asarray(points, dtype=np.float32)
    seg = np.diff(pts, axis=0)
    seg_len = np.hypot(seg[:, 0], seg[:, 1])
    total = float(seg_len.sum())
    spacing = max(spacing, total / max_stamps, 0.75)
    n = max(2, int(total / spacing) + 1)
    targets = np.linspace(0.0, total, n)
    cum = np.concatenate([[0.0], np.cumsum(seg_len)])

    out: list[tuple[float, float, float]] = []
    j = 0
    for t in targets:
        while j < len(seg_len) - 1 and cum[j + 1] < t:
            j += 1
        denom = max(1e-6, seg_len[j])
        f = (t - cum[j]) / denom
        x = pts[j, 0] + seg[j, 0] * f
        y = pts[j, 1] + seg[j, 1] * f
        angle = math.degrees(math.atan2(-seg[j, 1], seg[j, 0]))
        out.append((float(x), float(y), angle))
    return out


def _smooth_noise(rng: random.Random, n: int, scale: float) -> list[float]:
    """Low-frequency multiplicative noise around 1.0."""
    if n <= 0:
        return []
    knots = max(2, n // 6)
    vals = [rng.uniform(-1.0, 1.0) for _ in range(knots)]
    out = []
    for i in range(n):
        t = i / max(1, n - 1) * (knots - 1)
        k = min(int(t), knots - 2)
        f = t - k
        f = f * f * (3 - 2 * f)
        v = vals[k] * (1 - f) + vals[k + 1] * f
        out.append(1.0 + v * scale)
    return out


def _taper_profile(t: float, taper: float) -> float:
    """Width multiplier along the stroke; tapers at both ends."""
    head = min(1.0, t / 0.18) if t < 0.18 else 1.0
    tail = min(1.0, (1.0 - t) / 0.30) if t > 0.70 else 1.0
    ease = head * (0.4 + 0.6 * head) if t < 0.18 else tail * (0.4 + 0.6 * tail) if t > 0.70 else 1.0
    return 1.0 - taper * (1.0 - ease)


def _jitter_color(
    rgb: tuple[int, int, int], rng: random.Random, dyn: BrushDynamics
) -> tuple[float, float, float]:
    """Per-stamp broken color: jitter in HSV space, returns floats 0-255."""
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    h = (h + rng.uniform(-dyn.hue_jitter, dyn.hue_jitter)) % 1.0
    s = min(1.0, max(0.0, s + rng.uniform(-dyn.sat_jitter, dyn.sat_jitter) * (0.3 + s)))
    v = min(1.0, max(0.0, v + rng.uniform(-dyn.val_jitter, dyn.val_jitter)))
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (r * 255, g * 255, b * 255)


# ---------------------------------------------------------------------------
# Paint surface
# ---------------------------------------------------------------------------


class PaintSurface:
    """Accumulates painterly strokes plus a paint-height map for impasto."""

    def __init__(self, image: Image.Image) -> None:
        self.image = image  # RGBA, composited in place
        self.height_map = np.zeros((image.height, image.width), dtype=np.float32)
        self.tooth = canvas_tooth(image.width, image.height)
        self._painted = False

    def stroke(
        self,
        points: list[tuple[float, float]],
        rgba: tuple[int, int, int, int],
        stroke_width: float,
        brush: str | None,
    ) -> None:
        """Stamp a brush stroke onto the surface."""
        if len(points) < 2 or rgba[3] <= 0:
            return
        dyn = get_dynamics(brush)
        brush_key = brush or "oil_round"
        width = max(1.5, float(stroke_width))

        seed = (int(sum(x * 17.0 + y * 31.0 for x, y in points)) ^ int(width * 7)) & 0xFFFFFFFF
        rng = random.Random(seed)

        stamps = _resample(points, spacing=max(1.0, width * dyn.spacing))
        n = len(stamps)
        if n == 0:
            return
        wobble = _smooth_noise(rng, n, dyn.width_wobble)

        # Short marks (dabs) should not taper or deplete like long strokes.
        length_factor = min(1.0, n / 10.0)
        taper = dyn.taper * length_factor
        load_fade = dyn.load_fade * length_factor

        # Per-stamp alpha calibrated so accumulated coverage approximates
        # the requested stroke opacity despite stamp overlap.
        overlap = max(1.0, dyn.aspect / dyn.spacing * 0.45)
        target = min(0.985, (rgba[3] / 255) * dyn.opacity_scale)
        stamp_alpha = 1.0 - (1.0 - target) ** (1.0 / overlap)

        # Stroke bounding box with margin.
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        margin = width * dyn.aspect * 0.8 + 4
        x0 = max(0, int(min(xs) - margin))
        y0 = max(0, int(min(ys) - margin))
        x1 = min(self.image.width, int(max(xs) + margin) + 1)
        y1 = min(self.image.height, int(max(ys) + margin) + 1)
        if x1 <= x0 or y1 <= y0:
            return
        lw, lh = x1 - x0, y1 - y0

        layer_rgb = np.zeros((lh, lw, 3), dtype=np.float32)  # premultiplied
        layer_a = np.zeros((lh, lw), dtype=np.float32)

        base_rgb = (rgba[0], rgba[1], rgba[2])
        for i, (sx, sy, angle) in enumerate(stamps):
            t = i / max(1, n - 1)
            w_i = width * _taper_profile(t, taper) * wobble[i]
            if w_i < 0.6:
                continue
            len_i = w_i * dyn.aspect

            # Paint load: full at the start, depleting toward the end.
            load = 1.0 - load_fade * (t**1.3) * rng.uniform(0.7, 1.0)
            a_i = stamp_alpha * load
            if dyn.wet_edge > 0 and (t < 0.08 or t > 0.92):
                a_i = min(1.0, a_i * (1.0 + dyn.wet_edge))
            if a_i <= 0.004:
                continue

            variant = (seed + i * 7) % _SPRITE_VARIANTS
            # Slight oversize compensates for the sprite's soft edge falloff
            # so a stroke's painted body matches its requested width.
            sprite = _stamp_sprite(
                brush_key, variant, int(len_i * 1.1) + 1, max(1, int(w_i * 1.1) + 1), angle
            )
            sh, sw = sprite.shape
            px = round(sx - sw / 2) - x0
            py = round(sy - sh / 2) - y0
            sx0, sy0 = max(0, px), max(0, py)
            sx1, sy1 = min(lw, px + sw), min(lh, py + sh)
            if sx1 <= sx0 or sy1 <= sy0:
                continue
            sub = sprite[sy0 - py : sy1 - py, sx0 - px : sx1 - px]

            alpha = sub * a_i
            if dyn.dryness > 0:
                tooth = self.tooth[y0 + sy0 : y0 + sy1, x0 + sx0 : x0 + sx1]
                # Dry stamps skip the valleys of the canvas tooth.
                dry = dyn.dryness * (0.5 + 0.5 * (1.0 - load))
                alpha = alpha * np.clip(1.0 - dry * (1.6 - 2.0 * tooth), 0.0, 1.0)

            cr, cg, cb = _jitter_color(base_rgb, rng, dyn)
            # src-over composite (premultiplied)
            inv = 1.0 - alpha
            region_a = layer_a[sy0:sy1, sx0:sx1]
            region_rgb = layer_rgb[sy0:sy1, sx0:sx1]
            region_rgb[:, :, 0] = cr * alpha + region_rgb[:, :, 0] * inv
            region_rgb[:, :, 1] = cg * alpha + region_rgb[:, :, 1] * inv
            region_rgb[:, :, 2] = cb * alpha + region_rgb[:, :, 2] * inv
            layer_a[sy0:sy1, sx0:sx1] = alpha + region_a * inv

        if float(layer_a.max()) <= 0.0:
            return

        # Un-premultiply into an RGBA crop and optionally blur.
        safe_a = np.maximum(layer_a, 1e-5)[:, :, None]
        crop = np.empty((lh, lw, 4), dtype=np.uint8)
        crop[:, :, :3] = np.clip(layer_rgb / safe_a, 0, 255).astype(np.uint8)
        crop[:, :, 3] = np.clip(layer_a * 255, 0, 255).astype(np.uint8)
        layer_img = Image.fromarray(crop, "RGBA")
        if dyn.blur > 0:
            layer_img = layer_img.filter(ImageFilter.GaussianBlur(radius=dyn.blur))
            layer_a_arr = np.asarray(layer_img, dtype=np.float32)[:, :, 3] / 255.0
        else:
            layer_a_arr = layer_a

        self.image.alpha_composite(layer_img, (x0, y0))
        if dyn.impasto > 0:
            self.height_map[y0:y1, x0:x1] += layer_a_arr * dyn.impasto
        self._painted = True

    def add_fill_height(self, x0: int, y0: int, alpha: np.ndarray, amount: float = 0.08) -> None:
        """Optionally give filled shapes a faint paint body."""
        h, w = alpha.shape
        self.height_map[y0 : y0 + h, x0 : x0 + w] += alpha * amount

    def finish(self) -> Image.Image:
        """Apply impasto lighting and canvas grain; return RGB image."""
        rgb = np.asarray(self.image.convert("RGB"), dtype=np.float32)

        if self._painted:
            # Impasto: light from upper-left raking across paint relief.
            height = (
                np.asarray(
                    Image.fromarray(np.clip(self.height_map * 40, 0, 255).astype("uint8")).filter(
                        ImageFilter.GaussianBlur(radius=1.4)
                    ),
                    dtype=np.float32,
                )
                / 255.0
            )
            gy, gx = np.gradient(height)
            shade = 1.0 + np.clip((gx + gy) * -2.2, -0.10, 0.12)
            rgb *= shade[:, :, None]

            # Canvas grain: subtle everywhere, stronger where paint is thin.
            thin = np.clip(1.0 - self.height_map * 0.8, 0.25, 1.0)
            grain = 1.0 + (self.tooth - 0.5) * 0.075 * thin
            rgb *= grain[:, :, None]

        return Image.fromarray(np.clip(rgb, 0, 255).astype("uint8"), "RGB")
