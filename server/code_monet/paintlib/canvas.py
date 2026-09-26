"""Pixel painting canvas: real paint operations, stage keyframes, and a reveal log.

API REFERENCE. Coordinates are pixels, origin top-left. Colors: "#rrggbb", 0-255 ints,
or 0-1 floats. A "mask" is an HxW float array 0..1 (combine with *, np.maximum, 1 - m).
An "angles" field is an HxW array of stroke directions in radians (0 = right,
pi/2 = down). `cv.xx`, `cv.yy` are pixel-coordinate grids for numpy design fields.

Names in scope: cv, W, H, np, ndi (scipy.ndimage), math, random, rgb, fbm, value_noise,
cellular, smoothstep, mix, HUMAN_STROKES. Everything else below is a cv method
(cv.soften, cv.poly_mask, cv.sample_points, ...).

Workflow: design value/color fields ("guides") with numpy, then paint them in passes
like a painter: ground -> thin lay-in -> big masses -> forms -> detail -> glazes/accents.
In a painting program `cv` = Canvas(W, H, seed) already exists and is exported for you.

    cv.stage("ground"); cv.ground("#d8c8a8", weave=0.5)
    cv.stage("sky")
    sky = cv.rect_mask(0, 0, cv.W, 520)
    guide = cv.vgradient([(0, "#5d7390"), (520, "#e8d9b4")])
    cv.fill(sky, guide, alpha=0.8)                                # thin lay-in
    cv.paint_region(sky, 1500, guide, angle=0.1, dry=0.5)        # brushwork from the guide
    ...
    cv.sign(cv.W - 90, cv.H - 30)

Stages
  stage(label)   Start a painter's pass; viewers watch each pass paint in, stroke by
                 stroke. Use 4-10 stages named as a painter would ("sky", "figures").
                 Long stages auto-split every 2500 marks into extra keyframes of the
                 same label (layered reveal); the export summary lists each label once.

Surface (plain attributes: set them, e.g. cv.impasto = 0.4)
  ground(color, mottle=.03, weave=.5)   Prime the canvas; weave 0 smooth panel .. 1 linen.
  cv.impasto  Raking-light relief strength: 1.0 thick oil (Turner), 0.3-0.5 flat-brush
              oil (Cezanne), 0-0.2 acrylic/poster.
  cv.light    (dx, dy) light direction, default (-.65, -.6) = upper left.
  cv.varnish  RGB multiplier on the finished image (warm old varnish ~[1, .98, .92]).
  cv.rgb (HxWx3 float 0..1) and cv.height (HxW relief) are writable numpy arrays;
  direct edits are revealed as one area wipe at the end of the stage.
  Paint body follows value: light colors deposit more impasto than darks.

Masks (HxW float 0..1)
  poly_mask(pts, wobble=0)        Anti-aliased polygon; wobble=px -> hand-cut edge.
  rect_mask(x0, y0, x1, y1)       ellipse_mask(cx, cy, rx, ry, soft=1)  (soft ~ r: blob)
  line_mask(pts, width)           Constant-width polyline (masts, wires, bands).
  ribbon_mask(pts, widths)        Tapered band along a path (trunks, fronds, rivers).
  below_curve_mask(ys, feather=1) Below a per-column curve (horizons, ridges, shores).
  iso_mask(field, level, width)   Line along a field's level set (water-light nets,
                                  ripples, contour hatching); width may be an HxW array.
  soften(mask, px)                Feather edges (lost edges, atmosphere).
  rough_edge(mask, amount=4, scale=12)  Noisy, hand-painted edge; only a band ~amount
                                  px around the edge changes.
  wobble(pts, amp, freq=.02)      Densify + displace a path (changes the point count).
  ribbon/limb widths: a number, a (start, end) pair, or a list of any length
  (interpolated along the path).
  sample_points(mask, n, seed=None) -> (n, 2) float x, y drawn with probability
                                  proportional to mask (starts for traced strokes,
                                  knife touches, scattered figures).

Fields
  vgradient([(y, color), ...])   radial(cx, cy, r, inner, outer, squash=1)   -> HxWx3
  vortex_angles(cx, cy, squash=1, inward=.3, clockwise=False, rotation=0)  swirling
                 directions; squash>1 = elliptical, rotation (radians) tilts the ellipse.
  contour_angles(field, sigma=6)  directions along level lines (form-following strokes)
  trace(x, y, angles, length, step=4, bend=0, offset=0) -> (N, 2) path moving forward
                 along the field (angles + np.pi to go backward); offset = constant turn
                 (radians) each step, drifting across the flow; bend = turn accumulated
                 over the length (curling tails).
  smear_field(field, angles, length=24)  a design field (HxW or HxWx3) dragged along a
                                  field; paints nothing (swirling masks/guides)
Noise and helpers (bare names)
  fbm(shape, cell, octaves=4, seed=0, aniso=(1, 1))  fractal noise in [0, 1], mean ~.5.
  value_noise(shape, cell, seed, aniso=(1, 1))       smooth noise in [0, 1].
           aniso=(ax, ay) stretches features: (8, 1) horizontal grain/water/streaky sky.
  cellular(shape, cell, seed=0, aniso=(1, 1), return_id=False) -> (f1, edge) in px:
           Worley cells. edge < 1.5 = crack/lead-line/water-light net; 1 - f1/cell =
           cobbles, scales; return_id adds a cell id (patchwork fields).
  smoothstep(a, b, x) 0->1 ramp from a to b; a > b gives the inverse ramp (1->0).
  mix(a, b, t) colors, images or "#hex"; HxW t broadcasts over RGB.   rgb(color)

Area paint (one op each; fast; lay masses, then break them up with brushwork)
  fill(mask, color, alpha=1, mottle=.015, streak=.006, grain=.008, rim=0, thick=0)
        Opaque flat paint (acrylic, gouache, poster planes); color may be HxWx3.
        rim .05-.1: paint pooled against a taped edge. Set mottle=streak=grain=0 for
        a clean underlayer.
  glaze(mask, tint, alpha=1, mottle=0)   Transparent multiply (shadows, unifying color).
  wash(mask, color, alpha=.5, bloom=0)   Translucent veil/scumble/glow; bloom=watercolor.
  blur(mask, sigma)          Soften paint and relief (distance, mist, a melted eye of light).
  smear(mask, angles, length=24)   Drag wet paint and relief along a field (wet-into-
                             wet; storms, water, fur). angles may be a scalar.
  striate(mask, angles, amount=.04, relief=.1, length=18)   Combed bristle texture in
                             color and relief; puts "paint" back into smooth passages.
  crackle(amount=.05, cell=10, aspect=2.2)   Old-master craquelure over everything.

Brushes (each mark is recorded as a brush stroke for the reveal)
  stroke(pts, width, color, alpha=.9, dry=0, pickup=.2, thick=.4, taper=.4, streak=.3,
         knife=False, glaze=False, clip=None)
        Round bristle brush along a polyline. dry 0 loaded .. 1 catches only the tooth;
        pickup drags wet paint from below; taper 0 blunt .. 1 pointed; knife = flat
        hard-edged scrape (lights, foam); glaze = transparent multiply; clip = mask.
  dab(x, y, angle, length, width, color, alpha=.9, dry=.3, pickup=.12, thick=.5,
      curve=0, clip=None, tip="flat")
        One flat-brush mark: square end, bristle streaks (stronger when dry), paint
        breaking up on the tooth toward the tail. tip="round": filbert touch.
  paint_region(region, count, color, angle=0, length=(20, 60), width=(6, 16),
               alpha=.85, brush="dab", jitter=.03, angle_jitter=.12, dry=.3,
               pickup=.15, thick=.45, curve=.1, leak=0, seed=None, group=(3, 5),
               overlap=.85, tip="flat", chroma=None, scale=1) -> marks laid
        The workhorse. `count` marks spread evenly over `region` (a soft region is a
        density map); `count` is total marks, also for "patch" (count / ~4 groups).
        color: one color | HxWx3 guide sampled under each mark |
        fn(x, y, rng). angle: radians | HxW field | fn(x, y, rng).
        brush: "dab" flat marks | "patch" Cezanne constructive groups of `group`
        parallel dabs sharing one modulated color | "flow" long strokes following an
        angle field (skies, water, hair, grass; color taken mid-stroke).
        alpha and dry may be (lo, hi) ranges. jitter = per-mark value variation,
        chroma = hue variation (default jitter*.35; .01-.02 for calm, .03+ lively).
        leak: marks always start inside the region; 0 clips them hard at its edge,
        1 lets them run past, so the edge is formed by stroke ends (foliage clumps,
        clouds, bushes, broken coastlines). scale: number or HxW
        field multiplying mark size (perspective: smaller toward the horizon).
        Sizes: dab (20,60)x(6,16); patch (22,40)x(8,12); flow (60,260)x(8,40), broad
        sweeps (220,520)x(45,95). Coverage: count ~ 1.5 * area / (mean len * mean wid).
  contour(pts, width, color, alpha=.7, gap=.25, drift=1.5, pressure=.7)   Broken,
        searching contour (Cezanne's blue outlines); gap=0 continuous; pressure 0 even
        .. 1 each run lands thin, swells and lifts off.

Crisp shapes (figures, animals, boats, buildings, windows, birds, masts, lettering)
  shape(polys=[(pts, color)], lines=[(pts, width, color)],
        ellipses=[(cx, cy, rx, ry, color)], limbs=[(pts, widths, color)],
        parts=[("poly", pts, c) | ("line", pts, w, c) | ("limb", pts, widths, c) |
               ("ellipse", cx, cy, rx, ry, c) | ("rect", x0, y0, x1, y1, c)],
        alpha=1, model=0, texture=.02, thick=0, reflect=0, reflect_y=None,
        reflect_clip=None, clip=None, return_mask=False)
        One supersampled opaque unit. Lists draw in the order polys, limbs, lines,
        ellipses, then `parts` in the given order (use parts for figures: body, then
        lit side, then head, then hat). model .3-.5 rounds the form with light from the
        upper left. reflect .2-.4 adds a dim mirrored copy below reflect_y (default: the
        unit's lowest point), clipped to reflect_clip (water/ice mask). clip = mask
        it may paint into (taped border); return_mask=True returns its HxW coverage
        (glaze, texture or shadow the shape afterwards).
  sign(x, y, size=36)    The artist's "CM" monogram (left edge x, baseline y).

Output
  finished()        The painting as shown (relief lit by raking light, varnish).
  export(out_dir)   Close the last stage; write kf_NN.jpg, final.png, preview.jpg,
                    reveal.json; returns {"width", "height", "stages", "ops"}.

Speed at 1600x1200 (per op): dab ~.1-.3 ms, flow stroke ~1 ms, broad stroke ~4 ms,
fill/glaze/wash ~.1-.3 s, full-canvas smear ~.6 s, striate ~.7 s, crackle ~.8 s.
20k-30k marks render in ~10-20 s.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from .noise import cellular, fbm, smoothstep, value_noise

ColorLike = str | Sequence[float] | np.ndarray
Points = Sequence[Sequence[float]] | np.ndarray
ColorSpec = ColorLike | Callable[[float, float, np.random.Generator], ColorLike]
AngleSpec = float | np.ndarray | Callable[[float, float, np.random.Generator], float]

# Auto-split long stages so the reveal shows paint layering, not one jump.
_OPS_PER_KEYFRAME = 2500
_MAX_KEYFRAMES = 40
_MAX_REVEAL_POINTS = 8
_BRISTLE_BANK = 24


def rgb(color: ColorLike) -> np.ndarray:
    """Normalize a color to float32 RGB in [0, 1].

    Accepts "#rrggbb", ints 0-255, or floats 0-1.
    """
    if isinstance(color, str):
        s = color.lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        return np.array([int(s[i : i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0
    arr = np.asarray(color, np.float32)
    if arr.shape[-1] != 3:
        raise ValueError(f"color must have 3 channels, got shape {arr.shape}")
    if arr.ndim == 1 and np.issubdtype(np.asarray(color).dtype, np.integer):
        return arr / 255.0
    if arr.ndim == 1 and arr.max() > 1.0:
        return arr / 255.0
    return arr


@dataclass
class _Stage:
    label: str
    ops: list[list[Any]] = field(default_factory=list)


class Canvas:
    """A painting surface of W x H pixels (`rgb` float32 HxWx3, `height` impasto map)."""

    def __init__(self, width: int, height: int, seed: int = 0) -> None:
        self.W, self.H = int(width), int(height)
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.yy, self.xx = np.mgrid[0 : self.H, 0 : self.W].astype(np.float32)
        self.rgb = np.full((self.H, self.W, 3), 0.93, np.float32)
        self.height = np.zeros((self.H, self.W), np.float32)
        self._tooth: np.ndarray | None = None
        self.light = (-0.65, -0.6)  # raking light from upper left
        self.impasto = 1.0
        self.varnish = np.array([1.0, 0.985, 0.95], np.float32)
        self._stages: list[_Stage] = [_Stage("start")]
        self._keyframes: list[tuple[str, np.ndarray, list[list[Any]]]] = []
        self._last_snapshot = self.rgb.copy()
        self._bristle_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}

    # ------------------------------------------------------------------ setup

    @property
    def tooth(self) -> np.ndarray:
        """Canvas tooth (HxW 0..1): what dry brush and thin paint catch."""
        if self._tooth is None:
            self._tooth = self._make_tooth(0.5)
        return self._tooth

    @tooth.setter
    def tooth(self, value: np.ndarray) -> None:
        self._tooth = np.asarray(value, np.float32)

    def _make_tooth(self, weave: float) -> np.ndarray:
        shape = (self.H, self.W)
        p = 3.8
        warp = 5.0 * (value_noise(shape, 30, self.seed + 97) - 0.5)
        wx = np.sin((self.xx + warp) * 2 * np.pi / p)
        wy = np.sin((self.yy - warp) * 2 * np.pi / p)
        cloth = 0.5 + 0.25 * np.where(wy > 0, wx, wy)
        irregular = 0.6 * value_noise(shape, 2.5, self.seed + 96, order=1) + 0.4 * value_noise(
            shape, 9, self.seed + 95
        )
        return np.clip(weave * cloth + (1 - weave) * irregular, 0, 1).astype(np.float32)

    def ground(self, color: ColorLike, mottle: float = 0.03, weave: float = 0.5) -> None:
        """Prime the whole canvas with a colored ground and set the canvas tooth.

        weave: 0 = smooth panel/paper tooth, 1 = strong woven canvas.
        """
        self.tooth = self._make_tooth(weave)
        base = rgb(color)
        m = fbm((self.H, self.W), 180, 3, self.seed + 7) - 0.5
        self.rgb[:] = base * (1 + mottle * m[..., None] * 2)
        self.height[:] = 0
        self._record(["a", 0, 0, self.W, self.H])

    # ------------------------------------------------------------------ stages

    def stage(self, label: str) -> None:
        """Start a new painting pass (e.g. "ground", "big masses", "figures", "glazes").

        Viewers watch each pass paint in; name them as a painter would.
        """
        self._close_stage()
        self._stages.append(_Stage(label))

    def _record(self, op: list[Any]) -> None:
        st = self._stages[-1]
        st.ops.append(op)
        if len(st.ops) >= _OPS_PER_KEYFRAME:
            self._close_stage()
            self._stages.append(_Stage(st.label))

    def _close_stage(self) -> None:
        st = self._stages[-1]
        changed = np.abs(self.rgb - self._last_snapshot).max(axis=2) > 0.004
        any_change = bool(changed.any())
        if not st.ops and not any_change:
            return
        if any_change and not st.ops:
            ys, xs = np.nonzero(changed)
            st.ops.append(["a", int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1])
        self._keyframes.append((st.label, self.finished(), st.ops))
        self._last_snapshot = self.rgb.copy()
        st.ops = []

    # ------------------------------------------------------------------ masks

    def _raster(
        self,
        draw: Callable[[ImageDraw.ImageDraw, Callable[[float, float], tuple[float, float]]], None],
        box: tuple[float, float, float, float],
        ss: int,
    ) -> np.ndarray:
        """Supersample a PIL drawing inside `box` and return a full-size mask."""
        out = np.zeros((self.H, self.W), np.float32)
        x0 = max(0, int(math.floor(box[0])) - 2)
        y0 = max(0, int(math.floor(box[1])) - 2)
        x1 = min(self.W, int(math.ceil(box[2])) + 3)
        y1 = min(self.H, int(math.ceil(box[3])) + 3)
        if x1 <= x0 or y1 <= y0:
            return out
        pw, ph = x1 - x0, y1 - y0
        im = Image.new("L", (pw * ss, ph * ss), 0)

        def P(px: float, py: float) -> tuple[float, float]:
            return ((px - x0) * ss, (py - y0) * ss)

        draw(ImageDraw.Draw(im), P)
        a = np.asarray(im, np.float32).reshape(ph, ss, pw, ss).mean((1, 3)) / 255.0
        out[y0:y1, x0:x1] = a
        return out

    def poly_mask(self, pts: Points, ss: int = 3, wobble: float = 0.0, seed: int = 0) -> np.ndarray:
        """Anti-aliased polygon mask (HxW float 0..1).

        wobble: displace the outline by ~this many px for a hand-cut/painted edge.
        """
        p = np.asarray(pts, np.float64).reshape(-1, 2)
        if wobble:
            p = self.wobble(p, wobble, seed=self.seed * 31 + seed, closed=True)
        if len(p) < 3:
            return np.zeros((self.H, self.W), np.float32)
        box = (p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max())
        return self._raster(lambda d, P: d.polygon([P(x, y) for x, y in p], fill=255), box, ss)

    def ellipse_mask(
        self, cx: float, cy: float, rx: float, ry: float, soft: float = 1.0
    ) -> np.ndarray:
        """Ellipse mask; soft = edge feather in px (soft ~ radius gives a soft blob)."""
        out = np.zeros((self.H, self.W), np.float32)
        rx, ry = max(rx, 1e-3), max(ry, 1e-3)
        edge = soft / max(min(rx, ry), 1e-3)
        grow = 1 + 0.5 * max(edge, 1e-4)
        x0, x1 = max(0, int(cx - rx * grow) - 2), min(self.W, int(cx + rx * grow) + 3)
        y0, y1 = max(0, int(cy - ry * grow) - 2), min(self.H, int(cy + ry * grow) + 3)
        if x1 <= x0 or y1 <= y0:
            return out
        d = np.sqrt(
            ((self.xx[y0:y1, x0:x1] - cx) / rx) ** 2 + ((self.yy[y0:y1, x0:x1] - cy) / ry) ** 2
        )
        out[y0:y1, x0:x1] = np.clip((1 - d) / max(edge, 1e-4) + 0.5, 0, 1)
        return out

    def rect_mask(self, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
        """Axis-aligned rectangle mask (anti-aliased edges)."""
        return self.poly_mask([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    def line_mask(self, pts: Points, width: float, ss: int = 3) -> np.ndarray:
        """Constant-width polyline mask with round joints."""
        p = np.asarray(pts, np.float64).reshape(-1, 2)
        if len(p) < 2:
            return np.zeros((self.H, self.W), np.float32)
        w = width / 2 + 1
        box = (p[:, 0].min() - w, p[:, 1].min() - w, p[:, 0].max() + w, p[:, 1].max() + w)
        return self._raster(
            lambda d, P: d.line(
                [P(x, y) for x, y in p],
                fill=255,
                width=max(1, int(round(width * ss))),
                joint="curve",
            ),
            box,
            ss,
        )

    def ribbon_mask(
        self, pts: Points, widths: float | Sequence[float] | np.ndarray, ss: int = 3
    ) -> np.ndarray:
        """Tapered band along a path (trunks, fronds, limbs, rivers).

        widths: one value, a (start, end) pair, or a list of any length, interpolated
        along the path (safe after wobble() changes the point count).
        """
        poly = _ribbon(np.asarray(pts, np.float64).reshape(-1, 2), widths)
        if poly is None:
            return np.zeros((self.H, self.W), np.float32)
        return self.poly_mask(poly, ss=ss)

    def below_curve_mask(self, ys: np.ndarray, feather: float = 1.0) -> np.ndarray:
        """Mask of pixels below a per-column curve `ys` (len W): ridgelines, horizons, shores."""
        ys = np.asarray(ys, np.float32)[None, :]
        return np.clip((self.yy - ys) / max(feather, 1e-3) + 0.5, 0, 1).astype(np.float32)

    @staticmethod
    def iso_mask(field_: np.ndarray, level: float, width: float | np.ndarray) -> np.ndarray:
        """Anti-aliased line along field == level, `width` px wide (may be an HxW array)."""
        f = np.asarray(field_, np.float32)
        gy, gx = np.gradient(f)
        dist = np.abs(f - level) / (np.hypot(gx, gy) + 1e-6)
        return np.clip(np.asarray(width, np.float32) / 2 - dist + 0.5, 0, 1).astype(np.float32)

    @staticmethod
    def soften(mask: np.ndarray, px: float) -> np.ndarray:
        """Feather a mask's edge by roughly `px` pixels (lost edges, atmosphere)."""
        return ndi.gaussian_filter(mask.astype(np.float32), px / 2)

    def rough_edge(
        self, mask: np.ndarray, amount: float = 4.0, scale: float = 12.0, seed: int = 0
    ) -> np.ndarray:
        """Displace a mask's edge by ~`amount` px of noise so it reads as hand-painted.

        Only a band around the original edge changes; the rest of the mask is kept.
        """
        m = np.clip(np.asarray(mask, np.float32), 0, 1)
        out = m.copy()
        reach = amount * 1.5 + 3
        wide = ndi.gaussian_filter(m, reach / 2)
        band = (wide > 0.01) & (wide < 0.99)
        box = _bbox(band.astype(np.float32))
        if box is None:
            return out
        x0, y0, x1, y1 = box
        sub = (slice(y0, y1), slice(x0, x1))
        n = fbm((y1 - y0, x1 - x0), scale, 3, self.seed + 500 + seed) - 0.5
        d = ndi.gaussian_filter(m, 1.0)[sub]
        noisy = np.clip((d - 0.5) * 3 + 0.5 + n * amount * 0.25, 0, 1)
        w = smoothstep(0.01, 0.12, wide[sub]) * smoothstep(0.99, 0.88, wide[sub])
        out[sub] = m[sub] * (1 - w) + noisy * w
        return out.astype(np.float32)

    @staticmethod
    def wobble(
        pts: Points, amp: float, freq: float = 0.02, seed: int = 0, closed: bool = False
    ) -> np.ndarray:
        """Densify a polyline (every ~4 px) and displace it by smooth noise of ~`amp` px.

        freq: wobbles per px of outline (0.02 = a gentle wave every ~50 px).
        """
        p = np.asarray(pts, np.float64).reshape(-1, 2)
        if closed:
            p = np.vstack([p, p[:1]])
        seg = np.hypot(*np.diff(p, axis=0).T)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        if cum[-1] <= 0:
            return p
        n = max(4, int(cum[-1] / 4.0))
        s = np.linspace(0, cum[-1], n)
        d = np.stack([np.interp(s, cum, p[:, 0]), np.interp(s, cum, p[:, 1])], 1)
        r = np.random.default_rng(seed)
        k = max(4, int(cum[-1] * freq))
        ctrl = r.standard_normal((k + 3, 2))
        t = np.linspace(0, k, n)
        off = np.stack(
            [
                np.interp(t, np.arange(k + 3), ctrl[:, 0]),
                np.interp(t, np.arange(k + 3), ctrl[:, 1]),
            ],
            1,
        )
        off = off + 0.15 * r.standard_normal((n, 2))
        if closed:
            off[-1] = off[0]
        return (d + amp * off).astype(np.float64)

    def sample_points(self, mask: np.ndarray, n: int, seed: int | None = None) -> np.ndarray:
        """(n, 2) array of random (x, y) points, drawn with probability proportional to
        the mask value (a density map). Starts for traced strokes, knife touches, figures.
        """
        m = np.clip(np.asarray(mask, np.float64), 0, None).reshape(-1)
        total = m.sum()
        if n <= 0 or total <= 0:
            return np.zeros((0, 2), np.float32)
        r = np.random.default_rng(
            self.seed * 7919 + seed if seed is not None else int(self.rng.integers(1 << 30))
        )
        idx = r.choice(m.size, size=n, p=m / total)
        ys, xs = np.divmod(idx, self.W)
        return np.stack([xs + r.random(n), ys + r.random(n)], 1).astype(np.float32)

    # ------------------------------------------------------------------ gradients / fields

    def vgradient(self, stops: Sequence[tuple[float, ColorLike]]) -> np.ndarray:
        """Vertical color gradient (HxWx3). stops: [(y_px, color), ...]."""
        ys = np.array([s[0] for s in stops], np.float32)
        cols = np.stack([rgb(s[1]) for s in stops])
        y = self.yy[:, 0]
        out = np.stack([np.interp(y, ys, cols[:, c]) for c in range(3)], axis=1)
        return np.broadcast_to(out[:, None, :], (self.H, self.W, 3)).astype(np.float32).copy()

    def radial(
        self,
        cx: float,
        cy: float,
        radius: float,
        inner: ColorLike,
        outer: ColorLike,
        squash: float = 1.0,
    ) -> np.ndarray:
        """Radial color field (HxWx3) — light sources, vortices, halos."""
        d = np.sqrt((self.xx - cx) ** 2 + ((self.yy - cy) * squash) ** 2) / max(radius, 1e-3)
        t = smoothstep(0, 1, d)[..., None]
        return (rgb(inner) * (1 - t) + rgb(outer) * t).astype(np.float32)

    def vortex_angles(
        self,
        cx: float,
        cy: float,
        squash: float = 1.0,
        inward: float = 0.3,
        clockwise: bool = False,
        rotation: float = 0.0,
    ) -> np.ndarray:
        """Per-pixel stroke direction (radians) circling a center.

        squash > 1 flattens the vortex into an ellipse; rotation (radians) tilts that
        ellipse; inward > 0 spirals strokes toward the eye.
        """
        cr, sr = math.cos(rotation), math.sin(rotation)
        ex, ey = self.xx - cx, self.yy - cy
        dx = ex * cr + ey * sr
        dy = (-ex * sr + ey * cr) * squash
        sign = -1.0 if clockwise else 1.0
        fx = -dy * sign - inward * dx
        fy = (dx * sign - inward * dy) / squash
        return (np.arctan2(fy, fx) + rotation).astype(np.float32)

    def contour_angles(self, field_: np.ndarray, sigma: float = 6.0) -> np.ndarray:
        """Stroke direction running along the level lines of a scalar field (form-following)."""
        f = ndi.gaussian_filter(field_.astype(np.float32), sigma)
        gy, gx = np.gradient(f)
        return (np.arctan2(gy, gx) + np.pi / 2).astype(np.float32)

    def trace(
        self,
        x: float,
        y: float,
        angles: np.ndarray,
        length: float,
        step: float = 4.0,
        bend: float = 0.0,
        offset: float = 0.0,
    ) -> np.ndarray:
        """Polyline that follows a direction field from (x, y) — flowing brush paths.

        Each `step` px it moves along angles[y, x] (0 = +x/right, pi/2 = +y/down), i.e.
        forward along the field; use angles + np.pi to go backward. offset: constant turn
        (radians) added to every step (drift across the flow); bend: extra turn
        accumulated gradually over the length (curling tails). Returns an (N, 2) array.
        """
        n = max(2, int(length / step))
        pts = np.empty((n + 1, 2), np.float32)
        pts[0] = (x, y)
        wm, hm = self.W - 1, self.H - 1
        for i in range(n):
            xi = int(x) if 0 <= x <= wm else (0 if x < 0 else wm)
            yi = int(y) if 0 <= y <= hm else (0 if y < 0 else hm)
            a = float(angles[yi, xi]) + offset + bend * i / n
            x += math.cos(a) * step
            y += math.sin(a) * step
            pts[i + 1] = (x, y)
        return pts

    # ------------------------------------------------------------------ area paint

    def fill(
        self,
        mask: np.ndarray,
        color: ColorLike | np.ndarray,
        alpha: float = 1.0,
        mottle: float = 0.015,
        streak: float = 0.006,
        grain: float = 0.008,
        rim: float = 0.0,
        thick: float = 0.0,
    ) -> None:
        """Flat, opaque paint through a mask (acrylic/tempera/gouache planes, poster shapes).

        color: one color, or an HxWx3 array (gradient/field).
        mottle/streak/grain: hand-applied surface variation. rim: paint pooled
        against a taped edge (a faint darker line inside the boundary).
        """
        m = np.clip(mask * alpha, 0, 1).astype(np.float32)
        box = _bbox(m)
        if box is None:
            return
        x0, y0, x1, y1 = box
        mm = m[y0:y1, x0:x1][..., None]
        base = _color_field(color, self.H, self.W)[y0:y1, x0:x1]
        tex = self._surface_tex((y1 - y0, x1 - x0), mottle, streak, grain)
        if rim:
            sub = mask[y0:y1, x0:x1].astype(np.float32)
            edge = np.clip(sub - ndi.gaussian_filter(sub, 2.0), 0, 1) * 2
            tex = tex * (1 - rim * edge)
        region = self.rgb[y0:y1, x0:x1]
        region[:] = region * (1 - mm) + np.clip(base * tex[..., None], 0, 1) * mm
        h = self.height[y0:y1, x0:x1]
        h[:] = h * (1 - 0.6 * mm[..., 0]) + thick * mm[..., 0]
        self._record(["a", x0, y0, x1, y1])

    def _surface_tex(
        self, shape: tuple[int, int], mottle: float, streak: float, grain: float
    ) -> np.ndarray:
        s = int(self.rng.integers(1 << 30))
        tex = np.ones(shape, np.float32)
        if mottle:
            big = fbm(shape, 140, 2, s)
            small = value_noise(shape, 14, s + 3)
            tex = (tex + mottle * 2 * (0.75 * big + 0.25 * small - 0.5)).astype(np.float32)
        if streak:
            st = ndi.gaussian_filter(
                np.random.default_rng(s + 1).standard_normal(shape).astype(np.float32), (0.8, 10)
            )
            tex = tex + streak * st / (st.std() + 1e-6)
        if grain:
            tex = tex + grain * np.random.default_rng(s + 2).standard_normal(shape).astype(
                np.float32
            )
        return tex

    def glaze(
        self, mask: np.ndarray, tint: ColorLike, alpha: float = 1.0, mottle: float = 0.0
    ) -> None:
        """Transparent glaze: multiply the paint underneath by a tint (shadows, unifying color)."""
        m = np.clip(mask * alpha, 0, 1).astype(np.float32)
        box = _bbox(m)
        if box is None:
            return
        x0, y0, x1, y1 = box
        mm = m[y0:y1, x0:x1][..., None]
        t = _color_field(tint, self.H, self.W)[y0:y1, x0:x1]
        if mottle:
            t = t * self._surface_tex((y1 - y0, x1 - x0), mottle, 0.0, 0.004)[..., None]
        region = self.rgb[y0:y1, x0:x1]
        region[:] = region * (1 - mm) + region * t * mm
        self._record(["a", x0, y0, x1, y1])

    def wash(
        self,
        mask: np.ndarray,
        color: ColorLike | np.ndarray,
        alpha: float = 0.5,
        bloom: float = 0.0,
    ) -> None:
        """Thin translucent layer (scumble, veil, atmosphere, watercolor wash).

        bloom > 0 darkens the drying edge like watercolor.
        """
        m = np.clip(mask * alpha, 0, 1).astype(np.float32)
        box = _bbox(m)
        if box is None:
            return
        x0, y0, x1, y1 = box
        mm = m[y0:y1, x0:x1]
        if bloom:
            sub = mask[y0:y1, x0:x1].astype(np.float32)
            inner = ndi.gaussian_filter(sub, 3.0)
            mm = mm * (1 + bloom * np.clip(sub - inner, 0, 1) * 4)
        mm = np.clip(mm, 0, 1)[..., None]
        base = _color_field(color, self.H, self.W)[y0:y1, x0:x1]
        region = self.rgb[y0:y1, x0:x1]
        region[:] = region * (1 - mm) + base * mm
        self._record(["a", x0, y0, x1, y1])

    def blur(self, mask: np.ndarray, sigma: float) -> None:
        """Soften paint inside a mask (lost edges, distance, mist, motion)."""
        box = _bbox(mask)
        if box is None:
            return
        x0, y0, x1, y1 = _pad_box(box, int(sigma * 3), self.W, self.H)
        region = self.rgb[y0:y1, x0:x1]
        soft = ndi.gaussian_filter(region, (sigma, sigma, 0))
        mm = np.clip(mask[y0:y1, x0:x1], 0, 1)[..., None]
        region[:] = region * (1 - mm) + soft * mm
        h = self.height[y0:y1, x0:x1]
        h[:] = h * (1 - mm[..., 0]) + ndi.gaussian_filter(h, sigma) * mm[..., 0]
        self._record(["a", x0, y0, x1, y1])

    def _advect(
        self,
        src: np.ndarray,
        sel: tuple[np.ndarray, np.ndarray],
        angles: np.ndarray | float,
        length: float,
        step: float,
    ) -> np.ndarray:
        """Line-integral average of `src` (HxWxC) at pixels `sel`, along the angle field.

        Streamlines start from a fixed sub-pixel jitter and sample the nearest pixel;
        averaging many dithered samples is smooth and ~5x faster than bilinear taps.
        """
        ys, xs = sel
        wm, hm, w_ = self.W - 1, self.H - 1, self.W
        if np.ndim(angles) == 0:
            fxf = fyf = None
            cx, cy = math.cos(float(angles)) * step, math.sin(float(angles)) * step
        else:
            a = np.asarray(angles, np.float32).reshape(-1)
            fxf, fyf = np.cos(a) * np.float32(step), np.sin(a) * np.float32(step)
            cx = cy = 0.0
        c = src.shape[2]
        flat = np.ascontiguousarray(src, dtype=np.float32).reshape(-1, c)
        acc = flat[ys * w_ + xs].copy()
        wsum = 1.0
        n = max(1, int(length / step / 2))
        jr = np.random.default_rng(12345)
        jx = jr.random(len(xs), dtype=np.float32)
        jy = jr.random(len(xs), dtype=np.float32)
        for sgn in (1.0, -1.0):
            px = xs.astype(np.float32) + jx
            py = ys.astype(np.float32) + jy
            for k in range(1, n + 1):
                idx = np.clip(py, 0, hm).astype(np.int32) * w_ + np.clip(px, 0, wm).astype(np.int32)
                if fxf is None:
                    px += sgn * cx
                    py += sgn * cy
                else:
                    px += sgn * fxf[idx]
                    py += sgn * fyf[idx]  # type: ignore[index]
                w = math.exp(-2.0 * (k / n) ** 2)
                idx = np.clip(py, 0, hm).astype(np.int32) * w_ + np.clip(px, 0, wm).astype(np.int32)
                acc += w * flat[idx]
                wsum += w
        return acc / wsum

    def smear(
        self, mask: np.ndarray, angles: np.ndarray | float, length: float = 24.0, step: float = 2.5
    ) -> None:
        """Drag wet paint along a direction field (wet-into-wet blending, Turner's vortices)."""
        box = _bbox(mask)
        if box is None:
            return
        x0, y0, x1, y1 = box
        m = np.clip(mask, 0, 1)
        ys, xs = np.nonzero(m > 0.002)
        paint = np.concatenate([self.rgb, self.height[..., None]], axis=2)
        out = self._advect(paint, (ys, xs), angles, length, step)
        mm = m[ys, xs][:, None]
        self.rgb[ys, xs] = self.rgb[ys, xs] * (1 - mm) + out[:, :3] * mm
        self.height[ys, xs] = self.height[ys, xs] * (1 - mm[:, 0]) + out[:, 3] * mm[:, 0]
        self._record(["a", x0, y0, x1, y1])

    def smear_field(
        self,
        field_: np.ndarray,
        angles: np.ndarray | float,
        length: float = 24.0,
        step: float = 2.5,
    ) -> np.ndarray:
        """Return a copy of a design field (HxW or HxWx3) dragged along a direction field.

        Paints nothing: use it to shape masks and guides (a glaze mask that swirls with
        the storm, a guide image already blended wet-into-wet).
        """
        f = np.asarray(field_, np.float32)
        src = f[..., None] if f.ndim == 2 else f
        ys, xs = np.nonzero(np.ones((self.H, self.W), bool))
        out = self._advect(src, (ys, xs), angles, length, step).reshape(
            self.H, self.W, src.shape[2]
        )
        return out[..., 0] if f.ndim == 2 else out

    def striate(
        self,
        mask: np.ndarray,
        angles: np.ndarray | float,
        amount: float = 0.04,
        relief: float = 0.1,
        length: float = 18.0,
    ) -> None:
        """Bristle-drag texture along a direction field, in color and impasto relief.

        Lays the combed look of a loaded brush over smooth passages (after smear/fill).
        """
        box = _bbox(mask)
        if box is None:
            return
        x0, y0, x1, y1 = _pad_box(box, int(length * 2) + 2, self.W, self.H)
        s = int(self.rng.integers(1 << 30))
        sub = (slice(y0, y1), slice(x0, x1))
        noise = np.zeros((self.H, self.W, 2), np.float32)
        r = np.random.default_rng(s)
        noise[sub] = r.random((y1 - y0, x1 - x0, 2)).astype(np.float32)
        m = np.clip(mask, 0, 1)
        ys, xs = np.nonzero(m > 0.002)
        fine = self._advect(noise[..., :1], (ys, xs), angles, length * 1.6, 1.6)[:, 0]
        coarse = self._advect(noise[..., 1:], (ys, xs), angles, length * 2.0, 3.5)[:, 0]
        fine = (fine - fine.mean()) / (fine.std() + 1e-6)
        coarse = (coarse - coarse.mean()) / (coarse.std() + 1e-6)
        tex = (0.6 * fine + 0.4 * coarse) * m[ys, xs]
        self.rgb[ys, xs] *= (1 + amount * tex)[:, None]
        self.height[ys, xs] += relief * tex
        self._record(["a", *box])

    def crackle(
        self, amount: float = 0.05, cell: float = 10.0, aspect: float = 2.2, seed: int = 0
    ) -> None:
        """Craquelure: a fine network of dark age cracks over the whole painting.

        cell: crack-cell size in px; aspect > 1 stretches cells along the panel grain.
        Use 0.04-0.08 for an old-master panel; skip it for modern work.
        """
        _, edge = cellular(
            (self.H, self.W), cell, self.seed * 977 + seed, aniso=(aspect, 1.0), jitter=0.7
        )
        crack = np.exp(-((edge / 0.9) ** 2))
        patchy = 0.3 + 0.7 * smoothstep(
            0.35, 0.65, fbm((self.H, self.W), 240, 3, self.seed + 779 + seed)
        )
        lum = self.rgb.mean(axis=2)
        self.rgb *= (1 - amount * crack * patchy * (0.3 + lum))[..., None]
        self._record(["a", 0, 0, self.W, self.H])

    # ------------------------------------------------------------------ brushes

    def _bristles(self, n: int) -> tuple[np.ndarray, np.ndarray]:
        """Bank of per-mark bristle load profiles (smoothed, and raw for color), n bristles each."""
        bank = self._bristle_cache.get(n)
        if bank is None:
            r = np.random.default_rng(self.seed * 131 + n)
            raw = r.random((_BRISTLE_BANK, n)).astype(np.float32)
            sm = ndi.gaussian_filter1d(raw, 0.8, axis=1)
            lo, hi = sm.min(axis=1, keepdims=True), sm.max(axis=1, keepdims=True)
            sm = (sm - lo) / (hi - lo + 1e-6)
            bank = (sm.astype(np.float32), r.random((_BRISTLE_BANK, n)).astype(np.float32))
            self._bristle_cache[n] = bank
        return bank

    def stroke(
        self,
        pts: Points,
        width: float,
        color: ColorLike,
        alpha: float = 0.9,
        dry: float = 0.0,
        pickup: float = 0.2,
        thick: float = 0.4,
        taper: float = 0.4,
        streak: float = 0.3,
        knife: bool = False,
        glaze: bool = False,
        clip: np.ndarray | None = None,
    ) -> None:
        """Bristle brush (or palette knife) dragged along a polyline.

        dry: 0 loaded .. 1 dry brush that only catches the canvas tooth.
        pickup: wet paint underneath dragged into the stroke.
        thick: impasto deposited (lit by the raking light at the end).
        taper: 0 blunt .. 1 pointed ends.
        glaze: transparent multiply stroke instead of body color.
        knife: flat, hard-edged, square-ended smear.
        clip: optional mask limiting where the stroke lands.
        """
        p = np.asarray(pts, np.float32).reshape(-1, 2)
        if len(p) < 2 or width <= 0:
            return
        if self._stroke(
            p,
            float(width),
            rgb(color),
            alpha,
            dry,
            pickup,
            thick,
            taper,
            streak,
            knife,
            glaze,
            clip,
            self.rng,
        ):
            self._record(["s", round(float(width), 1), *_reveal_points(p)])

    def _stroke(
        self,
        p: np.ndarray,
        width: float,
        col: np.ndarray,
        alpha: float,
        dry: float,
        pickup: float,
        thick: float,
        taper: float,
        streak: float,
        knife: bool,
        glaze: bool,
        clip: np.ndarray | None,
        r: np.random.Generator,
    ) -> bool:
        hw = width / 2
        x0 = int(max(0, math.floor(float(p[:, 0].min()) - hw - 2)))
        x1 = int(min(self.W, math.ceil(float(p[:, 0].max()) + hw + 2)))
        y0 = int(max(0, math.floor(float(p[:, 1].min()) - hw - 2)))
        y1 = int(min(self.H, math.ceil(float(p[:, 1].max()) + hw + 2)))
        if x1 <= x0 or y1 <= y0:
            return False
        dist, s, side = _polyline_field(p, hw, (x0, y0, x1, y1))
        near = dist < hw + 1
        if not near.any():
            return False
        # Work only on pixels near the path (a thin band of a big bbox).
        iy, ix = np.nonzero(near)
        dist, s, side = dist[iy, ix], s[iy, ix], side[iy, ix]
        prof = np.clip(np.sin(np.pi * np.clip(s, 0, 1)), 0, 1) ** taper
        wloc = hw * (0.3 + 0.7 * prof)
        u = side * dist / (wloc + 1e-6)
        g = self.tooth[iy + y0, ix + x0]
        if knife:
            b = np.full_like(u, 0.8 + 0.2 * float(r.random()))
            load = 1.0 - 0.8 * s**1.5
            cov = np.clip((load - dry * (1.1 - g)) * 2.2, 0, 1)
            edge = smoothstep(1.0, 0.7, np.abs(u)) * smoothstep(0.0, 0.08, s) * (s < 1 - 1e-4)
        else:
            nb = int(min(48, max(6, width * 0.7)))
            bank, _ = self._bristles(nb)
            br = bank[int(r.integers(_BRISTLE_BANK))]
            fi = np.clip((u + 1) * 0.5 * (nb - 1), 0, nb - 1)
            i0 = fi.astype(np.int32)
            i1 = np.minimum(i0 + 1, nb - 1)
            fr = fi - i0
            b = br[i0] * (1 - fr) + br[i1] * fr
            load = 1.0 - s * (0.3 + 0.6 * dry)
            cov = (0.5 + 0.5 * b) * load - dry * (1.2 - g) + (1 - dry) * 0.35
            cov = np.clip(cov * 1.7, 0, 1)
            edge = (
                smoothstep(1.0, 0.45, np.abs(u))
                * smoothstep(0.0, 0.12, s)
                * smoothstep(1.0, 0.75, s)
            )
        cov = cov * edge * alpha * (np.abs(u) < 1.0)
        if clip is not None:
            cov = cov * clip[iy + y0, ix + x0]
        m = cov > 0.004
        if not m.any():
            return True
        gy, gx = iy[m] + y0, ix[m] + x0
        old = self.rgb[gy, gx]
        c = cov[m][:, None]
        if glaze:
            self.rgb[gy, gx] = old * (1 - (1 - col[None, :]) * c)
            return True
        bb = b[m][:, None]
        cc = col[None, :] * (1 + streak * (bb - 0.5) * 0.5)
        pk = pickup * (0.3 + 0.7 * s[m][:, None])
        cc = cc * (1 - pk) + old * pk
        self.rgb[gy, gx] = old * (1 - c) + cc * c
        c1 = c[:, 0]
        thick *= _body(col)
        self.height[gy, gx] = self.height[gy, gx] * (1 - 0.6 * c1) + thick * c1 * (
            0.5 + 0.7 * bb[:, 0]
        )
        return True

    def dab(
        self,
        x: float,
        y: float,
        angle: float,
        length: float,
        width: float,
        color: ColorLike,
        alpha: float = 0.9,
        dry: float = 0.3,
        pickup: float = 0.12,
        thick: float = 0.5,
        curve: float = 0.0,
        clip: np.ndarray | None = None,
        tip: str = "flat",
    ) -> None:
        """One short flat-brush mark (Cézanne patches, impressionist touches, foliage).

        Square end, per-bristle streaks, paint breaking up on the tooth toward
        the tail (more with `dry`). curve bends the mark (+/- ~0.3).
        tip: "flat" (square) or "round" (filbert).
        """
        if self._dab(
            float(x),
            float(y),
            float(angle),
            float(length),
            float(width),
            rgb(color),
            alpha,
            dry,
            pickup,
            thick,
            curve,
            clip,
            tip == "round",
            self.rng,
        ):
            self._record_dab(x, y, angle, length, width)

    def _record_dab(self, x: float, y: float, angle: float, length: float, width: float) -> None:
        ca, sa = math.cos(angle) * length / 2, math.sin(angle) * length / 2
        self._record(
            [
                "s",
                round(float(width), 1),
                round(x - ca, 1),
                round(y - sa, 1),
                round(x + ca, 1),
                round(y + sa, 1),
            ]
        )

    def _dab(
        self,
        x: float,
        y: float,
        angle: float,
        length: float,
        width: float,
        col: np.ndarray,
        alpha: float,
        dry: float,
        pickup: float,
        thick: float,
        curve: float,
        clip: np.ndarray | None,
        round_tip: bool,
        r: np.random.Generator,
    ) -> bool:
        if length <= 0 or width <= 0:
            return False
        ca, sa = math.cos(angle), math.sin(angle)
        hl, hw = max(length * 0.5, 0.5), width * 0.5
        bend = abs(curve) * hl
        ex = abs(ca) * hl + abs(sa) * (hw + bend) + 2
        ey = abs(sa) * hl + abs(ca) * (hw + bend) + 2
        x0, x1 = max(0, int(x - ex)), min(self.W, int(x + ex) + 2)
        y0, y1 = max(0, int(y - ey)), min(self.H, int(y + ey) + 2)
        if x0 >= x1 or y0 >= y1:
            return False
        dx = np.arange(x0, x1, dtype=np.float32)[None, :] - x
        dy = np.arange(y0, y1, dtype=np.float32)[:, None] - y
        u = dx * ca + dy * sa
        un = u / hl
        v = -dx * sa + dy * ca
        if curve:
            v = v - curve * hl * un * un
        au = np.minimum(np.abs(un), 1.0)
        wloc = hw * np.sqrt(np.clip(1 - au**4, 0, 1)) if round_tip else hw * (1 - 0.3 * au**5)
        em = np.clip(wloc - np.abs(v) + 0.5, 0, 1) * np.clip(hl - np.abs(u) + 0.5, 0, 1)
        iy, ix = np.nonzero(em > 0)
        if len(iy) == 0:
            return False
        em = em[iy, ix]
        vv = v[iy, ix]
        t = np.clip(un[iy, ix] * 0.5 + 0.5, 0, 1)
        nb = int(min(48, max(6, width * 0.8 + 4)))
        bank, raw = self._bristles(nb)
        k = int(r.integers(_BRISTLE_BANK))
        prof, prof2 = bank[k], raw[(k + 7) % _BRISTLE_BANK]
        fi = np.clip((vv / hw * 0.5 + 0.5) * (nb - 1), 0, nb - 1)
        i0 = fi.astype(np.int32)
        i1 = np.minimum(i0 + 1, nb - 1)
        fr = fi - i0
        pb = prof[i0] * (1 - fr) + prof[i1] * fr
        pc = prof2[i0] * (1 - fr) + prof2[i1] * fr
        gy, gx = iy + y0, ix + x0
        g = self.tooth[gy, gx]
        dens = 1 - dry * t**1.6
        cov = np.clip((dens * (0.55 + 0.45 * pb) - g * 0.38) * 5 + 0.3, 0, 1)
        a = alpha * em * cov * (1 - (0.12 + 0.35 * dry) * (1 - pb))
        if clip is not None:
            a = a * clip[gy, gx]
        old = self.rgb[gy, gx]
        cc = col[None, :] * (1 + 0.07 * (pc - 0.5))[:, None]
        if pickup:
            cc = cc * (1 - pickup) + old * pickup
        self.rgb[gy, gx] = old + (cc - old) * a[:, None]
        if thick:
            thick *= _body(col)
            rim = smoothstep(0.55, 0.95, np.abs(vv) / hw) * 0.3 + smoothstep(0.75, 1.0, t) * 0.3
            h = self.height[gy, gx]
            self.height[gy, gx] = h * (1 - 0.5 * a) + a * thick * (0.45 + 0.3 * pb + rim) * (
                1.1 - 0.3 * t
            )
        return True

    def paint_region(
        self,
        region: np.ndarray,
        count: int,
        color: ColorSpec | np.ndarray,
        angle: AngleSpec = 0.0,
        length: tuple[float, float] = (20, 60),
        width: tuple[float, float] = (6, 16),
        alpha: float | tuple[float, float] = 0.85,
        brush: str = "dab",
        jitter: float = 0.03,
        angle_jitter: float = 0.12,
        dry: float | tuple[float, float] = 0.3,
        pickup: float = 0.15,
        thick: float = 0.45,
        curve: float = 0.1,
        leak: float = 0.0,
        seed: int | None = None,
        group: tuple[int, int] = (3, 5),
        overlap: float = 0.85,
        tip: str = "flat",
        chroma: float | None = None,
        scale: float | np.ndarray = 1.0,
    ) -> int:
        """Cover a region with many brush marks — the workhorse for real brushwork.

        color: one color, an HxWx3 guide image to sample (paint what's "under" your
        design), or fn(x, y, rng) -> color.
        angle: radians, an HxW direction field, or fn(x, y, rng) -> radians.
        brush: "dab" (short flat marks), "patch" (groups of `group` parallel dabs
        sharing one modulated color — Cézanne's constructive stroke), or "flow"
        (long strokes that follow the `angle` field: vortices, waves, hair, grass).
        Marks are spread evenly (stratified); a soft region acts as a density map.
        length, width, and optionally alpha and dry are (lo, hi) ranges per mark.
        scale: multiplier on length and width, a number or an HxW field (perspective:
        smaller marks toward the horizon).
        jitter: value variation per mark; chroma: hue variation (default jitter*0.35).
        leak: how much marks may spill past the region edge (0 = clipped hard).
        Returns the number of marks laid.
        """
        if brush not in ("dab", "patch", "flow"):
            raise ValueError(f"brush must be 'dab', 'patch' or 'flow', got {brush!r}")
        r = np.random.default_rng(
            self.seed * 7919 + seed if seed is not None else int(self.rng.integers(1 << 30))
        )
        reg = np.clip(np.asarray(region, np.float32), 0, 1)
        n_seeds = count
        if brush == "patch":
            n_seeds = max(1, int(round(count / ((group[0] + group[1]) / 2))))
        pts = _stratified_points(reg, n_seeds, r)
        n = len(pts)
        if n == 0:
            return 0
        clip = None if leak >= 1 else (np.clip(reg + leak, 0, 1) if leak else reg)
        xs, ys = pts[:, 0], pts[:, 1]
        xi = np.clip(xs.astype(np.int32), 0, self.W - 1)
        yi = np.clip(ys.astype(np.int32), 0, self.H - 1)
        guide = _guide(color)
        if guide is not None:
            cols = guide[yi, xi].astype(np.float32)
        elif callable(color):
            cols = np.stack(
                [rgb(color(float(x), float(y), r)) for x, y in zip(xs, ys, strict=True)]
            )
        else:
            cols = np.broadcast_to(rgb(color), (n, 3)).astype(np.float32)
        ch = jitter * 0.35 if chroma is None else chroma
        vf = (1 + r.normal(0, jitter, (n, 1))).astype(np.float32)
        co = r.normal(0, ch, (n, 3)).astype(np.float32)
        cols = np.clip(cols * vf + co, 0, 1).astype(np.float32)
        alphas = _per_mark(alpha, n, r)
        drys = _per_mark(dry, n, r)
        field_ = isinstance(angle, np.ndarray) and angle.ndim == 2
        if field_:
            angs = np.asarray(angle, np.float32)[yi, xi].astype(np.float64)
        elif callable(angle):
            angs = np.array(
                [float(angle(float(x), float(y), r)) for x, y in zip(xs, ys, strict=True)]
            )
        else:
            angs = np.full(n, float(angle))
        angs = angs + r.normal(0, angle_jitter, n)
        Ls = r.uniform(length[0], length[1], n)
        Ws = r.uniform(width[0], width[1], n)
        if isinstance(scale, np.ndarray):
            sc = np.asarray(scale, np.float64)[yi, xi]
            Ls, Ws = Ls * sc, Ws * sc
        elif scale != 1.0:
            Ls, Ws = Ls * float(scale), Ws * float(scale)
        curves = r.normal(0, curve, n) if curve else np.zeros(n)
        round_tip = tip == "round"
        laid = 0
        if brush == "flow":
            fld = np.asarray(angle, np.float32) if field_ else None
            drift = r.normal(0, angle_jitter * 0.5, n)
            for i in range(n):
                wd = float(Ws[i])
                if fld is not None:
                    stp = max(3.0, wd * 0.5, float(Ls[i]) / 24)
                    path = self.trace(
                        float(xs[i]),
                        float(ys[i]),
                        fld,
                        float(Ls[i]),
                        step=stp,
                        offset=float(drift[i]),
                        bend=float(curves[i]),
                    )
                    c = cols[i]
                    if guide is not None:
                        mx, my = path[len(path) // 2]
                        gc = guide[
                            int(min(max(my, 0), self.H - 1)), int(min(max(mx, 0), self.W - 1))
                        ]
                        c = np.clip(gc * vf[i] + co[i], 0, 1)
                else:
                    a = float(angs[i])
                    path = np.array(
                        [
                            (xs[i], ys[i]),
                            (xs[i] + math.cos(a) * Ls[i], ys[i] + math.sin(a) * Ls[i]),
                        ],
                        np.float32,
                    )
                    c = cols[i]
                if self._stroke(
                    path,
                    wd,
                    np.asarray(c, np.float32),
                    float(alphas[i]),
                    float(drys[i]),
                    pickup,
                    thick,
                    0.4,
                    0.3,
                    False,
                    False,
                    clip,
                    r,
                ):
                    self._record(["s", round(wd, 1), *_reveal_points(path)])
                    laid += 1
            return laid
        if brush == "dab":
            for i in range(n):
                x, y, a, L, wd = (
                    float(xs[i]),
                    float(ys[i]),
                    float(angs[i]),
                    float(Ls[i]),
                    float(Ws[i]),
                )
                if self._dab(
                    x,
                    y,
                    a,
                    L,
                    wd,
                    cols[i],
                    float(alphas[i]),
                    float(drys[i]),
                    pickup,
                    thick,
                    float(curves[i]),
                    clip,
                    round_tip,
                    r,
                ):
                    self._record_dab(x, y, a, L, wd)
                    laid += 1
            return laid
        # patch: constructive groups of parallel strokes, one modulated color graded across
        for i in range(n):
            k = int(r.integers(group[0], group[1] + 1))
            a = float(angs[i])
            ca, sa = math.cos(a), math.sin(a)
            L, wd = float(Ls[i]), float(Ws[i])
            grade = float(r.normal(0, 0.018))
            shift = cols[i] - (guide[yi[i], xi[i]] if guide is not None else cols[i])
            for j in range(k):
                o = (j - (k - 1) / 2) * wd * overlap
                along = float(r.normal(0, L * 0.1))
                sx = float(xs[i]) - sa * o + ca * along
                sy = float(ys[i]) + ca * o + sa * along
                if guide is not None:
                    local = guide[
                        int(min(max(sy, 0), self.H - 1)), int(min(max(sx, 0), self.W - 1))
                    ]
                    c = 0.45 * cols[i] + 0.55 * (local + shift)
                else:
                    c = cols[i]
                c = np.clip(c + grade * (j - (k - 1) / 2) + r.normal(0, 0.008, 3), 0, 1).astype(
                    np.float32
                )
                la = L * float(r.uniform(0.85, 1.12))
                aj = a + float(r.normal(0, 0.04))
                if self._dab(
                    sx,
                    sy,
                    aj,
                    la,
                    wd,
                    c,
                    float(alphas[i]),
                    float(drys[i]),
                    pickup,
                    thick,
                    float(curves[i]) * 0.5,
                    clip,
                    round_tip,
                    r,
                ):
                    self._record_dab(sx, sy, aj, la, wd)
                    laid += 1
        return laid

    def contour(
        self,
        pts: Points,
        width: float,
        color: ColorLike,
        alpha: float = 0.7,
        gap: float = 0.25,
        drift: float = 1.5,
        step: float = 8.0,
        dry: float = 0.5,
        pickup: float = 0.2,
        pressure: float = 0.7,
    ) -> None:
        """Searching, broken painter's contour line (Cézanne's blue outlines).

        Runs of overlapping flat dabs that wander ~`drift` px off the path, broken by
        gaps (gap=0: continuous). pressure 0 even .. 1 strongly swelling: each run
        lands thin, swells, and lifts off, with width and paint load varying along it.
        """
        p = np.asarray(pts, np.float64).reshape(-1, 2)
        if len(p) < 2:
            return
        seg = np.hypot(*np.diff(p, axis=0).T)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        n = int(cum[-1])
        if n < 2:
            return
        s = np.linspace(0, cum[-1], n + 1)
        path = np.stack([np.interp(s, cum, p[:, 0]), np.interp(s, cum, p[:, 1])], 1)
        r = np.random.default_rng(int(self.rng.integers(1 << 30)))
        pr = float(np.clip(pressure, 0, 1))
        swell = 0.6 * _smooth1d(r, 9, len(path)) + 0.4 * _smooth1d(r, 40, len(path))
        wmod = np.clip(1 + 0.55 * pr * swell, 0.2, 2.0)
        dr = drift * _smooth1d(r, 30, len(path))
        col = rgb(color)
        st = max(2, int(step))
        i, on = 0, True
        while i < len(path) - st:
            run = int(r.uniform(40, 160) if on else r.uniform(10, 60) * gap * 3)
            if on:
                done: list[tuple[float, float]] = []
                j_end = min(i + run, len(path) - st)
                for j in range(i, j_end, max(2, st // 2)):
                    frac = (j - i) / max(1, j_end - i) if gap > 0 else j / max(1, len(path) - st)
                    env = 1 - pr * 0.75 * (1 - math.sin(math.pi * min(max(frac, 0.0), 1.0)) ** 0.5)
                    load = float(np.clip(0.55 + 0.45 * wmod[j] * env, 0.25, 1.0))
                    (xa, ya), (xb, yb) = path[j], path[j + st]
                    ang = math.atan2(yb - ya, xb - xa)
                    cx = (xa + xb) / 2 - math.sin(ang) * dr[j]
                    cy = (ya + yb) / 2 + math.cos(ang) * dr[j]
                    if self._dab(
                        cx,
                        cy,
                        ang,
                        st * 1.6,
                        width * float(wmod[j]) * env,
                        col,
                        alpha * 0.7 * load,
                        dry,
                        pickup,
                        0.3,
                        0.0,
                        None,
                        False,
                        r,
                    ):
                        done.append((cx, cy))
                if len(done) >= 2:
                    self._record(
                        ["s", round(float(width), 1), *_reveal_points(np.array(done, np.float32))]
                    )
                elif done:
                    self._record_dab(done[0][0], done[0][1], 0.0, st * 1.6, width)
            i += max(1, run)
            on = (not on) if gap > 0 else True

    # ------------------------------------------------------------------ crisp shapes

    def shape(
        self,
        polys: Sequence[tuple[Points, ColorLike]] = (),
        lines: Sequence[tuple[Points, float, ColorLike]] = (),
        ellipses: Sequence[tuple[float, float, float, float, ColorLike]] = (),
        alpha: float = 1.0,
        model: float = 0.0,
        texture: float = 0.02,
        ss: int = 4,
        limbs: Sequence[tuple[Points, Sequence[float] | float, ColorLike]] = (),
        thick: float = 0.0,
        parts: Sequence[tuple[Any, ...]] = (),
        reflect: float = 0.0,
        reflect_y: float | None = None,
        reflect_clip: np.ndarray | None = None,
        clip: np.ndarray | None = None,
        return_mask: bool = False,
    ) -> np.ndarray | None:
        """Crisp anti-aliased small shapes drawn as one opaque unit (figures, boats,
        windows, birds, masts, fence posts, lettering).

        polys: [(points, color)], limbs: [(points, widths, color)] tapered and
        round-jointed, lines: [(points, width, color)], ellipses: [(cx, cy, rx, ry,
        color)], drawn in that order, then `parts` in the order given:
        ("poly", pts, color) | ("line", pts, width, color) | ("limb", pts, widths, color)
        | ("ellipse", cx, cy, rx, ry, color) | ("rect", x0, y0, x1, y1, color).
        model > 0 rounds the silhouette with light from the upper left (0.3-0.5 for
        figures). thick: impasto deposited. reflect > 0 (0.2-0.4) mirrors the unit
        dimly below `reflect_y` (default: its lowest point) — boats on water, skaters
        on ice; reflect_clip limits the reflection to the water mask.
        clip: mask the unit may paint into (a taped border, a window). return_mask=True
        returns the unit's coverage as an HxW mask (to glaze or texture it afterwards).
        """
        empty = np.zeros((self.H, self.W), np.float32) if return_mask else None
        items: list[tuple[Any, ...]] = [("poly", p, c) for p, c in polys]
        items += [("limb", p, w, c) for p, w, c in limbs]
        items += [("line", p, w, c) for p, w, c in lines]
        items += [("ellipse", *e) for e in ellipses]
        items += list(parts)
        ops: list[tuple[str, Any, ColorLike]] = []
        xs: list[float] = []
        ys: list[float] = []
        for it in items:
            kind = it[0]
            if kind == "poly":
                pa = np.asarray(it[1], np.float64).reshape(-1, 2)
                ops.append(("poly", pa, it[2]))
                xs += list(pa[:, 0])
                ys += list(pa[:, 1])
            elif kind == "rect":
                ax, ay, bx, by = (float(v) for v in it[1:5])
                pa = np.array([(ax, ay), (bx, ay), (bx, by), (ax, by)], np.float64)
                ops.append(("poly", pa, it[5]))
                xs += [ax, bx]
                ys += [ay, by]
            elif kind == "limb":
                pa = np.asarray(it[1], np.float64).reshape(-1, 2)
                wa = _widths_along(pa, it[2])
                poly = _ribbon(pa, wa)
                if poly is None:
                    continue
                ops.append(("poly", poly, it[3]))
                for k in range(1, len(pa) - 1):
                    ops.append(("ellipse", (pa[k, 0], pa[k, 1], wa[k] / 2, wa[k] / 2), it[3]))
                xs += list(poly[:, 0])
                ys += list(poly[:, 1])
            elif kind == "line":
                pa = np.asarray(it[1], np.float64).reshape(-1, 2)
                w = float(it[2])
                ops.append(("line", (pa, w), it[3]))
                xs += list(pa[:, 0] - w) + list(pa[:, 0] + w)
                ys += list(pa[:, 1] - w) + list(pa[:, 1] + w)
            elif kind == "ellipse":
                cx, cy, rx, ry = (float(v) for v in it[1:5])
                ops.append(("ellipse", (cx, cy, rx, ry), it[5]))
                xs += [cx - rx, cx + rx]
                ys += [cy - ry, cy + ry]
            else:
                raise ValueError(f"unknown shape part {kind!r}")
        if not xs:
            return empty
        bottom = max(ys)
        ry0 = bottom if reflect_y is None else float(reflect_y)
        if reflect:
            ys.append(2 * ry0 - min(ys))
        x0 = max(0, int(math.floor(min(xs))) - 2)
        y0 = max(0, int(math.floor(min(ys))) - 2)
        x1 = min(self.W, int(math.ceil(max(xs))) + 3)
        y1 = min(self.H, int(math.ceil(max(ys))) + 3)
        if x1 <= x0 or y1 <= y0:
            return empty
        pw, ph = x1 - x0, y1 - y0
        im = Image.new("RGBA", (pw * ss, ph * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)

        def P(px: float, py: float) -> tuple[float, float]:
            return ((px - x0) * ss, (py - y0) * ss)

        def col(c: ColorLike) -> tuple[int, int, int, int]:
            v = np.clip(rgb(c) * 255, 0, 255).astype(int)
            return (int(v[0]), int(v[1]), int(v[2]), 255)

        for kind, geom, c in ops:
            if kind == "poly":
                d.polygon([P(float(px), float(py)) for px, py in geom], fill=col(c))
            elif kind == "line":
                pa, w = geom
                d.line(
                    [P(float(px), float(py)) for px, py in pa],
                    fill=col(c),
                    width=max(1, int(round(w * ss))),
                    joint="curve",
                )
            else:
                cx, cy, rx, ry = geom
                ax, ay = P(cx - rx, cy - ry)
                bx, by = P(cx + rx, cy + ry)
                d.ellipse([ax, ay, max(bx, ax + 1), max(by, ay + 1)], fill=col(c))
        a = np.asarray(im, np.float32).reshape(ph, ss, pw, ss, 4) / 255.0
        al = a[..., 3].mean((1, 3))
        if clip is not None:
            al = al * np.clip(clip[y0:y1, x0:x1], 0, 1)
        pm = (a[..., :3] * a[..., 3:4]).mean((1, 3))
        colr = pm / np.maximum(al[..., None], 1e-6)
        if model:
            sig = max(0.7, min(ph, pw) * 0.04)
            bl = ndi.gaussian_filter(al, sig)
            gy, gx = np.gradient(bl)
            lt = np.clip((gx * 0.8 + gy * 0.55) * sig * 2.2, -1, 1)
            colr = colr * (1 + model * lt[..., None]) + model * 0.08 * np.clip(lt, 0, 1)[..., None]
        if texture:
            n = (
                np.random.default_rng(int(self.rng.integers(1 << 30)))
                .standard_normal((ph, pw))
                .astype(np.float32)
            )
            colr = colr * (1 + texture * ndi.gaussian_filter(n, 0.7)[..., None])
        region = self.rgb[y0:y1, x0:x1]
        if reflect:
            fr = int(round(ry0 - y0))
            nr = min(fr, ph - fr)
            if nr > 2:
                src_a = al[fr - nr : fr][::-1]
                src_c = colr[fr - nr : fr][::-1]
                fade = np.linspace(1, 0, nr, dtype=np.float32) ** 1.5
                ra = ndi.gaussian_filter(src_a, (0.6, 0.4)) * fade[:, None] * reflect
                if reflect_clip is not None:
                    ra = ra * reflect_clip[y0 + fr : y0 + fr + nr, x0:x1]
                under = region[fr : fr + nr]
                rc = src_c * 0.7 + under * 0.3
                under[:] = under * (1 - ra[..., None]) + rc * ra[..., None]
        m = (al * alpha)[..., None]
        region[:] = region * (1 - m) + np.clip(colr, 0, 1) * m
        if thick:
            h = self.height[y0:y1, x0:x1]
            h[:] = h * (1 - 0.5 * m[..., 0]) + thick * m[..., 0]
        self._record(["a", x0, y0, x1, y1])
        if empty is not None:
            empty[y0:y1, x0:x1] = m[..., 0]
        return empty

    def sign(
        self,
        x: float,
        y: float,
        size: float = 36.0,
        color: ColorLike = "#2a2320",
        alpha: float = 0.85,
    ) -> None:
        """The artist's small "CM" monogram with its left edge at x, baseline at y."""
        s = size / 50.0

        def cubic(
            p0: tuple[float, float],
            p1: tuple[float, float],
            p2: tuple[float, float],
            p3: tuple[float, float],
        ) -> list[tuple[float, float]]:
            out = []
            for t in (float(v) for v in np.linspace(0, 1, 16)):
                u = 1 - t
                out.append(
                    (
                        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
                    )
                )
            return out

        c_curve = (
            cubic((34, 13), (25, 3), (8, 8), (6, 25))
            + cubic((6, 25), (4, 42), (24, 48), (36, 36))[1:]
        )
        m_curve = [(50, 43), (50, 9), (66, 34), (82, 9), (82, 43)]
        for pts in (c_curve, m_curve):
            p = np.array([(x + px * s, y - 50 * s + py * s) for px, py in pts], np.float32)
            self.stroke(
                p,
                max(1.5, 3.2 * s),
                color,
                alpha=alpha,
                dry=0.1,
                pickup=0.0,
                thick=0.3,
                taper=0.2,
                streak=0.1,
            )

    # ------------------------------------------------------------------ output

    def finished(self) -> np.ndarray:
        """The painting as it will be shown: impasto lit by raking light, varnish tone."""
        h = ndi.gaussian_filter(self.height, 1.0) + 0.06 * self.tooth * (
            1 - np.clip(self.height, 0, 1)
        )
        gy, gx = np.gradient(h * 2.6 * self.impasto)
        lx, ly = self.light
        L = np.array([lx, ly, 0.58], np.float32)
        L /= np.linalg.norm(L)
        nn = np.sqrt(gx * gx + gy * gy + 1)
        lam = (-gx * L[0] - gy * L[1] + L[2]) / nn
        shade = 1 + 0.7 * (lam - L[2])
        out = self.rgb * shade[..., None] * self.varnish
        return np.clip(out, 0, 1)

    def export(self, out_dir: str | Path, preview_width: int = 1200) -> RevealSummary:
        """Close the last stage and write keyframes, final image, and reveal log."""
        self._close_stage()
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        frames = _limit_keyframes(self._keyframes)
        manifest: list[dict[str, Any]] = []
        for i, (label, img, ops) in enumerate(frames):
            name = f"kf_{i:02d}.jpg"
            Image.fromarray(_to_u8(img)).save(out / name, quality=88)
            manifest.append({"label": label, "image": name, "ops": ops})
        final = self.finished()
        final_u8 = _to_u8(final)
        Image.fromarray(final_u8).save(out / "final.png")
        prev = Image.fromarray(final_u8)
        if prev.width > preview_width:
            prev = prev.resize(
                (preview_width, round(prev.height * preview_width / prev.width)),
                Image.Resampling.LANCZOS,
            )
        prev.save(out / "preview.jpg", quality=90)
        reveal = {"width": self.W, "height": self.H, "keyframes": manifest}
        (out / "reveal.json").write_text(json.dumps(reveal, separators=(",", ":")))
        return reveal_summary(reveal)


class RevealSummary(TypedDict):
    width: int
    height: int
    stages: list[str]
    ops: int


def reveal_summary(reveal: dict[str, Any]) -> RevealSummary:
    """Version metadata of a reveal manifest: size, distinct stages in order, op count."""
    labels = [kf["label"] for kf in reveal["keyframes"]]
    return {
        "width": reveal["width"],
        "height": reveal["height"],
        "stages": [lab for i, lab in enumerate(labels) if i == 0 or labels[i - 1] != lab],
        "ops": sum(len(kf["ops"]) for kf in reveal["keyframes"]),
    }


# ---------------------------------------------------------------------- helpers


def _to_u8(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    live = mask > 0.002
    rows = np.nonzero(live.any(axis=1))[0]
    if len(rows) == 0:
        return None
    cols = np.nonzero(live.any(axis=0))[0]
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def _pad_box(box: tuple[int, int, int, int], pad: int, w: int, h: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)


def _color_field(color: ColorLike | np.ndarray, h: int, w: int) -> np.ndarray:
    arr = np.asarray(color) if not isinstance(color, str) else None
    if arr is not None and arr.ndim == 3:
        return arr.astype(np.float32)
    return np.broadcast_to(rgb(color), (h, w, 3))


def _guide(color: object) -> np.ndarray | None:
    if isinstance(color, np.ndarray) and color.ndim == 3:
        return np.asarray(color, np.float32)
    return None


def _body(col: np.ndarray) -> float:
    """Paint body by color: lead-white lights stand thick, dark glazes lie thin."""
    return 0.55 + 0.75 * float(col[0] * 0.3 + col[1] * 0.59 + col[2] * 0.11)


def _per_mark(v: float | tuple[float, float], n: int, r: np.random.Generator) -> np.ndarray:
    if isinstance(v, tuple | list):
        return r.uniform(float(v[0]), float(v[1]), n)
    return np.full(n, float(v))


def _smooth1d(r: np.random.Generator, sigma: float, n: int) -> np.ndarray:
    v = ndi.gaussian_filter1d(r.standard_normal(n + 200), sigma, mode="wrap")[100:-100]
    return v / (v.std() + 1e-6)


def _stratified_points(region: np.ndarray, count: int, r: np.random.Generator) -> np.ndarray:
    """~count points spread evenly over a soft region (jittered grid, density = region value)."""
    if count <= 0:
        return np.zeros((0, 2), np.float32)
    live = region > 0.02
    rows = np.nonzero(live.any(axis=1))[0]
    if len(rows) == 0:
        return np.zeros((0, 2), np.float32)
    cols = np.nonzero(live.any(axis=0))[0]
    x0, x1, y0, y1 = int(cols[0]), int(cols[-1]) + 1, int(rows[0]), int(rows[-1]) + 1
    area = float(region[y0:y1, x0:x1].sum())
    sp = max(1.0, math.sqrt(max(area, 1.0) / count))
    gx, gy = np.meshgrid(np.arange(x0, x1, sp), np.arange(y0, y1, sp))
    px = gx.ravel() + r.uniform(0, sp, gx.size)
    py = gy.ravel() + r.uniform(0, sp, gy.size)
    ok = (px < x1) & (py < y1)
    px, py = px[ok], py[ok]
    dens = region[py.astype(np.int32), px.astype(np.int32)]
    keep = r.random(len(px)) < dens
    pts = np.stack([px[keep], py[keep]], 1)
    if len(pts) < count:
        ys, xs = np.nonzero(region > 0.5) if (region > 0.5).any() else np.nonzero(live)
        idx = r.integers(0, len(xs), count - len(pts))
        extra = np.stack([xs[idx] + r.random(len(idx)), ys[idx] + r.random(len(idx))], 1)
        pts = np.vstack([pts, extra])
    elif len(pts) > count:
        pts = pts[r.choice(len(pts), count, replace=False)]
    return pts[r.permutation(len(pts))].astype(np.float32)


def _widths_along(pts: np.ndarray, widths: float | Sequence[float] | np.ndarray) -> np.ndarray:
    """Per-point widths from a scalar, a (start, end) pair, or a list of any length."""
    w = np.asarray(widths, np.float64).reshape(-1)
    n = len(pts)
    if w.size == 1:
        return np.full(n, float(w[0]))
    if w.size == n:
        return w
    seg = np.hypot(*np.diff(pts, axis=0).T) if n > 1 else np.zeros(0)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    t = cum / cum[-1] if cum[-1] > 0 else np.linspace(0, 1, n)
    return np.interp(t, np.linspace(0, 1, w.size), w)


def _ribbon(pts: np.ndarray, widths: float | Sequence[float] | np.ndarray) -> np.ndarray | None:
    if len(pts) < 2:
        return None
    w = _widths_along(pts, widths)
    tg = np.gradient(pts, axis=0)
    tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-9
    nrm = np.stack([-tg[:, 1], tg[:, 0]], 1)
    a = pts + nrm * w[:, None] / 2
    b = pts - nrm * w[:, None] / 2
    return np.vstack([a, b[::-1]])


def _reveal_points(p: np.ndarray) -> list[float]:
    if len(p) > _MAX_REVEAL_POINTS:
        idx = np.linspace(0, len(p) - 1, _MAX_REVEAL_POINTS).round().astype(int)
        p = p[idx]
    return [round(float(v), 1) for v in p.reshape(-1)]


def _polyline_field(
    pts: np.ndarray, hw: float, box: tuple[int, int, int, int]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-pixel distance, normalized arc length, and side for a polyline."""
    x0, y0, x1, y1 = box
    dist = np.full((y1 - y0, x1 - x0), np.inf, np.float32)
    sarc = np.zeros_like(dist)
    side = np.ones_like(dist)
    a_pts = pts[:-1].astype(np.float64)
    ab = np.diff(pts, axis=0).astype(np.float64)
    seg = np.hypot(ab[:, 0], ab[:, 1]) + 1e-9
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    pad = hw + 2
    lo = np.minimum(pts[:-1], pts[1:]) - pad
    hi = np.maximum(pts[:-1], pts[1:]) + pad
    for i in range(len(a_pts)):
        sx0 = int(max(x0, math.floor(lo[i, 0])))
        sx1 = int(min(x1, math.ceil(hi[i, 0])))
        sy0 = int(max(y0, math.floor(lo[i, 1])))
        sy1 = int(min(y1, math.ceil(hi[i, 1])))
        if sx1 <= sx0 or sy1 <= sy0:
            continue
        ax, ay = a_pts[i]
        abx, aby = ab[i]
        apx = (np.arange(sx0, sx1, dtype=np.float32)[None, :] + 0.5) - np.float32(ax)
        apy = (np.arange(sy0, sy1, dtype=np.float32)[:, None] + 0.5) - np.float32(ay)
        inv = np.float32(1.0 / seg[i] ** 2)
        t = np.clip((apx * np.float32(abx) + apy * np.float32(aby)) * inv, 0, 1)
        ddx = apx - t * np.float32(abx)
        ddy = apy - t * np.float32(aby)
        d = np.sqrt(ddx * ddx + ddy * ddy)
        sl = (slice(sy0 - y0, sy1 - y0), slice(sx0 - x0, sx1 - x0))
        dv = dist[sl]
        better = d < dv
        dv[better] = d[better]
        sarc[sl][better] = (np.float32(cum[i]) + t * np.float32(seg[i]))[better]
        cr = np.float32(abx) * apy - np.float32(aby) * apx
        side[sl][better] = np.where(cr[better] < 0, -1.0, 1.0)
    dist[~np.isfinite(dist)] = 1e9
    return dist, sarc / np.float32(cum[-1]), side


def _limit_keyframes(
    frames: list[tuple[str, np.ndarray, list[list[Any]]]],
) -> list[tuple[str, np.ndarray, list[list[Any]]]]:
    """Merge adjacent keyframes (keeping the later image) until under the cap."""
    frames = list(frames)
    while len(frames) > _MAX_KEYFRAMES:
        sizes = [len(frames[i][2]) + len(frames[i + 1][2]) for i in range(len(frames) - 1)]
        i = int(np.argmin(sizes))
        label = frames[i + 1][0]
        frames[i : i + 2] = [(label, frames[i + 1][1], frames[i][2] + frames[i + 1][2])]
    return frames
