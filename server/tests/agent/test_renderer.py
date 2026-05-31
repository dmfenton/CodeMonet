"""Tests for the agent renderer module."""

import base64
from dataclasses import replace
from unittest.mock import MagicMock

from PIL import Image

from code_monet.agent.renderer import image_to_base64
from code_monet.rendering import RenderOptions, options_for_agent_view, render_strokes
from code_monet.types import DrawingStyleType, Path, PathType, Point


def _create_mock_canvas(
    strokes: list[Path] | None = None,
    width: int = 800,
    height: int = 600,
    drawing_style: DrawingStyleType = DrawingStyleType.PLOTTER,
) -> MagicMock:
    """Create a mock canvas state."""
    canvas = MagicMock()
    canvas.strokes = strokes or []
    canvas.width = width
    canvas.height = height
    canvas.drawing_style = drawing_style
    return canvas


def _luminance(pixel: tuple[int, int, int]) -> float:
    return 0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]


class TestRenderCanvasToImage:
    """Tests for render_strokes with options_for_agent_view."""

    def test_empty_canvas_renders_white_background(self) -> None:
        """Empty canvas renders as white image."""
        canvas = _create_mock_canvas()
        options = options_for_agent_view(canvas)

        img = render_strokes(canvas.strokes, options)

        assert isinstance(img, Image.Image)
        assert img.mode == "RGB"
        assert img.size == (800, 600)
        # Check that center pixel is white
        pixel = img.getpixel((400, 300))
        assert pixel == (255, 255, 255)

    def test_strokes_render_with_correct_colors(self) -> None:
        """Strokes render with style-appropriate colors."""
        # Create a simple line stroke
        stroke = Path(
            type=PathType.LINE,
            points=[Point(x=100, y=100), Point(x=200, y=100)],
            author="agent",
        )
        canvas = _create_mock_canvas(strokes=[stroke])
        options = options_for_agent_view(canvas)

        img = render_strokes(canvas.strokes, options)

        assert isinstance(img, Image.Image)
        # The stroke should be drawn (not white)
        # Check a pixel along the line
        pixel = img.getpixel((150, 100))
        assert pixel != (255, 255, 255)

    def test_human_strokes_highlighted(self) -> None:
        """Human strokes render in highlight color when highlight_human=True."""
        stroke = Path(
            type=PathType.LINE,
            points=[Point(x=100, y=100), Point(x=200, y=100)],
            author="human",
        )
        canvas = _create_mock_canvas(strokes=[stroke])
        options = options_for_agent_view(canvas)  # highlight_human=True by default

        img = render_strokes(canvas.strokes, options)

        assert isinstance(img, Image.Image)
        # The stroke should be drawn (not white)
        pixel = img.getpixel((150, 100))
        assert pixel != (255, 255, 255)

    def test_human_strokes_not_highlighted(self) -> None:
        """Human strokes render normally when highlight_human=False."""
        stroke = Path(
            type=PathType.LINE,
            points=[Point(x=100, y=100), Point(x=200, y=100)],
            author="human",
        )
        canvas = _create_mock_canvas(strokes=[stroke])
        options = replace(options_for_agent_view(canvas), highlight_human=False)

        img = render_strokes(canvas.strokes, options)

        assert isinstance(img, Image.Image)
        # The stroke should still be drawn
        pixel = img.getpixel((150, 100))
        assert pixel != (255, 255, 255)

    def test_returns_pil_image(self) -> None:
        """Function returns a PIL Image object."""
        canvas = _create_mock_canvas()
        options = options_for_agent_view(canvas)

        result = render_strokes(canvas.strokes, options)

        assert isinstance(result, Image.Image)

    def test_custom_canvas_size(self) -> None:
        """Respects custom canvas dimensions."""
        canvas = _create_mock_canvas(width=400, height=300)
        options = options_for_agent_view(canvas)

        img = render_strokes(canvas.strokes, options)

        assert isinstance(img, Image.Image)
        assert img.size == (400, 300)


class TestImageToBase64:
    """Tests for image_to_base64 function."""

    def test_returns_base64_string(self) -> None:
        """Returns a base64-encoded string."""
        img = Image.new("RGB", (100, 100), color="white")

        result = image_to_base64(img)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_base64_is_decodable(self) -> None:
        """Base64 string can be decoded back."""
        img = Image.new("RGB", (100, 100), color="white")

        result = image_to_base64(img)
        decoded = base64.standard_b64decode(result)

        assert len(decoded) > 0

    def test_output_is_valid_png(self) -> None:
        """Decoded output is valid PNG data."""
        img = Image.new("RGB", (50, 50), color="red")

        result = image_to_base64(img)
        decoded = base64.standard_b64decode(result)

        # PNG magic bytes
        assert decoded[:4] == b"\x89PNG"

    def test_handles_different_image_sizes(self) -> None:
        """Handles various image sizes."""
        for size in [(10, 10), (100, 200), (1920, 1080)]:
            img = Image.new("RGB", size, color="blue")
            result = image_to_base64(img)
            assert isinstance(result, str)
            assert len(result) > 0


class TestPaintModeStrokeLayering:
    """Tests for per-stroke compositing in paint mode."""

    def test_overlapping_strokes_accumulate_opacity(self) -> None:
        """Two overlapping semi-transparent strokes should be more opaque than one."""
        # A horizontal line through the center of a small canvas
        line = Path(
            type=PathType.POLYLINE,
            points=[Point(x=10, y=50), Point(x=90, y=50)],
            color="#000000",
            opacity=0.5,
            author="agent",
        )
        options = RenderOptions(
            width=100,
            height=100,
            drawing_style=DrawingStyleType.PAINT,
            output_format="image",
        )

        img_one = render_strokes([line], options)
        img_two = render_strokes([line, line], options)

        # Sample a pixel on the stroke path. With two overlapping strokes
        # the result should be darker (lower RGB on white background).
        assert isinstance(img_one, Image.Image)
        assert isinstance(img_two, Image.Image)
        r_one = img_one.getpixel((50, 50))[0]
        r_two = img_two.getpixel((50, 50))[0]
        assert r_two < r_one, (
            f"Two overlapping strokes should be darker than one, got {r_two} vs {r_one}"
        )

    def test_broad_flat_brush_has_no_dark_outer_rail(self) -> None:
        """Broad painterly strokes should blend at the edge instead of drawing outlines."""
        stroke = Path(
            type=PathType.LINE,
            points=[Point(x=10, y=50), Point(x=90, y=50)],
            brush="oil_flat",
            color="#d09060",
            stroke_width=30,
            opacity=0.8,
            author="agent",
        )
        options = RenderOptions(
            width=100,
            height=100,
            drawing_style=DrawingStyleType.PAINT,
            output_format="image",
        )

        img = render_strokes([stroke], options)

        assert isinstance(img, Image.Image)
        center = _luminance(img.getpixel((50, 50)))
        upper_edge = _luminance(img.getpixel((50, 35)))
        lower_edge = _luminance(img.getpixel((50, 65)))
        assert upper_edge >= center - 8
        assert lower_edge >= center - 8
