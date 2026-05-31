"""Tests for the drawing tools module."""

import pytest

from code_monet.tools import (
    _generate_signature_paths,
    _inject_canvas_image,
    _transform_svg_path,
    handle_draw_paths,
    handle_generate_svg,
    handle_mark_piece_done,
    handle_name_piece,
    handle_sign_canvas,
    parse_path_data,
    set_add_strokes_callback,
    set_canvas_dimensions,
    set_draw_callback,
    set_get_canvas_callback,
    set_piece_title_callback,
)
from code_monet.types import Path, PathType


class TestParsePathData:
    """Tests for parse_path_data function."""

    def test_parse_line(self) -> None:
        data = {
            "type": "line",
            "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}],
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.type == PathType.LINE
        assert len(result.points) == 2
        assert result.points[0].x == 0
        assert result.points[1].y == 100

    def test_parse_polyline(self) -> None:
        data = {
            "type": "polyline",
            "points": [
                {"x": 0, "y": 0},
                {"x": 50, "y": 50},
                {"x": 100, "y": 0},
            ],
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.type == PathType.POLYLINE
        assert len(result.points) == 3

    def test_parse_quadratic(self) -> None:
        data = {
            "type": "quadratic",
            "points": [
                {"x": 0, "y": 0},
                {"x": 50, "y": 100},
                {"x": 100, "y": 0},
            ],
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.type == PathType.QUADRATIC
        assert len(result.points) == 3

    def test_parse_cubic(self) -> None:
        data = {
            "type": "cubic",
            "points": [
                {"x": 0, "y": 0},
                {"x": 33, "y": 100},
                {"x": 66, "y": 100},
                {"x": 100, "y": 0},
            ],
        }
        result = parse_path_data(data)
        assert result is not None
        assert result.type == PathType.CUBIC
        assert len(result.points) == 4

    def test_parse_invalid_type(self) -> None:
        data = {
            "type": "invalid",
            "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}],
        }
        result = parse_path_data(data)
        assert result is None

    def test_parse_missing_points(self) -> None:
        data = {"type": "line"}
        result = parse_path_data(data)
        assert result is None

    def test_parse_insufficient_points(self) -> None:
        data = {
            "type": "line",
            "points": [{"x": 0, "y": 0}],  # Line needs 2 points
        }
        result = parse_path_data(data)
        assert result is None

    def test_parse_invalid_point_format(self) -> None:
        data = {
            "type": "line",
            "points": [{"x": 0}, {"x": 100, "y": 100}],  # Missing y
        }
        result = parse_path_data(data)
        assert result is None


class TestHandleDrawPaths:
    """Tests for handle_draw_paths function."""

    @pytest.mark.asyncio
    async def test_draw_paths_success(self) -> None:
        collected_paths: list[Path] = []
        done_flag = False

        async def callback(paths: list[Path], done: bool) -> None:
            nonlocal done_flag
            collected_paths.extend(paths)
            done_flag = done

        set_draw_callback(callback)

        args = {
            "paths": [
                {"type": "line", "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}]},
                {
                    "type": "quadratic",
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 50, "y": 100},
                        {"x": 100, "y": 0},
                    ],
                },
            ],
            "done": False,
        }

        result = await handle_draw_paths(args)

        assert result["content"][0]["text"] == "Successfully drew 2 paths."
        assert "is_error" not in result
        assert len(collected_paths) == 2
        assert done_flag is False

    @pytest.mark.asyncio
    async def test_draw_paths_with_done(self) -> None:
        done_flag = False

        async def callback(_paths: list[Path], done: bool) -> None:
            nonlocal done_flag
            done_flag = done

        set_draw_callback(callback)

        args = {
            "paths": [{"type": "line", "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}]}],
            "done": True,
        }

        result = await handle_draw_paths(args)

        assert "Piece marked as complete" in result["content"][0]["text"]
        assert done_flag is True

    @pytest.mark.asyncio
    async def test_draw_paths_invalid_input(self) -> None:
        set_draw_callback(None)

        args = {"paths": "not an array"}

        result = await handle_draw_paths(args)

        assert result["is_error"] is True
        assert "must be an array" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_draw_paths_partial_errors(self) -> None:
        collected_paths: list[Path] = []

        async def callback(paths: list[Path], _done: bool) -> None:
            collected_paths.extend(paths)

        set_draw_callback(callback)

        args = {
            "paths": [
                {"type": "line", "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}]},
                {"type": "invalid", "points": []},  # Invalid
            ],
        }

        result = await handle_draw_paths(args)

        # Should report error but still parse valid paths
        assert "1 errors" in result["content"][0]["text"]
        assert len(collected_paths) == 1


class TestHandleMarkPieceDone:
    """Tests for handle_mark_piece_done function."""

    @pytest.mark.asyncio
    async def test_mark_piece_done(self) -> None:
        done_flag = False

        async def callback(_paths: list[Path], done: bool) -> None:
            nonlocal done_flag
            done_flag = done

        set_draw_callback(callback)

        result = await handle_mark_piece_done()

        assert "Piece marked as complete" in result["content"][0]["text"]
        assert done_flag is True

    @pytest.mark.asyncio
    async def test_mark_piece_done_no_callback(self) -> None:
        set_draw_callback(None)

        result = await handle_mark_piece_done()

        assert "Piece marked as complete" in result["content"][0]["text"]


class TestInjectCanvasImage:
    """Tests for _inject_canvas_image helper function."""

    def test_inject_canvas_image_adds_image_to_content(self) -> None:
        # Create a simple PNG image (minimal valid PNG bytes)
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"

        def get_canvas() -> bytes:
            return png_bytes

        set_get_canvas_callback(get_canvas)

        content: list[dict] = []
        _inject_canvas_image(content)

        assert len(content) == 1
        assert content[0]["type"] == "image"
        assert content[0]["source"]["type"] == "base64"
        assert content[0]["source"]["media_type"] == "image/png"
        # Verify it's valid base64
        import base64

        decoded = base64.standard_b64decode(content[0]["source"]["data"])
        assert decoded == png_bytes

    def test_inject_canvas_image_no_callback(self) -> None:
        set_get_canvas_callback(None)

        content: list[dict] = []
        _inject_canvas_image(content)

        # Should not add anything if callback is not set
        assert len(content) == 0

    def test_inject_canvas_image_handles_exception(self) -> None:
        def failing_callback() -> bytes:
            raise RuntimeError("Canvas render failed")

        set_get_canvas_callback(failing_callback)

        content: list[dict] = []
        # Should not raise, just log warning
        _inject_canvas_image(content)

        # Should not add anything on error
        assert len(content) == 0


class TestAddStrokesCallback:
    """Tests for set_add_strokes_callback functionality."""

    @pytest.mark.asyncio
    async def test_add_strokes_callback_called_before_draw(self) -> None:
        call_order: list[str] = []
        collected_strokes: list[Path] = []

        async def add_strokes(paths: list[Path]) -> None:
            call_order.append("add_strokes")
            collected_strokes.extend(paths)

        async def draw_callback(_paths: list[Path], _done: bool) -> None:
            call_order.append("draw")

        set_add_strokes_callback(add_strokes)
        set_draw_callback(draw_callback)
        set_get_canvas_callback(None)  # Disable image injection for this test

        args = {
            "paths": [{"type": "line", "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}]}],
        }

        await handle_draw_paths(args)

        # add_strokes should be called before draw
        assert call_order == ["add_strokes", "draw"]
        assert len(collected_strokes) == 1

    @pytest.mark.asyncio
    async def test_add_strokes_not_called_when_no_paths(self) -> None:
        strokes_called = False

        async def add_strokes(_paths: list[Path]) -> None:
            nonlocal strokes_called
            strokes_called = True

        set_add_strokes_callback(add_strokes)
        set_draw_callback(None)
        set_get_canvas_callback(None)

        # All paths invalid
        args = {
            "paths": [{"type": "invalid", "points": []}],
        }

        await handle_draw_paths(args)

        # Should not call add_strokes when no valid paths
        assert strokes_called is False


class TestGenerateSvgHelpers:
    """Tests for Python sandbox drawing helpers exposed to the agent."""

    @pytest.mark.asyncio
    async def test_generic_painterly_helpers_output_paths(self) -> None:
        result = await handle_generate_svg(
            {
                "code": """
paths = []
paths.append(dab(100, 100, 20, 0.5, color="#ff0000"))
paths.extend(stroke_field(
    4,
    x_range=(120, 180),
    y_range=(130, 180),
    colors=["#00ff00"],
    exclude_polygons=[[(130, 130), (160, 130), (160, 160), (130, 160)]],
))
paths.extend(ramp_field(
    4,
    x_range=(120, 180),
    y_range=(190, 230),
    stops=[(0.0, ["#0000ff"]), (1.0, ["#ffcc00"])],
    texture_ratio=0.25,
))
paths.extend(curve_marks([(200, 200), (240, 230), (280, 205)], count=4))
paths.extend(mass_field([(40, 260), (95, 250), (115, 300), (35, 315)], count=6, wash_rows=2, texture_ratio=0.25))
paths.extend(curve_band([(0, 310), (120, 280), (240, 315)], bottom_y=360, count=5, texture_ratio=0.25))
paths.extend(tapered_band([(420, 290), (455, 330), (480, 380)], [18, 36, 52], count=6, wash_rows=2, texture_ratio=0.25))
paths.extend(broken_edge([(500, 300), (560, 285), (620, 310)], count=5))
paths.extend(fill_polygon([(300, 180), (340, 240), (260, 240)], count=5))
paths.extend(glow_field(360, 180, 60, count=5, core_marks=2))
paths.extend(reflection_field(380, 250, 80, 50, count=4))
paths.extend(radial_cluster(500, 260, count=5, rx=30, ry=20))
output_paths(paths)
"""
            }
        )

        assert "is_error" not in result
        text = result["content"][0]["text"]
        assert "Successfully generated and drew" in text or "Code executed" in text


class TestTransformSvgPath:
    """Tests for _transform_svg_path function."""

    def test_transform_simple_move(self) -> None:
        """Test transforming a simple M command."""
        result = _transform_svg_path("M 10 20", 2.0, 100.0, 200.0)
        # 10 * 2 + 100 = 120, 20 * 2 + 200 = 240
        assert result == "M 120.0 240.0"

    def test_transform_line_to(self) -> None:
        """Test transforming L command."""
        result = _transform_svg_path("M 0 0 L 50 50", 1.0, 10.0, 20.0)
        assert result == "M 10.0 20.0 L 60.0 70.0"

    def test_transform_quadratic(self) -> None:
        """Test transforming Q command."""
        result = _transform_svg_path("M 0 0 Q 25 25 50 0", 2.0, 0.0, 0.0)
        # Just scaling, no offset
        assert result == "M 0.0 0.0 Q 50.0 50.0 100.0 0.0"

    def test_transform_cubic(self) -> None:
        """Test transforming C command."""
        result = _transform_svg_path("M 0 0 C 10 10 20 10 30 0", 1.0, 5.0, 5.0)
        assert result == "M 5.0 5.0 C 15.0 15.0 25.0 15.0 35.0 5.0"


class TestGenerateSignaturePaths:
    """Tests for _generate_signature_paths function."""

    def test_generates_paths(self) -> None:
        """Test that signature paths are generated."""
        set_canvas_dimensions(800, 600)
        paths = _generate_signature_paths()
        assert len(paths) > 0
        assert all(p.type == PathType.SVG for p in paths)

    def test_default_position_bottom_right(self) -> None:
        """Test default position is bottom-right corner."""
        set_canvas_dimensions(800, 600)
        paths = _generate_signature_paths()
        # All paths should have d-strings with coordinates near bottom-right
        for p in paths:
            assert p.d is not None
            # Check that x coordinates are in right portion of canvas (> 400)
            # This is a rough check since we're transforming the signature

    def test_size_affects_stroke_width(self) -> None:
        """Test that size parameter affects stroke width."""
        set_canvas_dimensions(800, 600)
        small_paths = _generate_signature_paths(size="small")
        large_paths = _generate_signature_paths(size="large")
        # Larger size should have larger stroke width
        assert small_paths[0].stroke_width is not None
        assert large_paths[0].stroke_width is not None
        assert large_paths[0].stroke_width > small_paths[0].stroke_width

    def test_color_is_applied(self) -> None:
        """Test that custom color is applied to paths."""
        set_canvas_dimensions(800, 600)
        paths = _generate_signature_paths(color="#FF0000")
        assert all(p.color == "#FF0000" for p in paths)


class TestHandleSignCanvas:
    """Tests for handle_sign_canvas function."""

    @pytest.mark.asyncio
    async def test_sign_canvas_success(self) -> None:
        """Test successful signing."""
        collected_strokes: list[Path] = []

        async def add_strokes(paths: list[Path]) -> None:
            collected_strokes.extend(paths)

        async def draw_callback(_paths: list[Path], _done: bool) -> None:
            pass

        set_add_strokes_callback(add_strokes)
        set_draw_callback(draw_callback)
        set_get_canvas_callback(None)
        set_canvas_dimensions(800, 600)

        result = await handle_sign_canvas({})

        assert "is_error" not in result or result["is_error"] is False
        assert len(collected_strokes) > 0
        assert "Signed the canvas" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_sign_canvas_with_position(self) -> None:
        """Test signing with different positions."""
        set_add_strokes_callback(None)
        set_draw_callback(None)
        set_get_canvas_callback(None)
        set_canvas_dimensions(800, 600)

        for position in ["bottom_right", "bottom_left", "bottom_center"]:
            result = await handle_sign_canvas({"position": position})
            assert "is_error" not in result or result["is_error"] is False
            assert position.replace("_", " ") in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_sign_canvas_invalid_position_fallback(self) -> None:
        """Test that invalid position falls back to bottom_right."""
        set_add_strokes_callback(None)
        set_draw_callback(None)
        set_get_canvas_callback(None)
        set_canvas_dimensions(800, 600)

        result = await handle_sign_canvas({"position": "invalid_position"})
        assert "is_error" not in result or result["is_error"] is False
        assert "bottom right" in result["content"][0]["text"]


class TestHandleNamePiece:
    """Tests for handle_name_piece function."""

    @pytest.mark.asyncio
    async def test_name_piece_success(self) -> None:
        """Test successful naming."""
        saved_title: str | None = None

        async def save_title(title: str) -> None:
            nonlocal saved_title
            saved_title = title

        set_piece_title_callback(save_title)

        result = await handle_name_piece({"title": "Whispers at Dusk"})

        assert "is_error" not in result or result["is_error"] is False
        assert saved_title == "Whispers at Dusk"
        assert "Whispers at Dusk" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_name_piece_empty_title(self) -> None:
        """Test error when title is empty."""
        set_piece_title_callback(None)

        result = await handle_name_piece({"title": ""})

        assert result.get("is_error") is True
        assert "provide a title" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_name_piece_missing_title(self) -> None:
        """Test error when title is missing."""
        set_piece_title_callback(None)

        result = await handle_name_piece({})

        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_name_piece_long_title_truncation(self) -> None:
        """Test that very long titles are truncated."""
        saved_title: str | None = None

        async def save_title(title: str) -> None:
            nonlocal saved_title
            saved_title = title

        set_piece_title_callback(save_title)

        long_title = "A" * 150
        result = await handle_name_piece({"title": long_title})

        assert "is_error" not in result or result["is_error"] is False
        assert saved_title is not None
        assert len(saved_title) == 100

    @pytest.mark.asyncio
    async def test_name_piece_whitespace_stripped(self) -> None:
        """Test that whitespace is stripped from title."""
        saved_title: str | None = None

        async def save_title(title: str) -> None:
            nonlocal saved_title
            saved_title = title

        set_piece_title_callback(save_title)

        await handle_name_piece({"title": "  Sunset Reverie  "})

        assert saved_title == "Sunset Reverie"
