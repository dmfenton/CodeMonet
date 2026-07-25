"""Python code execution sandbox for SVG generation."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path as FilePath
from typing import Any

from code_monet.types import BRUSH_PRESETS, Path, PathType

from .path_parsing import parse_path_data

# Python code execution timeout (seconds)
PYTHON_TIMEOUT = 30


async def run_python_code(code: str, canvas_width: int, canvas_height: int) -> dict[str, Any]:
    """Execute Python code in a subprocess and capture output.

    The code should print JSON to stdout with one of these formats:
    1. {"paths": [...]} - array of path objects
    2. {"svg_paths": [...]} - array of SVG d-strings

    The code has access to canvas_width and canvas_height variables.
    Helper functions support optional style parameters: color, stroke_width, opacity,
    fill, and fill_opacity.

    Returns dict with stdout, stderr, return_code, and parsed paths.
    """
    # Generate BRUSHES list from presets (ensures consistency with types.py)
    brushes_list = json.dumps(list(BRUSH_PRESETS.keys()))

    # Prepend canvas dimensions as variables
    full_code = f"""
import math
import random
import json

# Canvas dimensions
canvas_width = {canvas_width}
canvas_height = {canvas_height}

# Available brush presets for paint mode (generated from BRUSH_PRESETS)
BRUSHES = {brushes_list}

# Helper function to add style properties to a path dict
def _add_style(path_dict: dict, brush=None, color=None, stroke_width=None, opacity=None, fill=None, fill_opacity=None) -> dict:
    \"\"\"Add optional style and brush properties to a path dict.\"\"\"
    if brush is not None:
        path_dict["brush"] = brush
    if color is not None:
        path_dict["color"] = color
    if stroke_width is not None:
        path_dict["stroke_width"] = stroke_width
    if opacity is not None:
        path_dict["opacity"] = opacity
    if fill is not None:
        path_dict["fill"] = fill
    if fill_opacity is not None:
        path_dict["fill_opacity"] = fill_opacity
    return path_dict

# Helper functions for generating paths (all support optional brush and style parameters)
def svg_path(d: str, brush=None, color=None, stroke_width=None, opacity=None, fill=None, fill_opacity=None) -> dict:
    \"\"\"Create an SVG path dict with optional brush and style.\"\"\"
    return _add_style({{"type": "svg", "d": d}}, brush, color, stroke_width, opacity, fill, fill_opacity)

def filled_svg_path(d: str, fill: str, fill_opacity: float = 1.0, stroke=None, stroke_width=0, opacity=None) -> dict:
    \"\"\"Create a closed filled SVG path. Use this for silhouettes, backgrounds, clouds, land, water, and large color masses.\"\"\"
    return svg_path(d, color=stroke, stroke_width=stroke_width, opacity=opacity, fill=fill, fill_opacity=fill_opacity)

def filled_polygon_path(vertices, fill: str, fill_opacity: float = 1.0, stroke=None, stroke_width=0, opacity=None) -> dict:
    \"\"\"Create a filled polygon path from (x, y) vertices.\"\"\"
    if not vertices:
        return filled_svg_path("M 0 0 Z", fill, fill_opacity, stroke, stroke_width, opacity)
    commands = ["M {{}} {{}}".format(vertices[0][0], vertices[0][1])]
    for x, y in vertices[1:]:
        commands.append("L {{}} {{}}".format(x, y))
    commands.append("Z")
    return filled_svg_path(" ".join(commands), fill, fill_opacity, stroke, stroke_width, opacity)

def rect_shape(x: float, y: float, width: float, height: float, fill: str, fill_opacity: float = 1.0, stroke=None, stroke_width=0, opacity=None) -> dict:
    \"\"\"Create a filled rectangle. Use rect_shape(0, 0, canvas_width, canvas_height, color) for a solid ground.\"\"\"
    d = "M {{}} {{}} L {{}} {{}} L {{}} {{}} L {{}} {{}} Z".format(
        x, y, x + width, y, x + width, y + height, x, y + height
    )
    return filled_svg_path(d, fill, fill_opacity, stroke, stroke_width, opacity)

def ellipse_shape(cx: float, cy: float, rx: float, ry: float, fill: str, fill_opacity: float = 1.0, stroke=None, stroke_width=0, opacity=None) -> dict:
    \"\"\"Create a filled ellipse with cubic Beziers.\"\"\"
    k = 0.5522847498
    d = (
        "M {{}} {{}} C {{}} {{}} {{}} {{}} {{}} {{}} "
        "C {{}} {{}} {{}} {{}} {{}} {{}} "
        "C {{}} {{}} {{}} {{}} {{}} {{}} "
        "C {{}} {{}} {{}} {{}} {{}} {{}} Z"
    ).format(
        cx + rx, cy,
        cx + rx, cy + k * ry, cx + k * rx, cy + ry, cx, cy + ry,
        cx - k * rx, cy + ry, cx - rx, cy + k * ry, cx - rx, cy,
        cx - rx, cy - k * ry, cx - k * rx, cy - ry, cx, cy - ry,
        cx + k * rx, cy - ry, cx + rx, cy - k * ry, cx + rx, cy,
    )
    return filled_svg_path(d, fill, fill_opacity, stroke, stroke_width, opacity)

def line(x1: float, y1: float, x2: float, y2: float, brush=None, color=None, stroke_width=None, opacity=None) -> dict:
    \"\"\"Create a line path with optional brush and style.\"\"\"
    return _add_style(
        {{"type": "line", "points": [{{"x": x1, "y": y1}}, {{"x": x2, "y": y2}}]}},
        brush, color, stroke_width, opacity
    )

def dab(x: float, y: float, length: float, angle: float, brush="oil_filbert", color=None, stroke_width=None, opacity=None) -> dict:
    \"\"\"Create a short broken brush mark. Ideal for impressionist optical-color dabs.\"\"\"
    tx = math.cos(angle)
    ty = math.sin(angle)
    nx = -ty
    ny = tx
    bend = random.uniform(-0.18, 0.18) * length
    wobble = max(1.0, length * 0.035)
    x1 = x - tx * length / 2 + random.uniform(-wobble, wobble)
    y1 = y - ty * length / 2 + random.uniform(-wobble, wobble)
    x2 = x + tx * length / 2 + random.uniform(-wobble, wobble)
    y2 = y + ty * length / 2 + random.uniform(-wobble, wobble)
    cx = x + nx * bend + random.uniform(-wobble, wobble)
    cy = y + ny * bend + random.uniform(-wobble, wobble)
    return quadratic(x1, y1, cx, cy, x2, y2, brush=brush, color=color, stroke_width=stroke_width, opacity=opacity)

def _choose(value, default):
    return default if value is None else value

def _rand_range(pair, default):
    low, high = _choose(pair, default)
    return random.uniform(low, high)

def _hex_to_rgb(color: str):
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

def _rgb_to_hex(rgb):
    return "#{{:02x}}{{:02x}}{{:02x}}".format(
        max(0, min(255, int(rgb[0]))),
        max(0, min(255, int(rgb[1]))),
        max(0, min(255, int(rgb[2]))),
    )

def _mix_hex(a: str, b: str, t: float) -> str:
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    return _rgb_to_hex((
        ar + (br - ar) * t,
        ag + (bg - ag) * t,
        ab + (bb - ab) * t,
    ))

def _luminance(color: str) -> float:
    red, green, blue = _hex_to_rgb(color)
    return red * 0.2126 + green * 0.7152 + blue * 0.0722

def _jitter_hex(color: str, amount: int = 10) -> str:
    r, g, b = _hex_to_rgb(color)
    return _rgb_to_hex((
        r + random.uniform(-amount, amount),
        g + random.uniform(-amount, amount),
        b + random.uniform(-amount, amount),
    ))

def _color_from_stops(stops, t: float) -> str:
    if not stops:
        return "#d8c7a4"
    ordered = sorted(stops, key=lambda stop: stop[0])
    if t <= ordered[0][0]:
        return random.choice(ordered[0][1])
    for (left_t, left_colors), (right_t, right_colors) in zip(ordered, ordered[1:]):
        if t <= right_t:
            span = max(1e-9, right_t - left_t)
            local_t = (t - left_t) / span
            return _jitter_hex(_mix_hex(random.choice(left_colors), random.choice(right_colors), local_t))
    return random.choice(ordered[-1][1])

def _color_from_palette(colors, stops, t: float) -> str:
    if stops is not None:
        return _color_from_stops(stops, t)
    return random.choice(colors)

def _polygon_bounds(vertices):
    return (
        min(p[0] for p in vertices),
        max(p[0] for p in vertices),
        min(p[1] for p in vertices),
        max(p[1] for p in vertices),
    )

def _polygon_spans_at_y(vertices, y: float):
    crossings = []
    for a, b in zip(vertices, vertices[1:] + vertices[:1]):
        x1, y1 = a
        x2, y2 = b
        if y1 == y2:
            continue
        if (y1 <= y < y2) or (y2 <= y < y1):
            t = (y - y1) / (y2 - y1)
            crossings.append(x1 + (x2 - x1) * t)
    crossings.sort()
    spans = []
    for i in range(0, len(crossings) - 1, 2):
        left = crossings[i]
        right = crossings[i + 1]
        if right - left > 1:
            spans.append((left, right))
    return spans

def _axis_t(axis: str, x: float, y: float, bounds) -> float:
    min_x, max_x, min_y, max_y = bounds
    if axis == "x":
        return 0 if max_x == min_x else (x - min_x) / (max_x - min_x)
    return 0 if max_y == min_y else (y - min_y) / (max_y - min_y)

def _target_count_with_texture(count: int, wash_count: int, texture_ratio: float) -> int:
    ratio = max(0.0, float(texture_ratio))
    return wash_count + int(max(0, count - wash_count) * ratio)

def stroke_field(
    count: int,
    x_range=None,
    y_range=None,
    angle: float = 0,
    angle_jitter: float = 0.2,
    length_range=None,
    width_range=None,
    colors=None,
    brushes=None,
    opacity_range=None,
    exclude_polygons=None,
) -> list:
    \"\"\"Create a field of loose brush marks for atmosphere, water, grass, shadow, crowds, or texture.\"\"\"
    x_range = _choose(x_range, (0, canvas_width))
    y_range = _choose(y_range, (0, canvas_height))
    length_range = _choose(length_range, (8, 48))
    width_range = _choose(width_range, (3, 14))
    opacity_range = _choose(opacity_range, (0.2, 0.65))
    colors = _choose(colors, ["#6f8fa8", "#d8c7a4", "#f2e6c9"])
    brushes = _choose(brushes, ["oil_filbert", "watercolor", "dry_brush"])
    exclude_polygons = _choose(exclude_polygons, [])
    paths = []
    attempts = 0
    while len(paths) < count and attempts < count * 30:
        attempts += 1
        depth = 0 if y_range[1] == y_range[0] else (random.uniform(*y_range) - y_range[0]) / (y_range[1] - y_range[0])
        x = random.uniform(*x_range)
        y = y_range[0] + depth * (y_range[1] - y_range[0])
        if any(_inside_polygon(x, y, polygon) for polygon in exclude_polygons):
            continue
        length = _rand_range(length_range, (8, 48)) * (0.85 + 0.35 * depth)
        paths.append(dab(
            x,
            y,
            length,
            angle + random.uniform(-angle_jitter, angle_jitter),
            brush=random.choice(brushes),
            color=random.choice(colors),
            stroke_width=_rand_range(width_range, (4, 16)),
            opacity=_rand_range(opacity_range, (0.2, 0.65)),
        ))
    return paths

def ramp_field(
    count: int,
    x_range=None,
    y_range=None,
    axis: str = "y",
    stops=None,
    angle: float = 0,
    angle_jitter: float = 0.16,
    length_range=None,
    width_range=None,
    brushes=None,
    opacity_range=None,
    exclude_polygons=None,
    wash_rows: int | None = None,
    texture_ratio: float = 1.0,
) -> list:
    \"\"\"Create a directional color-ramp field for sky, water, walls, fields, fabric, fog, or any broad plane.\"\"\"
    x_range = _choose(x_range, (0, canvas_width))
    y_range = _choose(y_range, (0, canvas_height))
    stops = _choose(stops, [
        (0.0, ["#6f8fa8", "#8798c6"]),
        (0.5, ["#f2d1a2", "#f6b06f"]),
        (1.0, ["#f7e7bf", "#fff1d0"]),
    ])
    length_range = _choose(length_range, (28, 110))
    width_range = _choose(width_range, (8, 28))
    brushes = _choose(brushes, ["watercolor", "airbrush", "oil_flat"])
    opacity_range = _choose(opacity_range, (0.12, 0.42))
    exclude_polygons = _choose(exclude_polygons, [])
    paths = []
    rows = max(0, count // 22 if wash_rows is None else wash_rows)
    for row in range(rows):
        t = (row + 0.5) / max(1, rows)
        y = y_range[0] + t * (y_range[1] - y_range[0])
        x_step = max(40, (x_range[1] - x_range[0]) / 8)
        points = []
        x = x_range[0] - random.uniform(0, 25)
        while x <= x_range[1] + 25:
            points.append((x, y + random.uniform(-8, 8)))
            x += x_step
        paths.append(polyline(
            *points,
            brush=random.choice(brushes),
            color=_color_from_stops(stops, t),
            stroke_width=_rand_range(width_range, (8, 28)) * 1.35,
            opacity=_rand_range(opacity_range, (0.12, 0.42)) * 0.72,
        ))
    attempts = 0
    target_count = _target_count_with_texture(count, rows, texture_ratio)
    while len(paths) < target_count and attempts < max(1, target_count) * 30:
        attempts += 1
        x = random.uniform(*x_range)
        y = random.uniform(*y_range)
        if any(_inside_polygon(x, y, polygon) for polygon in exclude_polygons):
            continue
        if axis == "x":
            t = 0 if x_range[1] == x_range[0] else (x - x_range[0]) / (x_range[1] - x_range[0])
        else:
            t = 0 if y_range[1] == y_range[0] else (y - y_range[0]) / (y_range[1] - y_range[0])
        paths.append(dab(
            x,
            y,
            _rand_range(length_range, (28, 110)) * (0.75 + 0.35 * t),
            angle + random.uniform(-angle_jitter, angle_jitter),
            brush=random.choice(brushes),
            color=_color_from_stops(stops, t),
            stroke_width=_rand_range(width_range, (8, 28)),
            opacity=_rand_range(opacity_range, (0.12, 0.42)),
        ))
    return paths

def background_wash(
    count: int = 420,
    stops=None,
    y_range=None,
    angle: float = 0.0,
    angle_jitter: float = 0.08,
    length_range=None,
    width_range=None,
    brushes=None,
    opacity_range=None,
    exclude_polygons=None,
    wash_rows: int = 14,
    texture_ratio: float = 0.18,
) -> list:
    \"\"\"Lay a full-canvas colored ground before subjects: sky, paper tone, atmosphere, sea, wall, stage, or shadow field.\"\"\"
    y_range = _choose(y_range, (0, canvas_height))
    stops = _choose(stops, [
        (0.0, ["#dbe7f4", "#c9d9ee", "#b7c7d8"]),
        (0.55, ["#f7ead0", "#e9d9b5", "#d8c7a4"]),
        (1.0, ["#b7c7d8", "#91a7b8", "#6f8fa8"]),
    ])
    length_range = _choose(length_range, (120, 280))
    width_range = _choose(width_range, (18, 30))
    brushes = _choose(brushes, ["watercolor", "airbrush", "oil_flat"])
    opacity_range = _choose(opacity_range, (0.34, 0.74))
    exclude_polygons = _choose(exclude_polygons, [])
    paths = ramp_field(
        count,
        x_range=(-30, canvas_width + 30),
        y_range=y_range,
        axis="y",
        stops=stops,
        angle=angle,
        angle_jitter=angle_jitter,
        length_range=length_range,
        width_range=width_range,
        brushes=brushes,
        opacity_range=opacity_range,
        exclude_polygons=exclude_polygons,
        wash_rows=wash_rows,
        texture_ratio=texture_ratio,
    )
    return paths

def curve_marks(
    points,
    count: int = 48,
    length_range=None,
    width_range=None,
    colors=None,
    brushes=None,
    opacity_range=None,
    jitter: float = 5,
) -> list:
    \"\"\"Place painterly marks along a polyline skeleton: stems, masts, roads, branches, shorelines, contours.\"\"\"
    length_range = _choose(length_range, (10, 28))
    width_range = _choose(width_range, (4, 14))
    opacity_range = _choose(opacity_range, (0.28, 0.7))
    colors = _choose(colors, ["#3f5f52", "#6f7a64", "#d8c7a4"])
    brushes = _choose(brushes, ["oil_filbert", "dry_brush", "watercolor"])
    segments = []
    total = 0
    for a, b in zip(points, points[1:]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length > 0:
            segments.append((a, b, length, total))
            total += length
    if not segments:
        return []
    paths = []
    for _ in range(count):
        target = random.uniform(0, total)
        a, b, seg_length, seg_start = segments[-1]
        for segment in segments:
            if target <= segment[3] + segment[2]:
                a, b, seg_length, seg_start = segment
                break
        t = (target - seg_start) / seg_length
        x = a[0] + (b[0] - a[0]) * t + random.uniform(-jitter, jitter)
        y = a[1] + (b[1] - a[1]) * t + random.uniform(-jitter, jitter)
        angle = math.atan2(b[1] - a[1], b[0] - a[0]) + random.uniform(-0.35, 0.35)
        paths.append(dab(
            x,
            y,
            _rand_range(length_range, (10, 28)),
            angle,
            brush=random.choice(brushes),
            color=random.choice(colors),
            stroke_width=_rand_range(width_range, (4, 14)),
            opacity=_rand_range(opacity_range, (0.28, 0.7)),
        ))
    return paths

def _polyline_lengths(points):
    lengths = []
    total = 0
    for a, b in zip(points, points[1:]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        lengths.append((a, b, length, total))
        total += length
    return lengths, total

def _sample_polyline(points, t: float):
    if not points:
        return (0, 0), 0
    if len(points) == 1:
        return points[0], 0
    segments, total = _polyline_lengths(points)
    if total <= 0:
        return points[0], 0
    target = max(0, min(1, t)) * total
    a, b, seg_length, seg_start = segments[-1]
    for segment in segments:
        if target <= segment[3] + segment[2]:
            a, b, seg_length, seg_start = segment
            break
    local_t = 0 if seg_length == 0 else (target - seg_start) / seg_length
    x = a[0] + (b[0] - a[0]) * local_t
    y = a[1] + (b[1] - a[1]) * local_t
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    return (x, y), angle

def _resample_polyline(points, count: int):
    if count <= 1:
        return [points[0]] if points else []
    return [_sample_polyline(points, i / (count - 1))[0] for i in range(count)]

def _inside_polygon(x: float, y: float, vertices) -> bool:
    inside = False
    j = len(vertices) - 1
    for i in range(len(vertices)):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        crosses = (yi > y) != (yj > y)
        if crosses:
            slope_x = (xj - xi) * (y - yi) / max(1e-9, yj - yi) + xi
            if x < slope_x:
                inside = not inside
        j = i
    return inside

def mass_field(
    vertices,
    count: int = 180,
    colors=None,
    stops=None,
    axis: str = "y",
    angle: float = 0,
    angle_jitter: float = 0.28,
    length_range=None,
    width_range=None,
    brushes=None,
    opacity_range=None,
    wash_rows: int | None = None,
    edge: bool = False,
    texture_ratio: float = 1.0,
) -> list:
    \"\"\"Fill a closed mass with broad wash rows plus sparse texture: land, water, sky holes, shadows, fabric, smoke, walls, light shapes.\"\"\"
    if len(vertices) < 3:
        return []
    colors = _choose(colors, ["#5f7656", "#84956b", "#d8b06a"])
    brushes = _choose(brushes, ["oil_flat", "watercolor", "dry_brush"])
    length_range = _choose(length_range, (14, 54))
    width_range = _choose(width_range, (6, 22))
    opacity_range = _choose(opacity_range, (0.24, 0.7))
    bounds = _polygon_bounds(vertices)
    min_x, max_x, min_y, max_y = bounds
    paths = []

    rows = max(0, count // 42 if wash_rows is None else wash_rows)
    for row in range(rows):
        t = (row + 0.5) / max(1, rows)
        y = min_y + t * (max_y - min_y)
        for left, right in _polygon_spans_at_y(vertices, y):
            point_count = max(3, int((right - left) / 42))
            points = []
            for i in range(point_count):
                px_t = i / max(1, point_count - 1)
                x = left + px_t * (right - left)
                points.append((x + random.uniform(-5, 5), y + random.uniform(-6, 6)))
            color_t = _axis_t(axis, (left + right) / 2, y, bounds)
            paths.append(polyline(
                *points,
                brush=random.choice(brushes),
                color=_color_from_palette(colors, stops, color_t),
                stroke_width=_rand_range(width_range, (6, 22)) * 1.35,
                opacity=_rand_range(opacity_range, (0.24, 0.7)) * 0.72,
            ))

    attempts = 0
    target_count = _target_count_with_texture(count, rows, texture_ratio)
    while len(paths) < target_count and attempts < max(1, target_count) * 45:
        attempts += 1
        x = random.uniform(min_x, max_x)
        y = random.uniform(min_y, max_y)
        if not _inside_polygon(x, y, vertices):
            continue
        color_t = _axis_t(axis, x, y, bounds)
        depth = 0 if max_y == min_y else (y - min_y) / (max_y - min_y)
        paths.append(dab(
            x,
            y,
            _rand_range(length_range, (14, 54)) * (0.85 + depth * 0.25),
            angle + random.uniform(-angle_jitter, angle_jitter),
            brush=random.choice(brushes),
            color=_color_from_palette(colors, stops, color_t),
            stroke_width=_rand_range(width_range, (6, 22)),
            opacity=_rand_range(opacity_range, (0.24, 0.7)),
        ))

    if edge:
        paths.extend(broken_edge(
            vertices + [vertices[0]],
            count=max(12, int(count * 0.08)),
            colors=colors,
            brushes=["dry_brush", "watercolor"],
            length_range=(8, max(16, length_range[0] * 2)),
            width_range=(max(1.5, width_range[0] * 0.35), max(3.0, width_range[0] * 0.85)),
            opacity_range=(0.16, min(0.52, opacity_range[1])),
            spread=4,
        ))
    return paths

def curve_band(
    top_points,
    bottom_points=None,
    bottom_y: float | None = None,
    count: int = 180,
    colors=None,
    stops=None,
    axis: str = "depth",
    brushes=None,
    length_range=None,
    width_range=None,
    opacity_range=None,
    angle_jitter: float = 0.28,
    edge: bool = True,
    wash_rows: int | None = None,
    texture_ratio: float = 1.0,
) -> list:
    \"\"\"Fill a curved band between two contours: hills, clouds, shadows, roads, rivers, cloth folds, light planes.\"\"\"
    if len(top_points) < 2:
        return []
    if bottom_points is None:
        y = canvas_height if bottom_y is None else bottom_y
        bottom_points = [(top_points[0][0], y), (top_points[-1][0], y)]
    samples = max(10, len(top_points) * 8)
    top = _resample_polyline(top_points, samples)
    bottom = _resample_polyline(bottom_points, samples)
    polygon = top + list(reversed(bottom))
    colors = _choose(colors, ["#5f7656", "#84956b", "#d8b06a"])
    brushes = _choose(brushes, ["oil_flat", "dry_brush", "watercolor"])
    length_range = _choose(length_range, (12, 46))
    width_range = _choose(width_range, (5, 18))
    opacity_range = _choose(opacity_range, (0.26, 0.72))
    paths = []
    rows = max(0, count // 38 if wash_rows is None else wash_rows)
    for row in range(rows):
        depth = (row + 0.5) / max(1, rows)
        row_points = []
        for top_point, bottom_point in zip(top, bottom):
            row_points.append((
                top_point[0] + (bottom_point[0] - top_point[0]) * depth + random.uniform(-4, 4),
                top_point[1] + (bottom_point[1] - top_point[1]) * depth + random.uniform(-5, 5),
            ))
        paths.append(polyline(
            *row_points,
            brush=random.choice(brushes),
            color=_color_from_palette(colors, stops, depth),
            stroke_width=_rand_range(width_range, (5, 18)) * 1.25,
            opacity=_rand_range(opacity_range, (0.26, 0.72)) * 0.68,
        ))
    attempts = 0
    min_x = min(p[0] for p in polygon)
    max_x = max(p[0] for p in polygon)
    min_y = min(p[1] for p in polygon)
    max_y = max(p[1] for p in polygon)
    target_count = _target_count_with_texture(count, rows, texture_ratio)
    while len(paths) < target_count and attempts < max(1, target_count) * 50:
        attempts += 1
        x = random.uniform(min_x, max_x)
        y = random.uniform(min_y, max_y)
        if not _inside_polygon(x, y, polygon):
            continue
        nearest_t = 0
        nearest_distance = None
        for i, point in enumerate(top):
            distance = abs(point[0] - x)
            if nearest_distance is None or distance < nearest_distance:
                nearest_distance = distance
                nearest_t = i / max(1, len(top) - 1)
        _, tangent = _sample_polyline(top_points, nearest_t)
        depth = 0 if max_y == min_y else (y - min_y) / (max_y - min_y)
        if axis == "x":
            color_t = 0 if max_x == min_x else (x - min_x) / (max_x - min_x)
        elif axis == "y":
            color_t = depth
        else:
            color_t = depth
        paths.append(dab(
            x,
            y,
            _rand_range(length_range, (12, 46)) * (0.9 + depth * 0.28),
            tangent + random.uniform(-angle_jitter, angle_jitter),
            brush=random.choice(brushes),
            color=_color_from_palette(colors, stops, color_t),
            stroke_width=_rand_range(width_range, (5, 18)),
            opacity=_rand_range(opacity_range, (0.26, 0.72)),
        ))
    if edge:
        paths.extend(curve_marks(
            top_points,
            count=max(12, int(count * 0.12)),
            length_range=(8, max(16, length_range[0] * 2)),
            width_range=(max(1.5, width_range[0] * 0.4), max(3.0, width_range[0] * 0.9)),
            colors=colors,
            brushes=["dry_brush", "watercolor"],
            opacity_range=(0.18, min(0.5, opacity_range[1])),
            jitter=3,
        ))
    return paths

def _width_at(widths, t: float) -> float:
    if isinstance(widths, (int, float)):
        return float(widths)
    if not widths:
        return 60.0
    if len(widths) == 1:
        return float(widths[0])
    scaled = max(0, min(1, t)) * (len(widths) - 1)
    index = min(len(widths) - 2, int(scaled))
    local_t = scaled - index
    return float(widths[index]) + (float(widths[index + 1]) - float(widths[index])) * local_t

def _band_polygon(center_points, widths, samples: int = 32):
    left = []
    right = []
    for i in range(max(2, samples)):
        t = i / max(1, samples - 1)
        (x, y), angle = _sample_polyline(center_points, t)
        half_width = _width_at(widths, t) / 2
        nx = -math.sin(angle)
        ny = math.cos(angle)
        left.append((x + nx * half_width, y + ny * half_width))
        right.append((x - nx * half_width, y - ny * half_width))
    return left + list(reversed(right))

def tapered_band(
    center_points,
    widths,
    count: int = 150,
    colors=None,
    stops=None,
    axis: str = "y",
    flow: str = "horizontal",
    brushes=None,
    length_range=None,
    width_range=None,
    opacity_range=None,
    angle_jitter: float = 0.18,
    wash_rows: int | None = None,
    edge: bool = False,
    texture_ratio: float = 1.0,
) -> list:
    \"\"\"Fill a tapered ribbon around a centerline: river, road, path, beam of light, cast shadow, wake, smoke plume, or cloud streak.\"\"\"
    if len(center_points) < 2:
        return []
    colors = _choose(colors, ["#9bb9c8", "#f2d3b0", "#526f7d"])
    brushes = _choose(brushes, ["oil_flat", "watercolor", "dry_brush"])
    length_range = _choose(length_range, (18, 70))
    width_range = _choose(width_range, (5, 20))
    opacity_range = _choose(opacity_range, (0.2, 0.66))
    polygon = _band_polygon(center_points, widths, samples=max(12, len(center_points) * 10))
    paths = mass_field(
        polygon,
        count=max(0, count // 3),
        colors=colors,
        stops=stops,
        axis=axis,
        angle=0,
        angle_jitter=0.08,
        length_range=length_range,
        width_range=width_range,
        brushes=brushes,
        opacity_range=(opacity_range[0] * 0.75, opacity_range[1] * 0.78),
        wash_rows=max(1, count // 46) if wash_rows is None else wash_rows,
        edge=False,
        texture_ratio=texture_ratio,
    )
    bounds = _polygon_bounds(polygon)
    min_x, max_x, min_y, max_y = bounds
    center_samples = [
        (*_sample_polyline(center_points, i / 32)[0], _sample_polyline(center_points, i / 32)[1])
        for i in range(33)
    ]
    attempts = 0
    target_count = _target_count_with_texture(count, len(paths), texture_ratio)
    while len(paths) < target_count and attempts < max(1, target_count) * 50:
        attempts += 1
        x = random.uniform(min_x, max_x)
        y = random.uniform(min_y, max_y)
        if not _inside_polygon(x, y, polygon):
            continue
        nearest = min(center_samples, key=lambda sample: (sample[0] - x) ** 2 + (sample[1] - y) ** 2)
        path_angle = nearest[2]
        if flow == "path":
            mark_angle = path_angle
        elif flow == "vertical":
            mark_angle = math.pi / 2
        else:
            mark_angle = 0
        color_t = _axis_t(axis, x, y, bounds)
        paths.append(dab(
            x,
            y,
            _rand_range(length_range, (18, 70)),
            mark_angle + random.uniform(-angle_jitter, angle_jitter),
            brush=random.choice(brushes),
            color=_color_from_palette(colors, stops, color_t),
            stroke_width=_rand_range(width_range, (5, 20)),
            opacity=_rand_range(opacity_range, (0.2, 0.66)),
        ))
    if edge:
        paths.extend(broken_edge(
            polygon + [polygon[0]],
            count=max(12, int(count * 0.08)),
            colors=colors,
            brushes=["dry_brush", "watercolor"],
            opacity_range=(0.14, min(0.46, opacity_range[1])),
            spread=5,
        ))
    return paths

def broken_edge(
    points,
    count: int = 64,
    colors=None,
    brushes=None,
    length_range=None,
    width_range=None,
    opacity_range=None,
    spread: float = 6,
    side: int = 0,
    angle_jitter: float = 0.32,
) -> list:
    \"\"\"Feather an edge with broken marks: ridges, shorelines, silhouettes, object contours, reflected glints, cloud rims.\"\"\"
    if len(points) < 2:
        return []
    colors = _choose(colors, ["#f2c06b", "#4b5f60", "#2d3936"])
    brushes = _choose(brushes, ["dry_brush", "oil_filbert", "watercolor"])
    length_range = _choose(length_range, (8, 38))
    width_range = _choose(width_range, (2, 10))
    opacity_range = _choose(opacity_range, (0.16, 0.58))
    paths = []
    for _ in range(count):
        t = random.random()
        (x, y), angle = _sample_polyline(points, t)
        normal_side = side if side != 0 else random.choice([-1, 1])
        offset = random.uniform(0, spread) * normal_side
        nx = -math.sin(angle)
        ny = math.cos(angle)
        paths.append(dab(
            x + nx * offset,
            y + ny * offset,
            _rand_range(length_range, (8, 38)),
            angle + random.uniform(-angle_jitter, angle_jitter),
            brush=random.choice(brushes),
            color=random.choice(colors),
            stroke_width=_rand_range(width_range, (2, 10)),
            opacity=_rand_range(opacity_range, (0.16, 0.58)),
        ))
    return paths

def fill_polygon(
    vertices,
    count: int = 120,
    angle: float = 0,
    angle_jitter: float = 0.35,
    length_range=None,
    width_range=None,
    colors=None,
    brushes=None,
    opacity_range=None,
    edge: bool = True,
) -> list:
    \"\"\"Fill any polygon with optical-color brush marks: sails, petals, roofs, figures, shadows, land masses.\"\"\"
    length_range = _choose(length_range, (10, 34))
    width_range = _choose(width_range, (5, 18))
    opacity_range = _choose(opacity_range, (0.26, 0.72))
    colors = _choose(colors, ["#f7ead0", "#d8c7a4", "#b7c7d8"])
    brushes = _choose(brushes, ["oil_filbert", "oil_round", "dry_brush"])
    min_x = min(p[0] for p in vertices)
    max_x = max(p[0] for p in vertices)
    min_y = min(p[1] for p in vertices)
    max_y = max(p[1] for p in vertices)
    paths = []
    attempts = 0
    while len(paths) < count and attempts < count * 40:
        attempts += 1
        x = random.uniform(min_x, max_x)
        y = random.uniform(min_y, max_y)
        if not _inside_polygon(x, y, vertices):
            continue
        paths.append(dab(
            x,
            y,
            _rand_range(length_range, (10, 34)),
            angle + random.uniform(-angle_jitter, angle_jitter),
            brush=random.choice(brushes),
            color=random.choice(colors),
            stroke_width=_rand_range(width_range, (5, 18)),
            opacity=_rand_range(opacity_range, (0.26, 0.72)),
        ))
    if edge:
        for a, b in zip(vertices, vertices[1:] + vertices[:1]):
            paths.append(line(
                a[0],
                a[1],
                b[0],
                b[1],
                brush="dry_brush",
                color=random.choice(colors),
                stroke_width=max(1.5, width_range[0] * 0.32),
                opacity=min(0.55, opacity_range[1]),
            ))
    return paths

def glow_field(
    cx: float,
    cy: float,
    radius: float,
    count: int = 140,
    colors=None,
    brushes=None,
    length_range=None,
    width_range=None,
    opacity_range=None,
    elliptical_y: float = 0.72,
    exclude_polygons=None,
    core_marks: int | None = None,
) -> list:
    \"\"\"Create a soft radial light field for sun, lamps, mist, fire, reflected glare, halos, or focal atmosphere.\"\"\"
    colors = _choose(colors, ["#fff3b0", "#ffd38a", "#f49a6a", "#f7d8b8"])
    brushes = _choose(brushes, ["watercolor", "airbrush", "oil_filbert"])
    length_range = _choose(length_range, (12, 58))
    width_range = _choose(width_range, (6, 28))
    opacity_range = _choose(opacity_range, (0.12, 0.48))
    exclude_polygons = _choose(exclude_polygons, [])
    paths = []
    core_count = max(0, count // 18 if core_marks is None else core_marks)
    for _ in range(core_count):
        angle = random.random() * math.tau
        distance = radius * 0.16 * math.sqrt(random.random())
        x = cx + math.cos(angle) * distance
        y = cy + math.sin(angle) * distance * elliptical_y
        paths.append(dab(
            x,
            y,
            _rand_range(length_range, (12, 58)) * 0.55,
            angle + math.pi / 2 + random.uniform(-0.55, 0.55),
            brush=random.choice(["watercolor", "airbrush", "oil_filbert"]),
            color=random.choice(colors),
            stroke_width=_rand_range(width_range, (6, 28)) * 0.75,
            opacity=min(0.72, _rand_range(opacity_range, (0.12, 0.48)) * 1.45),
        ))
    attempts = 0
    while len(paths) < count and attempts < count * 35:
        attempts += 1
        angle = random.random() * math.tau
        distance = radius * math.sqrt(random.random())
        x = cx + math.cos(angle) * distance
        y = cy + math.sin(angle) * distance * elliptical_y
        if any(_inside_polygon(x, y, polygon) for polygon in exclude_polygons):
            continue
        falloff = max(0, 1 - distance / max(1, radius))
        mark_angle = angle + math.pi / 2 + random.uniform(-0.45, 0.45)
        paths.append(dab(
            x,
            y,
            _rand_range(length_range, (12, 58)) * (0.45 + falloff),
            mark_angle,
            brush=random.choice(brushes),
            color=random.choice(colors),
            stroke_width=_rand_range(width_range, (6, 28)) * (0.55 + falloff * 0.75),
            opacity=_rand_range(opacity_range, (0.12, 0.48)) * (0.4 + falloff * 0.9),
        ))
    return paths

def reflection_field(
    cx: float,
    y: float,
    width: float,
    height: float,
    count: int = 72,
    angle: float = 0,
    colors=None,
    brushes=None,
    opacity_range=None,
) -> list:
    \"\"\"Create tapering mirrored marks under any subject: boats, trees, buildings, figures, clouds.\"\"\"
    colors = _choose(colors, ["#f7efe1", "#d8c7a4", "#9bb9c8", "#7d86ad", "#3f6578"])
    brushes = _choose(brushes, ["oil_filbert", "dry_brush", "watercolor"])
    opacity_range = _choose(opacity_range, (0.18, 0.58))
    paths = []
    for _ in range(count):
        t = random.random()
        band_width = width * (1 - t * 0.72)
        x = cx + random.uniform(-band_width / 2, band_width / 2)
        yy = y + t * height + random.uniform(-5, 5)
        length = random.uniform(14, max(20, band_width * random.uniform(0.1, 0.32)))
        paths.append(dab(
            x,
            yy,
            length,
            angle + random.uniform(-0.05, 0.05),
            brush=random.choice(brushes),
            color=random.choice(colors),
            stroke_width=random.uniform(3, 15),
            opacity=_rand_range(opacity_range, (0.18, 0.58)),
        ))
    return paths

def radial_cluster(
    cx: float,
    cy: float,
    count: int = 160,
    rx: float = 80,
    ry: float = 60,
    colors=None,
    brushes=None,
    length_range=None,
    width_range=None,
    opacity_range=None,
) -> list:
    \"\"\"Create an organic oval cluster for blooms, clouds, tree crowns, crowds, rocks, or reflected light.\"\"\"
    colors = _choose(colors, ["#f0b8c8", "#d8c7a4", "#b9c7df"])
    brushes = _choose(brushes, ["oil_filbert", "oil_round", "dry_brush"])
    length_range = _choose(length_range, (8, 32))
    width_range = _choose(width_range, (5, 18))
    opacity_range = _choose(opacity_range, (0.28, 0.74))
    paths = []
    for _ in range(count):
        a = random.random() * math.tau
        r = min(1.0, abs(random.gauss(0.45, 0.28)))
        x = cx + math.cos(a) * rx * r
        y = cy + math.sin(a) * ry * r
        paths.append(dab(
            x,
            y,
            _rand_range(length_range, (8, 32)),
            a + math.pi / 2 + random.uniform(-0.8, 0.8),
            brush=random.choice(brushes),
            color=random.choice(colors),
            stroke_width=_rand_range(width_range, (5, 18)),
            opacity=_rand_range(opacity_range, (0.28, 0.74)),
        ))
    return paths

def polyline(*points, brush=None, color=None, stroke_width=None, opacity=None) -> dict:
    \"\"\"Create a polyline from (x, y) tuples with optional brush and style.\"\"\"
    return _add_style(
        {{"type": "polyline", "points": [{{"x": p[0], "y": p[1]}} for p in points]}},
        brush, color, stroke_width, opacity
    )

def quadratic(x1: float, y1: float, cx: float, cy: float, x2: float, y2: float, brush=None, color=None, stroke_width=None, opacity=None) -> dict:
    \"\"\"Create a quadratic bezier curve with optional brush and style.\"\"\"
    return _add_style(
        {{"type": "quadratic", "points": [
            {{"x": x1, "y": y1}}, {{"x": cx, "y": cy}}, {{"x": x2, "y": y2}}
        ]}},
        brush, color, stroke_width, opacity
    )

def cubic(x1: float, y1: float, cx1: float, cy1: float, cx2: float, cy2: float, x2: float, y2: float, brush=None, color=None, stroke_width=None, opacity=None) -> dict:
    \"\"\"Create a cubic bezier curve with optional brush and style.\"\"\"
    return _add_style(
        {{"type": "cubic", "points": [
            {{"x": x1, "y": y1}}, {{"x": cx1, "y": cy1}}, {{"x": cx2, "y": cy2}}, {{"x": x2, "y": y2}}
        ]}},
        brush, color, stroke_width, opacity
    )

def sector_bounds(column: int, row: int, columns: int = 3, rows: int = 3, padding: float = 0) -> tuple:
    \"\"\"Return (left, top, right, bottom) for a compositional sector of the current canvas.\"\"\"
    cell_w = canvas_width / max(1, columns)
    cell_h = canvas_height / max(1, rows)
    left = column * cell_w + padding
    top = row * cell_h + padding
    right = (column + 1) * cell_w - padding
    bottom = (row + 1) * cell_h - padding
    return left, top, right, bottom

def sector_vertices(column: int, row: int, columns: int = 3, rows: int = 3, padding: float = 0) -> list:
    \"\"\"Return rectangle vertices for a compositional sector. Useful for reserving, filling, or auditing regions.\"\"\"
    left, top, right, bottom = sector_bounds(column, row, columns, rows, padding)
    return [(left, top), (right, top), (right, bottom), (left, bottom)]

def contour_stack(
    points,
    offsets=None,
    colors=None,
    brushes=None,
    count_per_offset: int = 16,
    width_range=None,
    length_range=None,
    opacity_range=None,
    jitter: float = 5,
) -> list:
    \"\"\"Create repeated offset contour lines and short marks around any flowing edge, fold, current, ridge, fabric, smoke, or body plane.\"\"\"
    offsets = _choose(offsets, [-24, -12, 0, 12, 24])
    colors = _choose(colors, ["#dfe8df", "#8bbcc6", "#2f7897", "#0d2f4c"])
    brushes = _choose(brushes, ["ink", "dry_brush", "watercolor"])
    width_range = _choose(width_range, (1.2, 4.5))
    length_range = _choose(length_range, (12, 52))
    opacity_range = _choose(opacity_range, (0.16, 0.48))
    paths = []
    for offset in offsets:
        shifted = [(x, y + offset) for x, y in points]
        paths.append(polyline(
            *shifted,
            brush=random.choice(brushes),
            color=random.choice(colors),
            stroke_width=_rand_range(width_range, (1.2, 4.5)),
            opacity=_rand_range(opacity_range, (0.16, 0.48)),
        ))
        paths.extend(curve_marks(
            shifted,
            count=count_per_offset,
            colors=colors,
            brushes=brushes,
            width_range=width_range,
            length_range=length_range,
            opacity_range=opacity_range,
            jitter=jitter,
        ))
    return paths

def edge_fingers(
    points,
    count: int = 18,
    side: float = -1,
    colors=None,
    brushes=None,
    length_range=None,
    width_range=None,
    opacity_range=None,
) -> list:
    \"\"\"Create tapered organic projections from an edge: useful for foam, flame, leaves, hair, spray, torn cloth, or claw-like highlights.\"\"\"
    colors = _choose(colors, ["#fbf5e5", "#dfe8df", "#b8ccd1"])
    brushes = _choose(brushes, ["ink", "dry_brush", "oil_filbert"])
    length_range = _choose(length_range, (16, 70))
    width_range = _choose(width_range, (2, 9))
    opacity_range = _choose(opacity_range, (0.28, 0.78))
    paths = []
    if len(points) < 2:
        return paths
    for _ in range(count):
        index = random.randrange(0, len(points) - 1)
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        t = random.random()
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        dx = x2 - x1
        dy = y2 - y1
        length = max(1.0, math.hypot(dx, dy))
        nx = -dy / length * side
        ny = dx / length * side
        projection = _rand_range(length_range, (16, 70))
        width = _rand_range(width_range, (2, 9))
        tip_x = x + nx * projection + random.uniform(-width, width)
        tip_y = y + ny * projection + random.uniform(-width, width)
        cx1 = x + nx * projection * 0.35 + random.uniform(-width, width)
        cy1 = y + ny * projection * 0.35 + random.uniform(-width, width)
        cx2 = x + nx * projection * 0.72 + random.uniform(-width, width)
        cy2 = y + ny * projection * 0.72 + random.uniform(-width, width)
        paths.append(cubic(
            x,
            y,
            cx1,
            cy1,
            cx2,
            cy2,
            tip_x,
            tip_y,
            brush=random.choice(brushes),
            color=random.choice(colors),
            stroke_width=width,
            opacity=_rand_range(opacity_range, (0.28, 0.78)),
        ))
    return paths

def _smooth_closed_path(points) -> str:
    if not points:
        return "M 0 0 Z"
    if len(points) < 3:
        return " ".join(["M {{}} {{}}".format(points[0][0], points[0][1])] + [
            "L {{}} {{}}".format(x, y) for x, y in points[1:]
        ] + ["Z"])
    commands = ["M {{}} {{}}".format(points[0][0], points[0][1])]
    count = len(points)
    for index in range(count):
        p0 = points[(index - 1) % count]
        p1 = points[index]
        p2 = points[(index + 1) % count]
        p3 = points[(index + 2) % count]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        commands.append(
            "C {{}} {{}} {{}} {{}} {{}} {{}}".format(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])
        )
    commands.append("Z")
    return " ".join(commands)

def curved_ribbon_mass(
    center_points,
    widths,
    fill: str,
    fill_opacity: float = 0.92,
    stroke=None,
    stroke_width: float = 0,
    contour_color=None,
    contour_count: int = 0,
) -> list:
    \"\"\"Create a filled variable-width ribbon around a centerline for separate folded lips, overhangs, loops, smoke curls, fabric edges, limbs, branches, or bold graphic strokes.\"\"\"
    if len(center_points) < 2:
        return []
    widths = list(widths)
    if len(widths) < len(center_points):
        widths = widths + [widths[-1]] * (len(center_points) - len(widths))
    widths = widths[:len(center_points)]

    left = []
    right = []
    for index, (x, y) in enumerate(center_points):
        if index == 0:
            x2, y2 = center_points[1]
            dx = x2 - x
            dy = y2 - y
        elif index == len(center_points) - 1:
            x0, y0 = center_points[index - 1]
            dx = x - x0
            dy = y - y0
        else:
            x0, y0 = center_points[index - 1]
            x2, y2 = center_points[index + 1]
            dx = x2 - x0
            dy = y2 - y0
        length = max(1.0, math.hypot(dx, dy))
        nx = -dy / length
        ny = dx / length
        half = max(1.0, widths[index] / 2)
        left.append((x + nx * half, y + ny * half))
        right.append((x - nx * half, y - ny * half))

    vertices = left + list(reversed(right))
    d = _smooth_closed_path(vertices)
    paths = [
        filled_svg_path(
            d,
            fill,
            fill_opacity=fill_opacity,
            stroke=stroke,
            stroke_width=stroke_width,
        )
    ]
    if contour_count > 0:
        paths.extend(contour_stack(
            center_points,
            offsets=[-max(widths) * 0.22, 0, max(widths) * 0.22],
            colors=[contour_color or stroke or fill],
            count_per_offset=contour_count,
            width_range=(1.5, 4.5),
            length_range=(14, 48),
            opacity_range=(0.22, 0.55),
            jitter=4,
        ))
    return paths

def crescent_mass(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    fill: str,
    cutout_fill: str,
    curl: str = "right",
    fill_opacity: float = 0.92,
    cutout_opacity: float = 0.96,
    stroke=None,
    stroke_width: float = 0,
    cutout_stroke=None,
    cutout_stroke_width: float = 0,
) -> list:
    \"\"\"Create a generic curved mass with an explicit negative-space bite: useful for curls, moons, arches, smoke loops, cloud scrolls, or hollow forms.\"\"\"
    angle = 0.0
    if curl == "left":
        angle = math.pi
    elif curl == "up":
        angle = -math.pi / 2
    elif curl == "down":
        angle = math.pi / 2

    def transform(x, y):
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        return (
            cx + x * cos_a - y * sin_a,
            cy + x * sin_a + y * cos_a,
        )

    def cmd(kind, *coords):
        parts = [kind]
        for i in range(0, len(coords), 2):
            x, y = transform(coords[i] * rx, coords[i + 1] * ry)
            parts.append(str(round(x, 3)))
            parts.append(str(round(y, 3)))
        return " ".join(parts)

    outer = " ".join([
        cmd("M", -1.00, 0.48),
        cmd("C", -0.90, -0.62, 0.06, -1.14, 0.82, -0.48),
        cmd("C", 1.18, -0.16, 1.10, 0.48, 0.36, 0.78),
        cmd("C", -0.18, 0.98, -0.72, 0.78, -1.00, 0.48),
        "Z",
    ])
    inner = " ".join([
        cmd("M", -0.02, 0.22),
        cmd("C", 0.14, -0.44, 0.66, -0.46, 0.84, -0.02),
        cmd("C", 0.74, 0.48, 0.26, 0.66, -0.08, 0.38),
        cmd("C", -0.20, 0.30, -0.14, 0.24, -0.02, 0.22),
        "Z",
    ])
    return [
        filled_svg_path(outer, fill, fill_opacity=fill_opacity, stroke=stroke, stroke_width=stroke_width, opacity=0.92),
        filled_svg_path(inner, cutout_fill, fill_opacity=cutout_opacity, stroke=cutout_stroke, stroke_width=cutout_stroke_width, opacity=0.78),
    ]

def small_figure_silhouette(
    cx: float,
    cy: float,
    scale: float = 1,
    pose: str = "crouch",
    color: str = "#0b263e",
    ground: bool = False,
    ground_color: str = "#734534",
) -> list:
    \"\"\"Create a readable small human silhouette with head, torso, limbs, and optional grounding line.\"\"\"
    paths = []
    paths.append(ellipse_shape(cx, cy - 26 * scale, 8 * scale, 10 * scale, color, fill_opacity=0.95, stroke_width=0))
    if pose == "upright":
        paths.append(line(cx, cy - 16 * scale, cx, cy + 22 * scale, brush="ink", color=color, stroke_width=5 * scale, opacity=0.9))
        paths.append(line(cx - 18 * scale, cy - 2 * scale, cx + 18 * scale, cy - 4 * scale, brush="ink", color=color, stroke_width=3 * scale, opacity=0.82))
        paths.append(line(cx, cy + 20 * scale, cx - 14 * scale, cy + 42 * scale, brush="ink", color=color, stroke_width=4 * scale, opacity=0.88))
        paths.append(line(cx, cy + 20 * scale, cx + 14 * scale, cy + 42 * scale, brush="ink", color=color, stroke_width=4 * scale, opacity=0.88))
    else:
        paths.append(cubic(cx, cy - 16 * scale, cx - 12 * scale, cy + 2 * scale, cx - 16 * scale, cy + 20 * scale, cx - 28 * scale, cy + 36 * scale, brush="ink", color=color, stroke_width=5 * scale, opacity=0.9))
        paths.append(line(cx - 10 * scale, cy + 2 * scale, cx - 36 * scale, cy + 28 * scale, brush="ink", color=color, stroke_width=3.5 * scale, opacity=0.82))
        paths.append(line(cx - 20 * scale, cy + 26 * scale, cx + 20 * scale, cy + 38 * scale, brush="ink", color=color, stroke_width=4.5 * scale, opacity=0.86))
        paths.append(line(cx - 26 * scale, cy + 36 * scale, cx - 52 * scale, cy + 38 * scale, brush="ink", color=color, stroke_width=4 * scale, opacity=0.86))
    if ground:
        paths.append(line(cx - 52 * scale, cy + 42 * scale, cx + 54 * scale, cy + 39 * scale, brush="oil_flat", color=ground_color, stroke_width=7 * scale, opacity=0.78))
    return paths

def _rotated_rect_vertices(cx: float, cy: float, length: float, width: float, angle: float) -> list:
    tx = math.cos(angle)
    ty = math.sin(angle)
    nx = -ty
    ny = tx
    half_l = length / 2
    half_w = width / 2
    return [
        (cx - tx * half_l - nx * half_w, cy - ty * half_l - ny * half_w),
        (cx + tx * half_l - nx * half_w, cy + ty * half_l - ny * half_w),
        (cx + tx * half_l + nx * half_w, cy + ty * half_l + ny * half_w),
        (cx - tx * half_l + nx * half_w, cy - ty * half_l + ny * half_w),
    ]

def small_figure_with_prop(
    cx: float,
    cy: float,
    scale: float = 1,
    pose: str = "crouch",
    color: str = "#0b263e",
    prop_color: str = "#39405a",
    prop_length: float = 78,
    prop_width: float = 10,
    prop_angle: float = 0,
    ground: bool = False,
    ground_color: str = "#734534",
) -> list:
    \"\"\"Create a small readable figure attached to a broad prop: board, oar, tool, instrument, beam, handle, or vehicle element.\"\"\"
    paths = []
    paths.append(filled_polygon_path(
        _rotated_rect_vertices(cx + 2 * scale, cy + 34 * scale, prop_length * scale, prop_width * scale, prop_angle),
        prop_color,
        fill_opacity=0.90,
        stroke_width=0,
    ))
    paths.append(ellipse_shape(cx, cy - 30 * scale, 8.5 * scale, 10.5 * scale, color, fill_opacity=0.96, stroke_width=0))
    paths.append(ellipse_shape(cx - 4 * scale, cy - 9 * scale, 10 * scale, 18 * scale, color, fill_opacity=0.90, stroke_width=0))
    if pose == "upright":
        paths.append(line(cx - 5 * scale, cy + 8 * scale, cx - 16 * scale, cy + 34 * scale, brush="ink", color=color, stroke_width=5 * scale, opacity=0.88))
        paths.append(line(cx + 1 * scale, cy + 8 * scale, cx + 18 * scale, cy + 34 * scale, brush="ink", color=color, stroke_width=5 * scale, opacity=0.88))
        paths.append(line(cx - 10 * scale, cy - 8 * scale, cx - 28 * scale, cy + 8 * scale, brush="ink", color=color, stroke_width=4 * scale, opacity=0.82))
        paths.append(line(cx + 2 * scale, cy - 8 * scale, cx + 28 * scale, cy + 8 * scale, brush="ink", color=color, stroke_width=4 * scale, opacity=0.82))
    else:
        paths.append(line(cx - 4 * scale, cy + 2 * scale, cx - 28 * scale, cy + 30 * scale, brush="ink", color=color, stroke_width=5 * scale, opacity=0.88))
        paths.append(line(cx - 2 * scale, cy + 4 * scale, cx + 28 * scale, cy + 30 * scale, brush="ink", color=color, stroke_width=5 * scale, opacity=0.88))
        paths.append(line(cx - 10 * scale, cy - 12 * scale, cx - 34 * scale, cy + 12 * scale, brush="ink", color=color, stroke_width=4 * scale, opacity=0.82))
        paths.append(line(cx + 2 * scale, cy - 12 * scale, cx + 34 * scale, cy + 10 * scale, brush="ink", color=color, stroke_width=4 * scale, opacity=0.82))
    if ground:
        paths.append(line(cx - 50 * scale, cy + 42 * scale, cx + 58 * scale, cy + 39 * scale, brush="oil_flat", color=ground_color, stroke_width=7 * scale, opacity=0.70))
    return paths

def output_paths(paths: list):
    \"\"\"Output paths as JSON to stdout.\"\"\"
    print(json.dumps({{"paths": paths}}))

def output_svg_paths(svg_d_strings: list):
    \"\"\"Output SVG d-strings as JSON to stdout.\"\"\"
    print(json.dumps({{"svg_paths": svg_d_strings}}))

# User code below
{code}
"""

    # Write code to temp file and execute
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(full_code)
        temp_path = FilePath(f.name)

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(temp_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=PYTHON_TIMEOUT)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "stdout": "",
                "stderr": f"Code execution timed out after {PYTHON_TIMEOUT} seconds",
                "return_code": -1,
                "paths": [],
            }

        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")

        # Parse output for paths
        paths: list[Path] = []
        if proc.returncode == 0 and stdout_str.strip():
            try:
                # Find JSON in output (last line or full output)
                lines = stdout_str.strip().split("\n")
                json_str = None
                for line in reversed(lines):
                    line = line.strip()
                    if line.startswith("{"):
                        json_str = line
                        break

                if json_str:
                    output = json.loads(json_str)

                    # Handle paths array
                    if "paths" in output:
                        for path_data in output["paths"]:
                            parsed = parse_path_data(
                                path_data,
                                canvas_width=canvas_width,
                                canvas_height=canvas_height,
                            )
                            if parsed:
                                paths.append(parsed)

                    # Handle svg_paths array (d-strings)
                    if "svg_paths" in output:
                        for d_string in output["svg_paths"]:
                            if isinstance(d_string, str) and d_string.strip():
                                paths.append(Path(type=PathType.SVG, points=[], d=d_string))

            except json.JSONDecodeError as e:
                stderr_str += f"\nFailed to parse JSON output: {e}"

        return {
            "stdout": stdout_str,
            "stderr": stderr_str,
            "return_code": proc.returncode or 0,
            "paths": paths,
        }
    finally:
        temp_path.unlink(missing_ok=True)
