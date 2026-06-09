"""Tests for path parsing and validation."""

from code_monet.tools.path_parsing import parse_path_data
from code_monet.types import PathType


class TestParsePathData:
    """Tests for parse_path_data()."""

    def test_parses_valid_polyline(self):
        """Should parse a valid polyline path."""
        data = {
            "type": "polyline",
            "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}],
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.type == PathType.POLYLINE
        assert len(result.points) == 2

    def test_parses_svg_path(self):
        """Should parse an SVG path with d-string."""
        data = {
            "type": "svg",
            "d": "M 0 0 L 100 100",
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.type == PathType.SVG
        assert result.d == "M 0 0 L 100 100"

    def test_rejects_invalid_path_type(self):
        """Should return None for invalid path type."""
        data = {
            "type": "invalid",
            "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}],
        }
        result = parse_path_data(data)
        assert result is None

    def test_rejects_insufficient_points(self):
        """Should return None when too few points for path type."""
        data = {
            "type": "line",
            "points": [{"x": 0, "y": 0}],  # Line needs 2 points
        }
        result = parse_path_data(data)
        assert result is None

    def test_parses_style_properties(self):
        """Should parse optional style properties."""
        data = {
            "type": "polyline",
            "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}],
            "color": "#ff0000",
            "stroke_width": 5.0,
            "opacity": 0.8,
            "fill": "#00ff00",
            "fill_opacity": 0.35,
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.color == "#ff0000"
        assert result.stroke_width == 5.0
        assert result.opacity == 0.8
        assert result.fill == "#00ff00"
        assert result.fill_opacity == 0.35


class TestPointClamping:
    """Tests for point clamping with canvas dimensions."""

    def test_clamps_negative_coordinates(self):
        """Negative coordinates should clamp to 0."""
        data = {
            "type": "polyline",
            "points": [{"x": -10, "y": -5}, {"x": 100, "y": 100}],
        }
        result = parse_path_data(data, canvas_width=800, canvas_height=600)
        assert result is not None
        assert result.points[0].x == 0.0
        assert result.points[0].y == 0.0

    def test_clamps_overflow_coordinates(self):
        """Coordinates beyond canvas should clamp to max."""
        data = {
            "type": "polyline",
            "points": [{"x": 850, "y": 650}, {"x": 100, "y": 100}],
        }
        result = parse_path_data(data, canvas_width=800, canvas_height=600)
        assert result is not None
        assert result.points[0].x == 800.0
        assert result.points[0].y == 600.0

    def test_no_clamp_without_dimensions(self):
        """No clamping when canvas dimensions not provided."""
        data = {
            "type": "polyline",
            "points": [{"x": 850, "y": 650}, {"x": 100, "y": 100}],
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.points[0].x == 850.0
        assert result.points[0].y == 650.0


class TestNaNInfValidation:
    """Tests for NaN/Infinity rejection."""

    def test_rejects_nan_x(self):
        """Should reject points with NaN x coordinate."""
        data = {
            "type": "polyline",
            "points": [{"x": float("nan"), "y": 0}, {"x": 100, "y": 100}],
        }
        result = parse_path_data(data)
        assert result is None

    def test_rejects_nan_y(self):
        """Should reject points with NaN y coordinate."""
        data = {
            "type": "polyline",
            "points": [{"x": 0, "y": float("nan")}, {"x": 100, "y": 100}],
        }
        result = parse_path_data(data)
        assert result is None

    def test_rejects_inf_x(self):
        """Should reject points with infinite x coordinate."""
        data = {
            "type": "polyline",
            "points": [{"x": float("inf"), "y": 0}, {"x": 100, "y": 100}],
        }
        result = parse_path_data(data)
        assert result is None

    def test_rejects_negative_inf_y(self):
        """Should reject points with negative infinite y coordinate."""
        data = {
            "type": "polyline",
            "points": [{"x": 0, "y": float("-inf")}, {"x": 100, "y": 100}],
        }
        result = parse_path_data(data)
        assert result is None


class TestStrokeWidthClamping:
    """Tests for stroke width clamping."""

    def test_clamps_stroke_width_below_minimum(self):
        """Stroke width below 0.5 should clamp to 0.5."""
        data = {
            "type": "polyline",
            "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}],
            "stroke_width": 0.1,
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.stroke_width == 0.5

    def test_clamps_stroke_width_above_maximum(self):
        """Stroke width above 30 should clamp to 30."""
        data = {
            "type": "polyline",
            "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}],
            "stroke_width": 50.0,
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.stroke_width == 30.0

    def test_allows_zero_stroke_width_for_filled_shapes(self):
        """Stroke width 0 should be preserved for fill-only shapes."""
        data = {
            "type": "svg",
            "d": "M 0 0 L 100 0 L 100 100 Z",
            "fill": "#f7ead0",
            "stroke_width": 0,
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.stroke_width == 0.0
        assert result.fill == "#f7ead0"


class TestBrushHandling:
    """Tests for brush parameter handling."""

    def test_svg_paths_drop_brush(self):
        """SVG paths should have brush set to None."""
        data = {
            "type": "svg",
            "d": "M 0 0 L 100 100",
            "brush": "oil_round",
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.brush is None

    def test_valid_brush_preserved(self):
        """Valid brush names should be preserved."""
        data = {
            "type": "polyline",
            "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}],
            "brush": "oil_round",
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.brush == "oil_round"

    def test_invalid_brush_dropped(self):
        """Invalid brush names should be dropped."""
        data = {
            "type": "polyline",
            "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}],
            "brush": "not_a_real_brush",
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.brush is None
