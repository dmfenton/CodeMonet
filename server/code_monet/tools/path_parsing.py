"""Path data parsing and validation."""

from __future__ import annotations

import math
from typing import Any

from code_monet.types import BRUSH_PRESETS, Path, PathType, Point, clamp_value


def _clamp_point(
    x: float,
    y: float,
    canvas_width: float,
    canvas_height: float,
) -> tuple[float, float]:
    return (
        clamp_value(x, 0.0, canvas_width),
        clamp_value(y, 0.0, canvas_height),
    )


def parse_path_data(
    path_data: dict[str, Any],
    canvas_width: float | None = None,
    canvas_height: float | None = None,
) -> Path | None:
    """Parse a path dictionary into a Path object.

    Supports optional style properties: brush, color, stroke_width, opacity, fill, fill_opacity.
    """
    try:
        path_type_str = path_data.get("type", "")
        points_data = path_data.get("points", [])

        # Validate path type
        try:
            path_type = PathType(path_type_str)
        except ValueError:
            return None

        # Extract optional style properties
        brush = path_data.get("brush")
        color = path_data.get("color")
        stroke_width = path_data.get("stroke_width")
        opacity = path_data.get("opacity")
        fill = path_data.get("fill")
        fill_opacity = path_data.get("fill_opacity")

        # Validate brush (must be a valid preset name or None)
        if brush is not None:
            if not isinstance(brush, str):
                brush = None
            elif brush not in BRUSH_PRESETS:
                brush = None  # Invalid brush name, ignore

        # Validate style properties
        if color is not None and not isinstance(color, str):
            color = None
        if fill is not None and not isinstance(fill, str):
            fill = None
        if stroke_width is not None:
            try:
                stroke_width = float(stroke_width)
                # Allow 0 for filled shapes with no outline; clamp positive widths.
                stroke_width = 0.0 if stroke_width <= 0 else max(0.5, min(30.0, stroke_width))
            except (TypeError, ValueError):
                stroke_width = None
        if opacity is not None:
            try:
                opacity = float(opacity)
                # Clamp to 0-1
                opacity = max(0.0, min(1.0, opacity))
            except (TypeError, ValueError):
                opacity = None
        if fill_opacity is not None:
            try:
                fill_opacity = float(fill_opacity)
                fill_opacity = max(0.0, min(1.0, fill_opacity))
            except (TypeError, ValueError):
                fill_opacity = None

        # Handle SVG path type (raw d-string)
        if path_type == PathType.SVG:
            d_string = path_data.get("d", "")
            if not d_string or not isinstance(d_string, str):
                return None
            # Brushes are ignored for SVG paths - drop to avoid confusion.
            brush = None
            return Path(
                type=PathType.SVG,
                points=[],
                d=d_string,
                brush=brush,
                color=color,
                stroke_width=stroke_width,
                opacity=opacity,
                fill=fill,
                fill_opacity=fill_opacity,
            )

        # Parse points for other path types
        points = []
        clamp_points = canvas_width is not None and canvas_height is not None
        max_x = float(canvas_width) if canvas_width is not None else 0.0
        max_y = float(canvas_height) if canvas_height is not None else 0.0
        for pt in points_data:
            if isinstance(pt, dict) and "x" in pt and "y" in pt:
                try:
                    x = float(pt["x"])
                    y = float(pt["y"])
                except (TypeError, ValueError):
                    return None
                if not math.isfinite(x) or not math.isfinite(y):
                    return None
                if clamp_points:
                    x, y = _clamp_point(x, y, max_x, max_y)
                points.append(Point(x=x, y=y))
            else:
                return None

        # Validate point count for path type
        min_points = {
            PathType.LINE: 2,
            PathType.QUADRATIC: 3,
            PathType.CUBIC: 4,
            PathType.POLYLINE: 2,
        }
        if len(points) < min_points.get(path_type, 2):
            return None

        return Path(
            type=path_type,
            points=points,
            brush=brush,
            color=color,
            stroke_width=stroke_width,
            opacity=opacity,
            fill=fill,
            fill_opacity=fill_opacity,
        )
    except (TypeError, ValueError):
        return None
