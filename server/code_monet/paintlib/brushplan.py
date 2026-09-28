"""Brush plans: how a painter's hand would lay in the pixels an area op changed.

An area op (fill, wash, glaze, smear, crisp shape) changes a region at once.
For the performance, its changed pixels are split into a sequence of brush
strokes whose union is exactly those pixels, each with a draw order along the
stroke. Pixel values are the op's own; only the pattern and timing are the
plan, and the plan is how a person would paint that region:

- **lay**: a broad brush in rows along the region's main axis, back and forth
  row by row; strokes a few brush-widths long, staggered like brickwork, rows
  wandering slightly, fronts ragged like bristles.
- **shape**: a crisp unit is outlined first (small strokes travelling around
  its edge), then filled in with a brush sized to it.
- **prime**: preparing the canvas (its ground) is not part of the painting;
  the performance starts on the primed canvas (one instant patch).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

PlanKind = Literal["lay", "shape", "prime"]

# Broad brush width, from the region's size (image px at ~1600 wide).
_MIN_BRUSH = 18.0
_MAX_BRUSH = 150.0
_BRUSH_PER_SQRT_AREA = 1 / 7
# A stroke is this many brush-widths long (a brush load), within bounds.
_STROKE_LENGTHS = (2.5, 5.0)
_MAX_STROKE_PX = 900.0
# Rows overlap their neighbours slightly and wander across the stroke direction.
_ROW_SPACING = 0.85
_ROW_WANDER = 0.12
# How ragged stroke boundaries are (relative perturbation of stroke distance).
_EDGE_RAG = 0.22
# Outline: pixels this close to the shape's edge are painted first.
_EDGE_PX = 3.0
_EDGE_STROKES = (3, 12)


@dataclass(frozen=True)
class PlannedStroke:
    length: float  # px along the stroke (for brush travel time)
    width: float  # px


PRIME = PlannedStroke(length=0.0, width=0.0)


@dataclass(frozen=True)
class Plan:
    """labels[i]: which planned stroke pixel i belongs to (strokes in paint order);
    frac[i]: 0..1 position along that stroke."""

    labels: np.ndarray
    frac: np.ndarray
    strokes: list[PlannedStroke]


def plan(kind: PlanKind, xs: np.ndarray, ys: np.ndarray, seed: int) -> Plan:
    """A brush plan covering the pixels (xs, ys) an area op changed."""
    if len(xs) == 0:
        return Plan(np.zeros(0, np.int32), np.zeros(0, np.float32), [])
    rng = np.random.default_rng(seed)
    if kind == "prime":
        return Plan(np.zeros(len(xs), np.int32), np.zeros(len(xs), np.float32), [PRIME])
    if kind == "shape" and len(xs) > 64:
        edge = _edge_pixels(xs, ys)
        if edge.any() and not edge.all():
            outline = _outline(xs[edge], ys[edge], rng)
            fill = _lay(xs[~edge], ys[~edge], rng)
            return _concat(len(xs), [(edge, outline), (~edge, fill)])
    return _lay(xs, ys, rng)


# ---------------------------------------------------------------------- lay-in


def _lay(xs: np.ndarray, ys: np.ndarray, rng: np.random.Generator) -> Plan:
    """Broad strokes: elongated, slightly turned lozenges laid row by row.

    Stroke centres sit on a jittered brickwork grid along the region's main
    axis; each pixel belongs to the nearest centre under a distance stretched
    along that stroke's own direction, so every stroke is an irregular,
    overlapping band a few brush-widths long. Rows progress across the region
    (back and forth), interleaved a little so no straight front sweeps across.
    """
    x = xs.astype(np.float32) + 0.5
    y = ys.astype(np.float32) + 0.5
    theta = _main_axis(x, y)
    c, s = math.cos(theta), math.sin(theta)
    u = x * c + y * s  # along the strokes
    v = -x * s + y * c  # across them
    u = u - float(u.min())
    v = v - float(v.min())
    lu, lv = float(u.max()) + 1, float(v.max()) + 1

    brush = float(np.clip(math.sqrt(len(xs)) * _BRUSH_PER_SQRT_AREA, _MIN_BRUSH, _MAX_BRUSH))
    brush = min(brush, max(_MIN_BRUSH, lv))  # a thin band is one row
    row_h = brush * _ROW_SPACING
    seg = min(_MAX_STROKE_PX, brush * float(np.mean(_STROKE_LENGTHS)))
    n_rows = max(1, math.ceil(lv / row_h))
    n_cols = max(1, math.ceil(lu / seg) + 1)

    # Centres: brickwork grid (odd rows shifted half a stroke), jittered.
    cr, cc = np.meshgrid(np.arange(n_rows), np.arange(n_cols), indexing="ij")
    cu = (cc + 0.5 * (cr % 2) + rng.uniform(-0.25, 0.25, cr.shape)) * seg - seg / 2
    cv = (cr + 0.5 + rng.uniform(-0.2, 0.2, cr.shape)) * row_h
    turn = rng.normal(0, 0.12, cr.shape)  # each stroke a little off the main axis
    reach = seg * rng.uniform(0.8, 1.25, cr.shape)  # and its own length

    # Stroke edges are ragged, not cut: a wobbly field perturbs the distance.
    ph = rng.uniform(0, 2 * math.pi, 4)
    wob = (
        np.sin(x * 0.045 + ph[0]) * np.sin(y * 0.052 + ph[1])
        + 0.6 * np.sin(x * 0.21 + y * 0.17 + ph[2])
        + 0.4 * np.sin(x * 0.61 - y * 0.47 + ph[3])
    )
    ragged = (1 + _EDGE_RAG * wob).astype(np.float32)

    # Nearest centre among the 3x3 grid neighbours, stretched along each stroke.
    gr = np.clip((v / row_h).astype(np.int32), 0, n_rows - 1)
    gc = np.clip((u / seg).astype(np.int32), 0, n_cols - 1)
    best = np.full(len(xs), np.inf, np.float32)
    lab_r = np.zeros(len(xs), np.int32)
    lab_c = np.zeros(len(xs), np.int32)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            r = np.clip(gr + dr, 0, n_rows - 1)
            k = np.clip(gc + dc, 0, n_cols - 1)
            du, dv = u - cu[r, k], v - cv[r, k]
            ct, st = np.cos(turn[r, k]), np.sin(turn[r, k])
            a = (du * ct + dv * st) / (reach[r, k] / 2)
            b = (-du * st + dv * ct) / (row_h / 2)
            d = (a * a + b * b) * ragged
            better = d < best
            best[better] = d[better]
            lab_r[better] = r[better]
            lab_c[better] = k[better]

    # Paint order: rows back and forth, each stroke nudged earlier or later.
    forward = lab_r % 2 == 0
    col_pos = np.where(forward, lab_c, n_cols - 1 - lab_c).astype(np.float32)
    grid_id = lab_r * n_cols + lab_c
    ids, inverse = np.unique(grid_id, return_inverse=True)
    rows_of = ids // n_cols
    cols_of = ids % n_cols
    pos = np.where(rows_of % 2 == 0, cols_of, n_cols - 1 - cols_of)
    key = rows_of * n_cols + pos + rng.uniform(-1.2, 1.2, len(ids))
    rank = np.empty(len(ids), np.int32)
    rank[np.argsort(key, kind="stable")] = np.arange(len(ids), dtype=np.int32)
    labels = rank[inverse]

    # Along each stroke: its own direction, the way this row travels, ragged front.
    r, k = lab_r, lab_c
    du, dv = u - cu[r, k], v - cv[r, k]
    along = (du * np.cos(turn[r, k]) + dv * np.sin(turn[r, k])) / reach[r, k] + 0.5
    along = np.where(forward, along, 1 - along)
    across = dv / row_h
    bristle = 0.05 * np.sin(across * 17.0 + col_pos) + 0.03 * np.sin(across * 41.0)
    frac = np.clip(along * 0.9 + 0.05 + bristle, 0, 1).astype(np.float32)

    strokes = [
        PlannedStroke(length=float(reach[i // n_cols, i % n_cols]), width=brush) for i in ids
    ]
    ordered = [strokes[i] for i in np.argsort(rank)]
    return Plan(labels.astype(np.int32), frac, ordered)


def _main_axis(x: np.ndarray, y: np.ndarray) -> float:
    """Direction of the region's longest extent (radians), from its covariance."""
    if len(x) < 3:
        return 0.0
    xm, ym = x - x.mean(), y - y.mean()
    cxx, cyy, cxy = float((xm * xm).mean()), float((ym * ym).mean()), float((xm * ym).mean())
    if abs(cxx - cyy) < 1e-6 and abs(cxy) < 1e-6:
        return 0.0
    return 0.5 * math.atan2(2 * cxy, cxx - cyy)


# ---------------------------------------------------------------------- outline


def _edge_pixels(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Pixels within _EDGE_PX of the region's boundary."""
    from scipy import ndimage as ndi

    x0, y0 = int(xs.min()), int(ys.min())
    m = np.zeros((int(ys.max()) - y0 + 3, int(xs.max()) - x0 + 3), bool)
    m[ys - y0 + 1, xs - x0 + 1] = True
    inside = ndi.distance_transform_edt(m)
    return inside[ys - y0 + 1, xs - x0 + 1] <= _EDGE_PX


def _outline(xs: np.ndarray, ys: np.ndarray, rng: np.random.Generator) -> Plan:
    """Edge pixels as a few strokes travelling around the shape."""
    cx, cy = float(xs.mean()), float(ys.mean())
    ang = np.arctan2(ys - cy, xs - cx)
    start = rng.uniform(-math.pi, math.pi)
    t = np.mod(ang - start, 2 * math.pi) / (2 * math.pi)  # 0..1 around the shape
    perimeter = len(xs) / (2 * _EDGE_PX)
    n = int(np.clip(round(perimeter / 120), *_EDGE_STROKES))
    idx = np.minimum(n - 1, (t * n).astype(np.int32))
    frac = (t * n - idx).astype(np.float32)
    strokes = [PlannedStroke(length=perimeter / n, width=_EDGE_PX * 2) for _ in range(n)]
    return Plan(idx.astype(np.int32), frac, strokes)


def _concat(n: int, parts: list[tuple[np.ndarray, Plan]]) -> Plan:
    labels = np.zeros(n, np.int32)
    frac = np.zeros(n, np.float32)
    strokes: list[PlannedStroke] = []
    for mask, p in parts:
        labels[mask] = p.labels + len(strokes)
        frac[mask] = p.frac
        strokes.extend(p.strokes)
    return Plan(labels, frac, strokes)
