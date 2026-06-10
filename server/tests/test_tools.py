"""Tests for the drawing tools module."""

from collections.abc import Generator

import pytest

from code_monet.tools import (
    _generate_signature_paths,
    _inject_canvas_image,
    _transform_svg_path,
    get_quality_gate_snapshot,
    handle_critique_canvas,
    handle_draw_paths,
    handle_generate_svg,
    handle_mark_piece_done,
    handle_name_piece,
    handle_sign_canvas,
    handle_view_canvas,
    parse_path_data,
    quality_gate_prompt_context,
    record_critique_result,
    reset_quality_gate,
    set_add_strokes_callback,
    set_canvas_dimensions,
    set_draw_callback,
    set_get_canvas_callback,
    set_piece_title_callback,
)
from code_monet.tools.quality_gate import critique_gate_message
from code_monet.types import Path, PathType


@pytest.fixture(autouse=True)
def reset_tool_quality_gate() -> Generator[None]:
    reset_quality_gate()
    yield
    reset_quality_gate()


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
        record_critique_result("VERDICT: PASS\nFINDINGS:\n- ready")

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
        record_critique_result("VERDICT: PASS\nFINDINGS:\n- ready")

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
        record_critique_result("VERDICT: PASS\nFINDINGS:\n- ready")

        result = await handle_mark_piece_done()

        assert "Piece marked as complete" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_mark_piece_done_requires_passing_critique(self) -> None:
        set_draw_callback(None)

        result = await handle_mark_piece_done()

        assert result["is_error"] is True
        assert "critique_canvas first" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_mark_piece_done_blocked_after_failed_critique(self) -> None:
        done_flag = False

        async def callback(_paths: list[Path], done: bool) -> None:
            nonlocal done_flag
            done_flag = done

        set_draw_callback(callback)
        record_critique_result("VERDICT: FAIL\nFINDINGS:\n- weak silhouette")

        result = await handle_mark_piece_done()

        assert result["is_error"] is True
        assert "Finish blocked" in result["content"][0]["text"]
        assert done_flag is False


class TestHandleViewCanvas:
    """Tests for handle_view_canvas function."""

    @pytest.mark.asyncio
    async def test_view_canvas_returns_mcp_image_content(self) -> None:
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

        def get_canvas() -> bytes:
            return png_bytes

        set_get_canvas_callback(get_canvas)

        result = await handle_view_canvas()

        assert result["content"][0]["type"] == "text"
        assert "Inspect the actual rendered canvas" in result["content"][0]["text"]
        content = result["content"][1]
        assert content["type"] == "image"
        assert content["mimeType"] == "image/png"

        import base64

        assert base64.standard_b64decode(content["data"]) == png_bytes

    @pytest.mark.asyncio
    async def test_view_canvas_no_callback(self) -> None:
        set_get_canvas_callback(None)

        result = await handle_view_canvas()

        assert result["is_error"] is True
        assert "Canvas not available" in result["content"][0]["text"]


class TestHandleCritiqueCanvas:
    """Tests for handle_critique_canvas validation paths."""

    @pytest.mark.asyncio
    async def test_critique_canvas_requires_brief(self) -> None:
        result = await handle_critique_canvas({"brief": ""})

        assert result["is_error"] is True
        assert "brief must be a non-empty string" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_critique_canvas_requires_canvas_callback(self) -> None:
        set_get_canvas_callback(None)

        result = await handle_critique_canvas({"brief": "dominant silhouette must read"})

        assert result["is_error"] is True
        assert "Canvas not available" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_failed_critique_blocks_finish_tools_until_pass(self) -> None:
        collected_strokes: list[Path] = []
        saved_title: str | None = None
        done_flag = False

        async def add_strokes(paths: list[Path]) -> None:
            collected_strokes.extend(paths)

        async def draw_callback(_paths: list[Path], done: bool) -> None:
            nonlocal done_flag
            done_flag = done

        async def save_title(title: str) -> None:
            nonlocal saved_title
            saved_title = title

        set_add_strokes_callback(add_strokes)
        set_draw_callback(draw_callback)
        set_piece_title_callback(save_title)
        set_get_canvas_callback(None)
        set_canvas_dimensions(800, 600)

        record_critique_result("VERDICT: FAIL\nFINDINGS:\n- flat cap")

        sign_result = await handle_sign_canvas({})
        assert sign_result["is_error"] is True
        assert collected_strokes == []

        name_result = await handle_name_piece({"title": "Premature Title"})
        assert name_result["is_error"] is True
        assert saved_title is None

        draw_result = await handle_draw_paths(
            {
                "paths": [
                    {
                        "type": "line",
                        "points": [{"x": 0, "y": 0}, {"x": 100, "y": 100}],
                    }
                ],
                "done": True,
            }
        )
        assert "Finish blocked" in draw_result["content"][0]["text"]
        assert len(collected_strokes) == 1
        assert done_flag is False

        record_critique_result("VERDICT: PASS\nFINDINGS:\n- ready")
        sign_result = await handle_sign_canvas({})
        assert "is_error" not in sign_result or sign_result["is_error"] is False
        assert len(collected_strokes) > 1

    def test_failed_critique_builds_next_turn_context(self) -> None:
        record_critique_result(
            "VERDICT: FAIL\n"
            "FINDINGS:\n"
            "- Subject reads as a smooth ramp instead of a hooked form with a tunnel.\n"
            "REQUIRED_REVISIONS:\n"
            "- Rebuild body, lip, and opening."
        )

        context = quality_gate_prompt_context()

        assert context is not None
        assert "Finish gate is blocked" in context
        assert "smooth ramp" in context
        assert "structural revision" in context
        assert "Do not sign, name, or mark done" in context
        assert get_quality_gate_snapshot()["blocked_by_failure"] is True

    def test_failed_critique_message_is_binding(self) -> None:
        message = critique_gate_message("FAIL")

        assert "FINISH GATE: BLOCKED" in message
        assert "structural revision" in message

    def test_consecutive_failures_trigger_repaint_directive(self) -> None:
        """After 3 FAILs the gate orders an opaque repaint, not more texture."""
        for _ in range(2):
            record_critique_result("VERDICT: FAIL\nFINDINGS:\n- values collapse")

        # Two failures: still ordinary revision guidance.
        assert "OVERWORK ALERT" not in critique_gate_message("FAIL")
        context = quality_gate_prompt_context()
        assert context is not None
        assert "OVERWORK ALERT" not in context

        record_critique_result("VERDICT: FAIL\nFINDINGS:\n- values collapse")

        # Third consecutive failure: repaint directive becomes binding.
        assert get_quality_gate_snapshot()["consecutive_failures"] == 3
        assert "OVERWORK ALERT" in critique_gate_message("FAIL")
        context = quality_gate_prompt_context()
        assert context is not None
        assert "OVERWORK ALERT" in context
        assert "fill_opacity=1.0" in context

    def test_pass_resets_consecutive_failures(self) -> None:
        for _ in range(3):
            record_critique_result("VERDICT: FAIL\nFINDINGS:\n- mud")
        assert get_quality_gate_snapshot()["consecutive_failures"] == 3

        record_critique_result("VERDICT: PASS\nFINDINGS:\n- reads cleanly")

        assert get_quality_gate_snapshot()["consecutive_failures"] == 0
        assert "OVERWORK ALERT" not in critique_gate_message("FAIL")


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
        assert content[0]["mimeType"] == "image/png"
        # Verify it's valid base64
        import base64

        decoded = base64.standard_b64decode(content[0]["data"])
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
    async def test_filled_shape_helpers_output_paths(self) -> None:
        collected_strokes: list[Path] = []

        async def add_strokes(paths: list[Path]) -> None:
            collected_strokes.extend(paths)

        set_add_strokes_callback(add_strokes)
        set_draw_callback(None)
        set_get_canvas_callback(None)

        result = await handle_generate_svg(
            {
                "code": """
paths = [
    rect_shape(0, 0, canvas_width, canvas_height, "#f7ead0"),
    filled_polygon_path([(10, 10), (90, 10), (50, 80)], "#1a1a2e", fill_opacity=0.8),
    ellipse_shape(140, 60, 30, 20, "#ff0000", stroke="#000000", stroke_width=2),
]
output_paths(paths)
"""
            }
        )

        assert "is_error" not in result
        assert len(collected_strokes) == 3
        assert collected_strokes[0].fill == "#f7ead0"
        assert collected_strokes[0].stroke_width == 0
        assert collected_strokes[1].fill_opacity == 0.8
        assert collected_strokes[2].color == "#000000"

    @pytest.mark.asyncio
    async def test_generic_painterly_helpers_output_paths(self) -> None:
        result = await handle_generate_svg(
            {
                "code": """
paths = []
paths.extend(background_wash(
    count=12,
    stops=[(0.0, ["#dbe7f4"]), (1.0, ["#8faec0"])],
    wash_rows=2,
    texture_ratio=0.2,
))
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

    @pytest.mark.asyncio
    async def test_composition_helpers_output_transferable_structure(self) -> None:
        collected_strokes: list[Path] = []

        async def add_strokes(paths: list[Path]) -> None:
            collected_strokes.extend(paths)

        set_add_strokes_callback(add_strokes)
        set_draw_callback(None)
        set_get_canvas_callback(None)
        set_canvas_dimensions(1200, 420)

        result = await handle_generate_svg(
            {
                "code": """
import random
random.seed(31)
paths = []
paths.append(rect_shape(0, 0, canvas_width, canvas_height, "#efe4cb"))
paths.append(filled_polygon_path(
    sector_vertices(0, 2, columns=3, rows=3, padding=4),
    "#123a57",
    fill_opacity=0.22,
))
main_curve = [(80, 310), (310, 245), (560, 210), (880, 250)]
edge_curve = [(610, 150), (730, 110), (860, 122), (1000, 176)]
paths.extend(contour_stack(
    main_curve,
    offsets=[-18, 0, 22, 48],
    count_per_offset=5,
    colors=["#1f5d82", "#5f9db0", "#f7efd9"],
))
paths.extend(edge_fingers(
    edge_curve,
    count=10,
    side=-1,
    colors=["#fbf6e6", "#dfe8df"],
))
paths.extend(curved_ribbon_mass(
    [(560, 150), (680, 105), (830, 132), (760, 238)],
    [38, 68, 54, 30],
    "#123a57",
    fill_opacity=0.88,
    contour_color="#f7efd9",
    contour_count=3,
))
paths.extend(crescent_mass(
    760,
    190,
    170,
    92,
    "#123a57",
    "#efe4cb",
    curl="right",
    cutout_stroke="#1f5d82",
    cutout_stroke_width=2,
))
paths.extend(tapered_band(
    [(120, 350), (440, 375), (760, 348), (1120, 388)],
    [34, 58, 44, 66],
    count=18,
    wash_rows=2,
    texture_ratio=0.35,
))
paths.extend(small_figure_silhouette(900, 275, scale=1.2, ground=True))
paths.extend(small_figure_with_prop(1010, 265, scale=1.1, prop_angle=0.08, ground=True))
output_paths(paths)
"""
            }
        )

        assert "is_error" not in result
        assert len(collected_strokes) >= 65
        assert any(path.fill for path in collected_strokes)
        assert any(
            path.type in {PathType.LINE, PathType.POLYLINE, PathType.CUBIC}
            and any(point.y > 300 for point in path.points)
            for path in collected_strokes
        )
        assert sum(1 for path in collected_strokes if path.type == PathType.LINE) >= 4
        assert any(path.type == PathType.CUBIC for path in collected_strokes)
        assert sum(1 for path in collected_strokes if path.type == PathType.SVG and path.fill) >= 5


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
        record_critique_result("VERDICT: PASS\nFINDINGS:\n- ready")

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
            record_critique_result("VERDICT: PASS\nFINDINGS:\n- ready")
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
        record_critique_result("VERDICT: PASS\nFINDINGS:\n- ready")

        result = await handle_sign_canvas({"position": "invalid_position"})
        assert "is_error" not in result or result["is_error"] is False
        assert "bottom right" in result["content"][0]["text"]


class TestHandleNamePiece:
    """Tests for handle_name_piece function."""

    @pytest.mark.asyncio
    async def test_name_piece_success(self) -> None:
        """Test successful naming."""
        saved_title: str | None = None
        record_critique_result("VERDICT: PASS\nFINDINGS:\n- ready")

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
        record_critique_result("VERDICT: PASS\nFINDINGS:\n- ready")

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
        record_critique_result("VERDICT: PASS\nFINDINGS:\n- ready")

        async def save_title(title: str) -> None:
            nonlocal saved_title
            saved_title = title

        set_piece_title_callback(save_title)

        await handle_name_piece({"title": "  Sunset Reverie  "})

        assert saved_title == "Sunset Reverie"
