"""Tests for brush expansion logic."""

from code_monet.brushes import (
    _apply_edge_noise,
    _calculate_velocity_widths,
    _clamp_points,
    _clamp_stroke_width,
    _get_path_points,
    _offset_path,
    expand_brush_stroke,
    get_brush_descriptions,
    get_brush_names,
)
from code_monet.types import (
    BRUSH_PRESETS,
    Path,
    PathType,
    Point,
)


class TestGetBrushNames:
    """Tests for get_brush_names()."""

    def test_returns_all_preset_names(self):
        names = get_brush_names()
        assert len(names) == 12
        assert "oil_round" in names
        assert "watercolor" in names
        assert "palette_knife" in names

    def test_matches_brush_presets_keys(self):
        names = get_brush_names()
        assert set(names) == set(BRUSH_PRESETS.keys())


class TestGetBrushDescriptions:
    """Tests for get_brush_descriptions()."""

    def test_returns_formatted_string(self):
        desc = get_brush_descriptions()
        assert "Available brushes:" in desc
        assert "oil_round:" in desc
        assert "watercolor:" in desc


class TestExpandBrushStroke:
    """Tests for expand_brush_stroke()."""

    def test_returns_original_path_when_no_preset(self):
        """Path without brush preset should return unchanged."""
        path = Path(
            type=PathType.POLYLINE,
            points=[Point(x=0, y=0), Point(x=100, y=100)],
        )
        result = expand_brush_stroke(path, preset=None)
        assert len(result) == 1
        assert result[0] == path

    def test_expands_path_with_brush_preset(self):
        """Path with brush preset should expand to multiple paths."""
        path = Path(
            type=PathType.POLYLINE,
            points=[Point(x=0, y=0), Point(x=50, y=50), Point(x=100, y=100)],
            brush="oil_round",
        )
        preset = BRUSH_PRESETS["oil_round"]
        result = expand_brush_stroke(path, preset)

        # Should have main stroke + bristle strokes
        # oil_round has 5 bristles
        assert len(result) == 1 + preset.bristle_count

    def test_no_bristles_for_zero_count(self):
        """Brush with no bristles should return just main stroke."""
        path = Path(
            type=PathType.POLYLINE,
            points=[Point(x=0, y=0), Point(x=50, y=50), Point(x=100, y=100)],
            brush="pencil",
        )
        preset = BRUSH_PRESETS["pencil"]
        assert preset.bristle_count == 0

        result = expand_brush_stroke(path, preset)
        assert len(result) == 1

    def test_preserves_color(self):
        """Expanded paths should preserve the original color."""
        path = Path(
            type=PathType.POLYLINE,
            points=[Point(x=0, y=0), Point(x=100, y=100)],
            brush="oil_round",
            color="#ff0000",
        )
        result = expand_brush_stroke(path)
        for p in result:
            assert p.color == "#ff0000"

    def test_preserves_author(self):
        """Expanded paths should preserve the original author."""
        path = Path(
            type=PathType.POLYLINE,
            points=[Point(x=0, y=0), Point(x=100, y=100)],
            brush="oil_round",
            author="human",
        )
        result = expand_brush_stroke(path)
        for p in result:
            assert p.author == "human"

    def test_single_point_path_unchanged(self):
        """Path with single point should return unchanged."""
        path = Path(
            type=PathType.POLYLINE,
            points=[Point(x=50, y=50)],
            brush="oil_round",
        )
        result = expand_brush_stroke(path)
        assert len(result) == 1
        assert result[0] == path

    def test_empty_path_unchanged(self):
        """Path with no points should return unchanged."""
        path = Path(
            type=PathType.POLYLINE,
            points=[],
            brush="oil_round",
        )
        result = expand_brush_stroke(path)
        assert len(result) == 1

    def test_svg_path_unchanged(self):
        """SVG paths (d-string) should return unchanged - no points to expand."""
        path = Path(
            type=PathType.SVG,
            points=[],
            d="M 0 0 L 100 100",
            brush="oil_round",
        )
        result = expand_brush_stroke(path)
        assert len(result) == 1
        assert result[0] == path

    def test_main_stroke_has_brush_preset(self):
        """Main stroke should retain brush preset for client-side rendering."""
        path = Path(
            type=PathType.POLYLINE,
            points=[Point(x=0, y=0), Point(x=100, y=100)],
            brush="watercolor",
        )
        result = expand_brush_stroke(path)
        assert result[0].brush == "watercolor"


class TestCalculateVelocityWidths:
    """Tests for _calculate_velocity_widths()."""

    def test_single_point_returns_base_width(self):
        """Single point should return base width."""
        points = [Point(x=0, y=0)]
        widths = _calculate_velocity_widths(points, base_width=10.0, pressure_response=0.5)
        assert widths == [10.0]

    def test_two_points_returns_two_widths(self):
        """Two points should return two widths."""
        points = [Point(x=0, y=0), Point(x=100, y=0)]
        widths = _calculate_velocity_widths(points, base_width=10.0, pressure_response=0.5)
        assert len(widths) == 2

    def test_zero_pressure_response_constant_width(self):
        """Zero pressure response should give constant widths."""
        points = [
            Point(x=0, y=0),
            Point(x=10, y=0),
            Point(x=100, y=0),  # Different distances
        ]
        widths = _calculate_velocity_widths(points, base_width=10.0, pressure_response=0.0)
        assert all(w == 10.0 for w in widths)

    def test_velocity_affects_width(self):
        """Faster movement should produce thinner strokes."""
        points = [
            Point(x=0, y=0),
            Point(x=10, y=0),  # Short distance (slow)
            Point(x=110, y=0),  # Long distance (fast)
        ]
        widths = _calculate_velocity_widths(points, base_width=10.0, pressure_response=1.0)
        # Width after slow segment should be thicker than after fast segment
        assert widths[1] > widths[2]


class TestApplyEdgeNoise:
    """Tests for _apply_edge_noise()."""

    def test_zero_noise_unchanged(self):
        """Zero noise amount should return identical points."""
        points = [Point(x=0, y=0), Point(x=100, y=100)]
        result = _apply_edge_noise(points, noise_amount=0.0, stroke_width=10.0)
        assert result[0].x == 0
        assert result[0].y == 0
        assert result[1].x == 100
        assert result[1].y == 100

    def test_noise_displaces_points(self):
        """Non-zero noise should displace points (though randomly)."""
        points = [Point(x=50, y=50), Point(x=100, y=100), Point(x=150, y=150)]
        # Run multiple times to verify randomness
        all_same = True
        for _ in range(10):
            result = _apply_edge_noise(points, noise_amount=0.5, stroke_width=10.0)
            if result[1].x != 100 or result[1].y != 100:
                all_same = False
                break
        # Interior points should be displaced at least sometimes
        assert not all_same

    def test_endpoints_less_displaced(self):
        """Start and end points should have reduced displacement factor."""
        # This is more of a sanity check - the actual edge_factor is 0.3 for endpoints
        points = [Point(x=0, y=0), Point(x=50, y=50), Point(x=100, y=100)]
        result = _apply_edge_noise(points, noise_amount=1.0, stroke_width=100.0)
        # Points should be returned (even if displaced)
        assert len(result) == 3


class TestOffsetPath:
    """Tests for _offset_path()."""

    def test_zero_offset_unchanged(self):
        """Zero offset should return identical points."""
        points = [Point(x=0, y=0), Point(x=100, y=0)]
        result = _offset_path(points, offset=0.0)
        assert result[0].x == 0
        assert result[0].y == 0
        assert result[1].x == 100
        assert result[1].y == 0

    def test_horizontal_line_vertical_offset(self):
        """Horizontal line offset should move points vertically."""
        points = [Point(x=0, y=50), Point(x=100, y=50)]
        result = _offset_path(points, offset=10.0)
        # Perpendicular to horizontal is vertical
        assert result[0].y != 50 or result[1].y != 50
        # X coordinates should be unchanged
        assert result[0].x == 0
        assert result[1].x == 100

    def test_vertical_line_horizontal_offset(self):
        """Vertical line offset should move points horizontally."""
        points = [Point(x=50, y=0), Point(x=50, y=100)]
        result = _offset_path(points, offset=10.0)
        # Perpendicular to vertical is horizontal
        assert result[0].x != 50 or result[1].x != 50
        # Y coordinates should be unchanged
        assert result[0].y == 0
        assert result[1].y == 100

    def test_single_point_unchanged(self):
        """Single point cannot be offset (no direction)."""
        points = [Point(x=50, y=50)]
        result = _offset_path(points, offset=10.0)
        assert result == points


class TestGetPathPoints:
    """Tests for _get_path_points()."""

    def test_returns_points_from_polyline(self):
        """Should return points from a polyline path."""
        path = Path(
            type=PathType.POLYLINE,
            points=[Point(x=0, y=0), Point(x=100, y=100)],
        )
        result = _get_path_points(path)
        assert len(result) == 2

    def test_returns_empty_for_svg_path(self):
        """Should return empty list for SVG paths (no points array)."""
        path = Path(
            type=PathType.SVG,
            points=[],
            d="M 0 0 L 100 100",
        )
        result = _get_path_points(path)
        assert result == []

    def test_returns_empty_for_empty_points(self):
        """Should return empty list if path has no points."""
        path = Path(type=PathType.POLYLINE, points=[])
        result = _get_path_points(path)
        assert result == []


class TestBrushPresetValues:
    """Tests for brush preset definitions."""

    def test_all_presets_have_required_fields(self):
        """All presets should have required BrushPreset fields."""
        for name, preset in BRUSH_PRESETS.items():
            assert preset.name == name
            assert preset.display_name
            assert preset.description
            assert 0 <= preset.bristle_count <= 50
            assert 0 <= preset.main_opacity <= 1
            assert preset.base_width > 0

    def test_oil_round_has_bristles(self):
        """Oil round should have subtle bristles."""
        preset = BRUSH_PRESETS["oil_round"]
        assert preset.bristle_count == 3
        assert preset.bristle_opacity < 0.2

    def test_pencil_has_no_bristles(self):
        """Pencil should have no bristles."""
        preset = BRUSH_PRESETS["pencil"]
        assert preset.bristle_count == 0

    def test_watercolor_is_translucent(self):
        """Watercolor should have low opacity."""
        preset = BRUSH_PRESETS["watercolor"]
        assert preset.main_opacity < 0.5

    def test_palette_knife_is_opaque(self):
        """Palette knife should have high opacity."""
        preset = BRUSH_PRESETS["palette_knife"]
        assert preset.main_opacity > 0.9


class TestClampStrokeWidth:
    """Tests for _clamp_stroke_width()."""

    def test_clamps_below_minimum(self):
        """Values below 0.5 should clamp to 0.5."""
        assert _clamp_stroke_width(0.1) == 0.5
        assert _clamp_stroke_width(0.0) == 0.5
        assert _clamp_stroke_width(-5.0) == 0.5

    def test_clamps_above_maximum(self):
        """Values above 30 should clamp to 30."""
        assert _clamp_stroke_width(50.0) == 30.0
        assert _clamp_stroke_width(100.0) == 30.0

    def test_preserves_valid_width(self):
        """Values in range should be unchanged."""
        assert _clamp_stroke_width(0.5) == 0.5
        assert _clamp_stroke_width(15.0) == 15.0
        assert _clamp_stroke_width(30.0) == 30.0


class TestClampPoints:
    """Tests for _clamp_points()."""

    def test_clamps_negative_coordinates(self):
        """Negative coordinates should clamp to 0."""
        points = [Point(x=-10, y=-5)]
        result = _clamp_points(points, 800, 600)
        assert result[0].x == 0.0
        assert result[0].y == 0.0

    def test_clamps_overflow_coordinates(self):
        """Coordinates beyond canvas should clamp to max."""
        points = [Point(x=850, y=650)]
        result = _clamp_points(points, 800, 600)
        assert result[0].x == 800.0
        assert result[0].y == 600.0

    def test_preserves_valid_coordinates(self):
        """Coordinates within bounds should be unchanged."""
        points = [Point(x=400, y=300)]
        result = _clamp_points(points, 800, 600)
        assert result[0].x == 400.0
        assert result[0].y == 300.0

    def test_no_clamp_when_dimensions_none(self):
        """No clamping when canvas dimensions are None."""
        points = [Point(x=850, y=650)]
        result = _clamp_points(points, None, None)
        assert result[0].x == 850
        assert result[0].y == 650

    def test_no_clamp_when_width_none(self):
        """No clamping when only width is None."""
        points = [Point(x=850, y=650)]
        result = _clamp_points(points, None, 600)
        assert result[0].x == 850
        assert result[0].y == 650

    def test_returns_same_list_when_no_changes(self):
        """Should return original list if no clamping needed."""
        points = [Point(x=100, y=100), Point(x=200, y=200)]
        result = _clamp_points(points, 800, 600)
        assert result is points

    def test_returns_new_list_when_clamped(self):
        """Should return new list if any point was clamped."""
        points = [Point(x=100, y=100), Point(x=900, y=200)]
        result = _clamp_points(points, 800, 600)
        assert result is not points
        assert result[1].x == 800.0

    def test_empty_list(self):
        """Empty list should return unchanged."""
        points: list[Point] = []
        result = _clamp_points(points, 800, 600)
        assert result == []
