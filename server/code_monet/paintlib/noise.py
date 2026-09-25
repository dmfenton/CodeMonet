"""Smooth noise and small numeric helpers for painting programs."""

from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi


def value_noise(
    shape: tuple[int, int],
    cell: float,
    seed: int,
    order: int = 3,
    aniso: tuple[float, float] = (1.0, 1.0),
) -> np.ndarray:
    """Smooth random field in [0, 1] with features about `cell` pixels wide.

    `aniso=(ax, ay)` stretches features: (8, 1) gives horizontal grain (wood, water,
    streaky sky), (1, 6) vertical (rain, reeds).
    """
    h, w = shape
    cx, cy = max(1.0, cell * aniso[0]), max(1.0, cell * aniso[1])
    gy = max(2, int(np.ceil(h / cy)) + 3)
    gx = max(2, int(np.ceil(w / cx)) + 3)
    grid = np.random.default_rng(seed).random((gy, gx))
    z = ndi.zoom(grid, (cy, cx), order=order, grid_mode=False)
    z = z[:h, :w]
    if z.shape != (h, w):
        z = np.pad(z, ((0, h - z.shape[0]), (0, w - z.shape[1])), mode="edge")
    lo, hi = float(z.min()), float(z.max())
    return ((z - lo) / (hi - lo + 1e-9)).astype(np.float32)


def fbm(
    shape: tuple[int, int],
    cell: float,
    octaves: int = 4,
    seed: int = 0,
    gain: float = 0.5,
    aniso: tuple[float, float] = (1.0, 1.0),
) -> np.ndarray:
    """Fractal (multi-octave) value noise, range [0, 1] with mean ~0.5.

    Center it with `fbm(...) - 0.5`. `aniso=(ax, ay)` stretches every octave.
    """
    acc = np.zeros(shape, np.float32)
    amp, total, c = 1.0, 0.0, float(cell)
    for o in range(octaves):
        acc += amp * value_noise(shape, c, seed + 131 * o, aniso=aniso)
        total += amp
        amp *= gain
        c = max(1.5, c / 2)
    return acc / total


def smoothstep(a: float, b: float, x: np.ndarray | float) -> np.ndarray:
    """Smooth 0->1 ramp as x goes from a to b; a > b gives the inverse ramp (1->0)."""
    t = np.clip((np.asarray(x, np.float32) - a) / (b - a + 1e-9), 0, 1)
    return t * t * (3 - 2 * t)


def _as_array(v: object) -> np.ndarray:
    if isinstance(v, str):
        from .canvas import rgb  # local import: canvas imports this module

        return rgb(v)
    return np.asarray(v, np.float32)


def mix(a: np.ndarray | str, b: np.ndarray | str, t: np.ndarray | float) -> np.ndarray:
    """Linear blend of colors or fields; a 2-D `t` (HxW) broadcasts over RGB channels.

    mix(color_a, color_b, mask) -> HxWx3; mix(img, color, mask) -> HxWx3.
    """
    a_, b_ = _as_array(a), _as_array(b)
    t = np.asarray(t, np.float32)
    colorish = any(v.ndim == 3 or (v.ndim == 1 and v.shape[0] == 3) for v in (a_, b_))
    if t.ndim == 2 and colorish:
        t = t[..., None]
    return a_ * (1 - t) + b_ * t


def cellular(
    shape: tuple[int, int],
    cell: float,
    seed: int = 0,
    aniso: tuple[float, float] = (1.0, 1.0),
    jitter: float = 0.7,
    return_id: bool = False,
) -> tuple[np.ndarray, ...]:
    """Cellular (Worley) noise over an HxW grid of cells ~`cell` px wide.

    Returns (f1, edge) in px: f1 = distance to the nearest cell center (cobbles,
    scales, pebbles: e.g. 1 - f1 / cell), edge = F2 - F1 = distance to the nearest
    cell border (edge < 1.5 draws a crack/lead-line/water-light net). With
    return_id=True also returns an int cell id (color patchwork fields per cell).
    aniso=(ax, ay) stretches cells: (3, 1) = wide flat cells (fields in perspective).
    jitter 0 = regular grid .. 1 = fully random centers.
    """
    h, w = shape
    cw, ch = max(1.0, cell * aniso[0]), max(1.0, cell * aniso[1])
    nu, nv = int(w / cw) + 4, int(h / ch) + 4
    r = np.random.default_rng(seed)
    lo = 0.5 - jitter / 2
    jx = (lo + jitter * r.random((nv, nu))).astype(np.float32)
    jy = (lo + jitter * r.random((nv, nu))).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = xx / np.float32(cw), yy / np.float32(ch)
    iu, iv = u.astype(np.int32), v.astype(np.int32)
    d1 = np.full((h, w), np.inf, np.float32)
    d2 = np.full((h, w), np.inf, np.float32)
    ids = np.zeros((h, w), np.int64)
    for dv in (-1, 0, 1):
        for du in (-1, 0, 1):
            cu, cv_ = iu + du, iv + dv
            px = cu + jx[cv_ + 1, cu + 1]
            py = cv_ + jy[cv_ + 1, cu + 1]
            d = np.hypot((u - px) * np.float32(cw), (v - py) * np.float32(ch))
            closer = d < d1
            d2 = np.where(closer, d1, np.minimum(d2, d))
            d1 = np.where(closer, d, d1)
            if return_id:
                ids = np.where(closer, (cv_ + 1) * nu + cu + 1, ids)
    if return_id:
        return d1, d2 - d1, ids
    return d1, d2 - d1
