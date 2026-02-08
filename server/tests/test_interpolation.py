"""Tests for path interpolation."""

import pytest

from code_monet.interpolation import (
    cubic_bezier,
    dedupe_close_points,
    estimate_path_length,
    interpolate_path,
    interpolate_polyline_adaptive,
    lerp,
    lerp_point,
    quadratic_bezier,
)
from code_monet.types import Path, PathType, Point


class TestLerp:
    def test_lerp_start(self) -> None:
        assert lerp(0, 100, 0) == 0

    def test_lerp_end(self) -> None:
        assert lerp(0, 100, 1) == 100

    def test_lerp_middle(self) -> None:
        assert lerp(0, 100, 0.5) == 50

    def test_lerp_point(self) -> None:
        p1 = Point(x=0, y=0)
        p2 = Point(x=100, y=100)
        result = lerp_point(p1, p2, 0.5)
        assert result.x == 50
        assert result.y == 50


class TestBezier:
    def test_quadratic_bezier_start(self) -> None:
        p0 = Point(x=0, y=0)
        p1 = Point(x=50, y=100)
        p2 = Point(x=100, y=0)
        result = quadratic_bezier(p0, p1, p2, 0)
        assert result.x == pytest.approx(0)
        assert result.y == pytest.approx(0)

    def test_quadratic_bezier_end(self) -> None:
        p0 = Point(x=0, y=0)
        p1 = Point(x=50, y=100)
        p2 = Point(x=100, y=0)
        result = quadratic_bezier(p0, p1, p2, 1)
        assert result.x == pytest.approx(100)
        assert result.y == pytest.approx(0)

    def test_cubic_bezier_start(self) -> None:
        p0 = Point(x=0, y=0)
        p1 = Point(x=33, y=100)
        p2 = Point(x=66, y=100)
        p3 = Point(x=100, y=0)
        result = cubic_bezier(p0, p1, p2, p3, 0)
        assert result.x == pytest.approx(0)
        assert result.y == pytest.approx(0)

    def test_cubic_bezier_end(self) -> None:
        p0 = Point(x=0, y=0)
        p1 = Point(x=33, y=100)
        p2 = Point(x=66, y=100)
        p3 = Point(x=100, y=0)
        result = cubic_bezier(p0, p1, p2, p3, 1)
        assert result.x == pytest.approx(100)
        assert result.y == pytest.approx(0)


class TestPathLength:
    def test_line_length(self) -> None:
        path = Path(
            type=PathType.LINE,
            points=[Point(x=0, y=0), Point(x=100, y=0)],
        )
        assert estimate_path_length(path) == pytest.approx(100)

    def test_polyline_length(self) -> None:
        path = Path(
            type=PathType.POLYLINE,
            points=[
                Point(x=0, y=0),
                Point(x=100, y=0),
                Point(x=100, y=100),
            ],
        )
        assert estimate_path_length(path) == pytest.approx(200)

    def test_empty_path(self) -> None:
        path = Path(type=PathType.LINE, points=[])
        assert estimate_path_length(path) == 0


class TestInterpolatePath:
    def test_interpolate_line(self) -> None:
        path = Path(
            type=PathType.LINE,
            points=[Point(x=0, y=0), Point(x=100, y=0)],
        )
        result = interpolate_path(path, steps_per_unit=0.1)
        assert len(result) >= 2
        assert result[0].x == pytest.approx(0)
        assert result[-1].x == pytest.approx(100)

    def test_interpolate_preserves_endpoints(self) -> None:
        path = Path(
            type=PathType.QUADRATIC,
            points=[
                Point(x=0, y=0),
                Point(x=50, y=100),
                Point(x=100, y=0),
            ],
        )
        result = interpolate_path(path)
        assert result[0].x == pytest.approx(0)
        assert result[0].y == pytest.approx(0)
        assert result[-1].x == pytest.approx(100)
        assert result[-1].y == pytest.approx(0)


class TestDedupeClosePoints:
    def test_empty_list(self) -> None:
        result = dedupe_close_points([])
        assert result == []

    def test_single_point(self) -> None:
        points = [Point(x=0, y=0)]
        result = dedupe_close_points(points)
        assert len(result) == 1

    def test_two_points_always_kept(self) -> None:
        points = [Point(x=0, y=0), Point(x=0.5, y=0.5)]
        result = dedupe_close_points(points, min_distance=10)
        assert len(result) == 2

    def test_removes_close_points(self) -> None:
        # Points less than 1.5 apart should be removed (except first/last)
        points = [
            Point(x=0, y=0),
            Point(x=0.5, y=0),  # too close, should be removed
            Point(x=1.0, y=0),  # too close, should be removed
            Point(x=10, y=0),  # far enough, should be kept
            Point(x=10.5, y=0),  # too close, should be removed
            Point(x=20, y=0),  # last point, always kept
        ]
        result = dedupe_close_points(points, min_distance=1.5)
        # Should keep: first (0,0), (10,0), last (20,0)
        assert len(result) == 3
        assert result[0].x == 0
        assert result[1].x == 10
        assert result[2].x == 20

    def test_preserves_first_and_last(self) -> None:
        # First and last should always be preserved even if close
        points = [
            Point(x=0, y=0),
            Point(x=50, y=0),
            Point(x=50.1, y=0),  # very close to last, but last is preserved
        ]
        result = dedupe_close_points(points, min_distance=1.5)
        assert result[0].x == 0
        assert result[-1].x == 50.1

    def test_custom_min_distance(self) -> None:
        points = [
            Point(x=0, y=0),
            Point(x=5, y=0),
            Point(x=10, y=0),
        ]
        # With min_distance=3, (5,0) should be kept
        result = dedupe_close_points(points, min_distance=3)
        assert len(result) == 3

        # With min_distance=6, (5,0) should be removed
        result = dedupe_close_points(points, min_distance=6)
        assert len(result) == 2


class TestInterpolatePolylineAdaptive:
    """Tests for curvature-adaptive polyline interpolation."""

    def test_zigzag_produces_more_points_than_straight(self) -> None:
        """Zigzag path has higher curvature, should produce more points."""
        # Straight line: total length ~300
        straight = [
            Point(x=0, y=0),
            Point(x=100, y=0),
            Point(x=200, y=0),
            Point(x=300, y=0),
        ]
        # Zigzag: same total length but high curvature at each vertex
        zigzag = [
            Point(x=0, y=0),
            Point(x=100, y=50),
            Point(x=200, y=0),
            Point(x=300, y=50),
        ]

        straight_points = interpolate_polyline_adaptive(straight, 0.2)
        zigzag_points = interpolate_polyline_adaptive(zigzag, 0.2)

        assert len(zigzag_points) > len(straight_points)

    def test_preserves_first_and_last_points(self) -> None:
        """Output should include first and last input points."""
        points = [
            Point(x=10, y=20),
            Point(x=50, y=80),
            Point(x=100, y=30),
        ]
        result = interpolate_polyline_adaptive(points, 0.2)

        assert len(result) >= 3
        assert result[0].x == pytest.approx(10)
        assert result[0].y == pytest.approx(20)
        assert result[-1].x == pytest.approx(100)
        assert result[-1].y == pytest.approx(30)

    def test_single_point_returns_as_is(self) -> None:
        """Single point input returns single point."""
        points = [Point(x=5, y=5)]
        result = interpolate_polyline_adaptive(points, 0.2)
        assert len(result) == 1

    def test_two_points_returns_interpolated(self) -> None:
        """Two points should interpolate the segment."""
        points = [Point(x=0, y=0), Point(x=100, y=0)]
        result = interpolate_polyline_adaptive(points, 0.2)
        assert len(result) >= 2
        assert result[0].x == pytest.approx(0)
        assert result[-1].x == pytest.approx(100)

    def test_dedup_works_after_adaptive_interpolation(self) -> None:
        """Adaptive interpolation output should work with dedupe."""
        points = [
            Point(x=0, y=0),
            Point(x=50, y=50),
            Point(x=100, y=0),
        ]
        result = interpolate_polyline_adaptive(points, 0.2)
        deduped = dedupe_close_points(result, min_distance=1.5)
        # Should still have first and last
        assert deduped[0].x == pytest.approx(0)
        assert deduped[-1].x == pytest.approx(100)

    def test_interpolate_path_uses_adaptive_for_polyline(self) -> None:
        """interpolate_path should use adaptive interpolation for polylines."""
        # Zigzag polyline
        path = Path(
            type=PathType.POLYLINE,
            points=[
                Point(x=0, y=0),
                Point(x=100, y=50),
                Point(x=200, y=0),
                Point(x=300, y=50),
            ],
        )
        result = interpolate_path(path, steps_per_unit=0.2)
        assert len(result) >= 4
        assert result[0].x == pytest.approx(0)
        assert result[-1].x == pytest.approx(300)
