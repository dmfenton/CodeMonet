"""Pure functions for path interpolation.

This module contains stateless, pure mathematical functions for
interpolating paths into discrete points. No side effects or I/O.
"""

import contextlib
import math
import re
from collections.abc import Callable

from code_monet.types import Path, PathType, Point

# SVG path command regex
SVG_COMMAND_RE = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|(-?[\d.]+)")


def parse_svg_path(d: str) -> list[tuple[str, list[float]]]:
    """Parse SVG path d-string into commands with arguments.

    Returns list of (command, [args]) tuples.
    """
    commands: list[tuple[str, list[float]]] = []
    current_cmd = ""
    current_args: list[float] = []

    for match in SVG_COMMAND_RE.finditer(d):
        token = match.group()
        if token.isalpha():
            # New command
            if current_cmd:
                commands.append((current_cmd, current_args))
            current_cmd = token
            current_args = []
        else:
            # Number argument
            with contextlib.suppress(ValueError):
                current_args.append(float(token))

    # Don't forget the last command
    if current_cmd:
        commands.append((current_cmd, current_args))

    return commands


def svg_commands_to_points(
    commands: list[tuple[str, list[float]]], steps_per_unit: float = 0.5
) -> list[Point]:
    """Convert SVG path commands to interpolated points.

    This handles the common SVG path commands and interpolates curves.
    Returns a flat list of points suitable for drawing.
    """
    points: list[Point] = []
    current_x, current_y = 0.0, 0.0
    start_x, start_y = 0.0, 0.0  # For Z command
    last_control_x, last_control_y = 0.0, 0.0  # For smooth curves

    for cmd, args in commands:
        is_relative = cmd.islower()
        cmd_upper = cmd.upper()

        if cmd_upper == "M":  # MoveTo
            i = 0
            while i < len(args) - 1:
                x, y = args[i], args[i + 1]
                if is_relative:
                    x += current_x
                    y += current_y
                current_x, current_y = x, y
                if i == 0:
                    start_x, start_y = x, y
                points.append(Point(x=x, y=y))
                i += 2

        elif cmd_upper == "L":  # LineTo
            i = 0
            while i < len(args) - 1:
                x, y = args[i], args[i + 1]
                if is_relative:
                    x += current_x
                    y += current_y
                # Interpolate line segment
                dist = math.sqrt((x - current_x) ** 2 + (y - current_y) ** 2)
                steps = max(2, int(dist * steps_per_unit))
                for j in range(1, steps + 1):
                    t = j / steps
                    px = current_x + (x - current_x) * t
                    py = current_y + (y - current_y) * t
                    points.append(Point(x=px, y=py))
                current_x, current_y = x, y
                i += 2

        elif cmd_upper == "H":  # Horizontal LineTo
            for x in args:
                if is_relative:
                    x += current_x
                dist = abs(x - current_x)
                steps = max(2, int(dist * steps_per_unit))
                for j in range(1, steps + 1):
                    t = j / steps
                    px = current_x + (x - current_x) * t
                    points.append(Point(x=px, y=current_y))
                current_x = x

        elif cmd_upper == "V":  # Vertical LineTo
            for y in args:
                if is_relative:
                    y += current_y
                dist = abs(y - current_y)
                steps = max(2, int(dist * steps_per_unit))
                for j in range(1, steps + 1):
                    t = j / steps
                    py = current_y + (y - current_y) * t
                    points.append(Point(x=current_x, y=py))
                current_y = y

        elif cmd_upper == "C":  # Cubic Bezier
            i = 0
            while i < len(args) - 5:
                x1, y1, x2, y2, x, y = args[i : i + 6]
                if is_relative:
                    x1 += current_x
                    y1 += current_y
                    x2 += current_x
                    y2 += current_y
                    x += current_x
                    y += current_y
                # Interpolate cubic bezier
                p0 = Point(x=current_x, y=current_y)
                p1 = Point(x=x1, y=y1)
                p2 = Point(x=x2, y=y2)
                p3 = Point(x=x, y=y)
                dist = distance(p0, p1) + distance(p1, p2) + distance(p2, p3)  # Rough estimate
                steps = max(10, int(dist * steps_per_unit))
                for j in range(1, steps + 1):
                    t = j / steps
                    pt = cubic_bezier(p0, p1, p2, p3, t)
                    points.append(pt)
                current_x, current_y = x, y
                last_control_x, last_control_y = x2, y2
                i += 6

        elif cmd_upper == "S":  # Smooth Cubic Bezier
            i = 0
            while i < len(args) - 3:
                x2, y2, x, y = args[i : i + 4]
                if is_relative:
                    x2 += current_x
                    y2 += current_y
                    x += current_x
                    y += current_y
                # First control point is reflection of last
                x1 = 2 * current_x - last_control_x
                y1 = 2 * current_y - last_control_y
                p0 = Point(x=current_x, y=current_y)
                p1 = Point(x=x1, y=y1)
                p2 = Point(x=x2, y=y2)
                p3 = Point(x=x, y=y)
                dist = distance(p0, p1) + distance(p1, p2) + distance(p2, p3)
                steps = max(10, int(dist * steps_per_unit))
                for j in range(1, steps + 1):
                    t = j / steps
                    pt = cubic_bezier(p0, p1, p2, p3, t)
                    points.append(pt)
                current_x, current_y = x, y
                last_control_x, last_control_y = x2, y2
                i += 4

        elif cmd_upper == "Q":  # Quadratic Bezier
            i = 0
            while i < len(args) - 3:
                x1, y1, x, y = args[i : i + 4]
                if is_relative:
                    x1 += current_x
                    y1 += current_y
                    x += current_x
                    y += current_y
                p0 = Point(x=current_x, y=current_y)
                p1 = Point(x=x1, y=y1)
                p2 = Point(x=x, y=y)
                dist = distance(p0, p1) + distance(p1, p2)
                steps = max(10, int(dist * steps_per_unit))
                for j in range(1, steps + 1):
                    t = j / steps
                    pt = quadratic_bezier(p0, p1, p2, t)
                    points.append(pt)
                current_x, current_y = x, y
                last_control_x, last_control_y = x1, y1
                i += 4

        elif cmd_upper == "T":  # Smooth Quadratic Bezier
            i = 0
            while i < len(args) - 1:
                x, y = args[i], args[i + 1]
                if is_relative:
                    x += current_x
                    y += current_y
                x1 = 2 * current_x - last_control_x
                y1 = 2 * current_y - last_control_y
                p0 = Point(x=current_x, y=current_y)
                p1 = Point(x=x1, y=y1)
                p2 = Point(x=x, y=y)
                dist = distance(p0, p1) + distance(p1, p2)
                steps = max(10, int(dist * steps_per_unit))
                for j in range(1, steps + 1):
                    t = j / steps
                    pt = quadratic_bezier(p0, p1, p2, t)
                    points.append(pt)
                current_x, current_y = x, y
                last_control_x, last_control_y = x1, y1
                i += 2

        elif cmd_upper == "Z":  # Close Path
            if start_x != current_x or start_y != current_y:
                dist = math.sqrt((start_x - current_x) ** 2 + (start_y - current_y) ** 2)
                steps = max(2, int(dist * steps_per_unit))
                for j in range(1, steps + 1):
                    t = j / steps
                    px = current_x + (start_x - current_x) * t
                    py = current_y + (start_y - current_y) * t
                    points.append(Point(x=px, y=py))
            current_x, current_y = start_x, start_y

        # Note: Arc (A/a) command is complex and not implemented here

    return points


def interpolate_svg_path(d: str, steps_per_unit: float = 0.5) -> list[Point]:
    """Interpolate an SVG path d-string into discrete points."""
    commands = parse_svg_path(d)
    return svg_commands_to_points(commands, steps_per_unit)


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between two values."""
    return a + (b - a) * t


def lerp_point(p1: Point, p2: Point, t: float) -> Point:
    """Linearly interpolate between two points."""
    return Point(x=lerp(p1.x, p2.x, t), y=lerp(p1.y, p2.y, t))


def distance(p1: Point, p2: Point) -> float:
    """Calculate Euclidean distance between two points."""
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    return math.sqrt(dx * dx + dy * dy)


def dedupe_close_points(points: list[Point], min_distance: float = 1.5) -> list[Point]:
    """Remove points that are closer than min_distance pixels apart.

    Always keeps first and last points for proper stroke endpoints.
    This reduces unnecessary animation frames for sub-pixel movements.
    """
    if len(points) <= 2:
        return points

    result = [points[0]]
    for point in points[1:-1]:
        if distance(result[-1], point) >= min_distance:
            result.append(point)
    # Always keep the last point
    result.append(points[-1])
    return result


def quadratic_bezier(p0: Point, p1: Point, p2: Point, t: float) -> Point:
    """Evaluate quadratic bezier at t."""
    one_minus_t = 1 - t
    return Point(
        x=one_minus_t**2 * p0.x + 2 * one_minus_t * t * p1.x + t**2 * p2.x,
        y=one_minus_t**2 * p0.y + 2 * one_minus_t * t * p1.y + t**2 * p2.y,
    )


def cubic_bezier(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    """Evaluate cubic bezier at t."""
    one_minus_t = 1 - t
    return Point(
        x=(
            one_minus_t**3 * p0.x
            + 3 * one_minus_t**2 * t * p1.x
            + 3 * one_minus_t * t**2 * p2.x
            + t**3 * p3.x
        ),
        y=(
            one_minus_t**3 * p0.y
            + 3 * one_minus_t**2 * t * p1.y
            + 3 * one_minus_t * t**2 * p2.y
            + t**3 * p3.y
        ),
    )


def estimate_path_length(path: Path) -> float:
    """Estimate the length of a path for timing calculations."""
    # Handle SVG paths specially - they may have no points array
    if path.type == PathType.SVG:
        if not path.d:
            return 0.0
        # Estimate by interpolating and measuring
        points = interpolate_svg_path(path.d, steps_per_unit=0.1)
        if len(points) < 2:
            return 0.0
        return sum(distance(points[i], points[i + 1]) for i in range(len(points) - 1))

    if len(path.points) < 2:
        return 0.0

    points = path.points

    match path.type:
        case PathType.LINE:
            return distance(points[0], points[1])

        case PathType.POLYLINE:
            return sum(distance(points[i], points[i + 1]) for i in range(len(points) - 1))

        case PathType.QUADRATIC | PathType.CUBIC:
            # Approximate with linear segments
            steps = 20
            total = 0.0
            prev = points[0]
            for i in range(1, steps + 1):
                t = i / steps
                if path.type == PathType.QUADRATIC and len(points) >= 3:
                    curr = quadratic_bezier(points[0], points[1], points[2], t)
                elif path.type == PathType.CUBIC and len(points) >= 4:
                    curr = cubic_bezier(points[0], points[1], points[2], points[3], t)
                else:
                    break
                total += distance(prev, curr)
                prev = curr
            return total

        case _:
            return 0.0


# Type alias for interpolation strategy
Interpolator = Callable[[list[Point], int], list[Point]]


def interpolate_line(points: list[Point], num_steps: int) -> list[Point]:
    """Interpolate a line into discrete points."""
    if len(points) < 2:
        return list(points)
    return [lerp_point(points[0], points[1], i / num_steps) for i in range(num_steps + 1)]


def interpolate_polyline_adaptive(
    points: list[Point], base_steps_per_unit: float = 0.2
) -> list[Point]:
    """Interpolate a polyline with curvature-adaptive point density.

    Higher curvature segments get more points (slower animation),
    straight segments get fewer points (faster animation).

    Args:
        points: Polyline vertices.
        base_steps_per_unit: Base density. Adapted per-segment based on curvature.
    """
    if len(points) < 2:
        return list(points)

    min_spu = 0.05
    max_spu = 0.5

    result: list[Point] = [points[0]]

    for seg_idx in range(len(points) - 1):
        p1 = points[seg_idx]
        p2 = points[seg_idx + 1]
        seg_length = distance(p1, p2)

        # Calculate angle change from previous segment for curvature estimate
        if seg_idx > 0:
            p0 = points[seg_idx - 1]
            # Vectors for previous and current segments
            dx_prev = p1.x - p0.x
            dy_prev = p1.y - p0.y
            dx_curr = p2.x - p1.x
            dy_curr = p2.y - p1.y
            len_prev = math.sqrt(dx_prev * dx_prev + dy_prev * dy_prev)
            len_curr = math.sqrt(dx_curr * dx_curr + dy_curr * dy_curr)

            if len_prev > 0.01 and len_curr > 0.01:
                # Dot product for angle
                dot = (dx_prev * dx_curr + dy_prev * dy_curr) / (len_prev * len_curr)
                dot = max(-1.0, min(1.0, dot))
                angle = math.acos(dot)  # 0 = straight, pi = U-turn
                # Scale: more curvature → higher density
                curvature_factor = 1.0 + (angle / math.pi) * 2.0
            else:
                curvature_factor = 1.0
        else:
            curvature_factor = 1.0

        local_spu = max(min_spu, min(max_spu, base_steps_per_unit * curvature_factor))
        seg_steps = max(1, int(seg_length * local_spu))

        for j in range(1, seg_steps + 1):
            t = j / seg_steps
            result.append(lerp_point(p1, p2, t))

    return result


def interpolate_quadratic(points: list[Point], num_steps: int) -> list[Point]:
    """Interpolate a quadratic bezier into discrete points."""
    if len(points) < 3:
        return list(points)
    return [
        quadratic_bezier(points[0], points[1], points[2], i / num_steps)
        for i in range(num_steps + 1)
    ]


def interpolate_cubic(points: list[Point], num_steps: int) -> list[Point]:
    """Interpolate a cubic bezier into discrete points."""
    if len(points) < 4:
        return list(points)
    return [
        cubic_bezier(points[0], points[1], points[2], points[3], i / num_steps)
        for i in range(num_steps + 1)
    ]


def interpolate_path(
    path: Path, steps_per_unit: float = 0.2, dedupe_min_distance: float = 1.5
) -> list[Point]:
    """Interpolate a path into discrete points for drawing.

    This is a pure function - no side effects or external dependencies.

    Args:
        path: The path to interpolate.
        steps_per_unit: Points per pixel of path length. Lower = fewer points = faster animation.
        dedupe_min_distance: Minimum distance between points. Removes sub-pixel movements.
    """
    # Handle SVG paths specially
    if path.type == PathType.SVG:
        if not path.d:
            return []
        points = interpolate_svg_path(path.d, steps_per_unit)
        return dedupe_close_points(points, dedupe_min_distance)

    if len(path.points) < 2:
        return list(path.points)

    points = path.points
    length = estimate_path_length(path)
    num_steps = max(2, int(length * steps_per_unit))

    result: list[Point]
    match path.type:
        case PathType.LINE:
            result = interpolate_line(points, num_steps)

        case PathType.POLYLINE:
            result = interpolate_polyline_adaptive(points, steps_per_unit)

        case PathType.QUADRATIC:
            result = interpolate_quadratic(points, num_steps)

        case PathType.CUBIC:
            result = interpolate_cubic(points, num_steps)

        case _:
            result = list(points)

    # Remove sub-pixel movements to reduce unnecessary animation frames
    return dedupe_close_points(result, dedupe_min_distance)
