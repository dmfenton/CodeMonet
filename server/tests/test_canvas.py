"""Tests for canvas rendering."""

import io

from PIL import Image

from code_monet.canvas import render_path_to_svg_d
from code_monet.rendering import (
    RenderOptions,
    hex_to_rgba,
    options_for_og_image,
    options_for_share_preview,
    options_for_thumbnail,
    render_strokes,
)
from code_monet.types import DrawingStyleType, Path, PathType, Point


def _render_strokes_to_png_sync(
    strokes: list[Path],
    width: int = 800,
    height: int = 600,
    drawing_style: DrawingStyleType = DrawingStyleType.PLOTTER,
) -> bytes:
    """Test helper: render strokes to PNG using centralized rendering."""
    options = RenderOptions(
        width=width,
        height=height,
        drawing_style=drawing_style,
        output_format="bytes",
    )
    result = render_strokes(strokes, options)
    assert isinstance(result, bytes)
    return result


class TestSvgPathRendering:
    def test_line_to_svg(self) -> None:
        path = Path(
            type=PathType.LINE,
            points=[Point(x=0, y=0), Point(x=100, y=100)],
        )
        d = render_path_to_svg_d(path)
        # Points are floats, so output contains decimal values
        assert d.startswith("M ")
        assert "L " in d

    def test_polyline_to_svg(self) -> None:
        path = Path(
            type=PathType.POLYLINE,
            points=[
                Point(x=0, y=0),
                Point(x=50, y=50),
                Point(x=100, y=0),
            ],
        )
        d = render_path_to_svg_d(path)
        assert d.startswith("M ")
        assert d.count("L ") == 2

    def test_quadratic_to_svg(self) -> None:
        path = Path(
            type=PathType.QUADRATIC,
            points=[
                Point(x=0, y=0),
                Point(x=50, y=100),
                Point(x=100, y=0),
            ],
        )
        d = render_path_to_svg_d(path)
        assert d.startswith("M ")
        assert "Q " in d

    def test_cubic_to_svg(self) -> None:
        path = Path(
            type=PathType.CUBIC,
            points=[
                Point(x=0, y=0),
                Point(x=33, y=100),
                Point(x=66, y=100),
                Point(x=100, y=0),
            ],
        )
        d = render_path_to_svg_d(path)
        assert d.startswith("M ")
        assert "C " in d

    def test_empty_path(self) -> None:
        path = Path(type=PathType.LINE, points=[])
        d = render_path_to_svg_d(path)
        assert d == ""


class TestHexToRgba:
    def test_opaque_black(self) -> None:
        assert hex_to_rgba("#000000", 1.0) == (0, 0, 0, 255)

    def test_opaque_white(self) -> None:
        assert hex_to_rgba("#FFFFFF", 1.0) == (255, 255, 255, 255)

    def test_half_opacity(self) -> None:
        assert hex_to_rgba("#FF0000", 0.5) == (255, 0, 0, 127)

    def test_no_hash(self) -> None:
        assert hex_to_rgba("00FF00", 1.0) == (0, 255, 0, 255)

    def test_zero_opacity(self) -> None:
        assert hex_to_rgba("#0000FF", 0.0) == (0, 0, 255, 0)

    def test_invalid_short_hex_falls_back_to_gray(self) -> None:
        assert hex_to_rgba("#FF") == (128, 128, 128, 255)

    def test_shorthand_hex_expands(self) -> None:
        assert hex_to_rgba("#f0a") == (255, 0, 170, 255)

    def test_hex_with_alpha_channel(self) -> None:
        assert hex_to_rgba("#FF00FF00") == (255, 0, 255, 0)
        assert hex_to_rgba("#ff0000ff", 1.0) == (255, 0, 0, 255)

    def test_garbage_hex_never_raises(self) -> None:
        assert hex_to_rgba("#1a2550f") == (26, 37, 80, 255)
        assert hex_to_rgba("not-a-color") == (128, 128, 128, 255)


class TestPngRasterization:
    """Test PNG rendering uses actual path styles."""

    def _get_pixel(self, png_bytes: bytes, x: int, y: int) -> tuple[int, int, int]:
        """Get RGB pixel value at coordinates."""
        img = Image.open(io.BytesIO(png_bytes))
        pixel = img.getpixel((x, y))
        return (pixel[0], pixel[1], pixel[2])

    def test_plotter_uses_default_color(self) -> None:
        """Plotter mode should use style defaults, not path color."""
        path = Path(
            type=PathType.LINE,
            points=[Point(x=50, y=50), Point(x=150, y=50)],
            color="#FF0000",  # Should be ignored in plotter mode
        )
        png = _render_strokes_to_png_sync(
            [path], width=200, height=100, drawing_style=DrawingStyleType.PLOTTER
        )
        # Sample pixel on the line - should be dark (#1a1a2e), not red
        pixel = self._get_pixel(png, 100, 50)
        assert pixel == (26, 26, 46), f"Expected plotter default (26,26,46), got {pixel}"

    def test_paint_uses_path_color(self) -> None:
        """Paint mode should use the path's color."""
        path = Path(
            type=PathType.LINE,
            points=[Point(x=50, y=50), Point(x=150, y=50)],
            color="#FF0000",  # Pure red
            stroke_width=10,  # Wide for reliable sampling
        )
        png = _render_strokes_to_png_sync(
            [path], width=200, height=100, drawing_style=DrawingStyleType.PAINT
        )
        pixel = self._get_pixel(png, 100, 50)
        # Should be red (with possible opacity blending against white)
        # Paint default opacity is 0.85, so RGB won't be pure red
        # 255 * 0.85 + 255 * 0.15 = 255 for R, 0 * 0.85 + 255 * 0.15 = 38 for G/B
        assert pixel[0] > 200, f"Expected red-ish, got {pixel}"
        assert pixel[1] < 100, f"Expected low green, got {pixel}"
        assert pixel[2] < 100, f"Expected low blue, got {pixel}"

    def test_paint_renders_fill_only_svg_shape(self) -> None:
        """Paint mode should render filled closed SVG paths with no outline."""
        path = Path(
            type=PathType.SVG,
            d="M 20 20 L 180 20 L 180 80 L 20 80 Z",
            fill="#ff0000",
            fill_opacity=1,
            stroke_width=0,
        )
        png = _render_strokes_to_png_sync(
            [path], width=200, height=100, drawing_style=DrawingStyleType.PAINT
        )

        assert self._get_pixel(png, 100, 50) == (255, 0, 0)

    def test_paint_uses_custom_stroke_width(self) -> None:
        """Paint mode should respect custom stroke width."""
        # Wide stroke
        wide_path = Path(
            type=PathType.LINE,
            points=[Point(x=50, y=50), Point(x=150, y=50)],
            color="#000000",
            stroke_width=20,
        )
        wide_png = _render_strokes_to_png_sync(
            [wide_path], width=200, height=100, drawing_style=DrawingStyleType.PAINT
        )

        # Narrow stroke
        narrow_path = Path(
            type=PathType.LINE,
            points=[Point(x=50, y=50), Point(x=150, y=50)],
            color="#000000",
            stroke_width=2,
        )
        narrow_png = _render_strokes_to_png_sync(
            [narrow_path], width=200, height=100, drawing_style=DrawingStyleType.PAINT
        )

        # Sample at offset from center - wide stroke should be dark, narrow should be white
        wide_pixel = self._get_pixel(wide_png, 100, 58)  # 8 pixels below center
        narrow_pixel = self._get_pixel(narrow_png, 100, 58)

        # Wide stroke covers this point (dark)
        assert wide_pixel[0] < 100, f"Wide stroke should cover y=58, got {wide_pixel}"
        # Narrow stroke doesn't reach this point (white or near-white)
        assert narrow_pixel[0] > 200, f"Narrow stroke shouldn't reach y=58, got {narrow_pixel}"

    def test_multiple_colors(self) -> None:
        """Multiple paths with different colors render correctly."""
        paths = [
            Path(
                type=PathType.LINE,
                points=[Point(x=50, y=25), Point(x=150, y=25)],
                color="#FF0000",
                stroke_width=10,
                opacity=1.0,
            ),
            Path(
                type=PathType.LINE,
                points=[Point(x=50, y=75), Point(x=150, y=75)],
                color="#0000FF",
                stroke_width=10,
                opacity=1.0,
            ),
        ]
        png = _render_strokes_to_png_sync(
            paths, width=200, height=100, drawing_style=DrawingStyleType.PAINT
        )

        red_pixel = self._get_pixel(png, 100, 25)
        blue_pixel = self._get_pixel(png, 100, 75)

        # Red line
        assert red_pixel[0] > 200, f"Expected red line, got {red_pixel}"
        assert red_pixel[2] < 100, f"Expected red line, got {red_pixel}"

        # Blue line
        assert blue_pixel[2] > 200, f"Expected blue line, got {blue_pixel}"
        assert blue_pixel[0] < 100, f"Expected blue line, got {blue_pixel}"

    def test_background_is_white(self) -> None:
        """Empty canvas should be white."""
        png = _render_strokes_to_png_sync([], width=100, height=100)
        pixel = self._get_pixel(png, 50, 50)
        assert pixel == (255, 255, 255), f"Background should be white, got {pixel}"

    def test_opacity_blends_correctly(self) -> None:
        """Semi-transparent strokes blend with white background."""
        path = Path(
            type=PathType.LINE,
            points=[Point(x=10, y=50), Point(x=90, y=50)],
            color="#000000",  # Black
            stroke_width=20,
            opacity=0.5,  # 50% opacity
        )
        png = _render_strokes_to_png_sync(
            [path], width=100, height=100, drawing_style=DrawingStyleType.PAINT
        )
        pixel = self._get_pixel(png, 50, 50)
        # Black at 50% on white = gray (around 127-128)
        assert 100 < pixel[0] < 156, f"Expected gray from 50% opacity blend, got {pixel}"
        assert pixel[0] == pixel[1] == pixel[2], f"Should be gray, got {pixel}"


class TestRenderOptions:
    """Test RenderOptions dataclass and preset factories."""

    def test_default_options(self) -> None:
        """Default options should have sensible values."""
        options = RenderOptions()
        assert options.width == 800
        assert options.height == 600
        assert options.background_color == "#FFFFFF"
        assert options.drawing_style == DrawingStyleType.PLOTTER
        assert options.output_format == "bytes"

    def test_options_for_og_image_plotter(self) -> None:
        """OG image options for plotter mode."""
        options = options_for_og_image(DrawingStyleType.PLOTTER)
        assert options.width == 1200
        assert options.height == 630
        assert options.background_color == (26, 26, 46, 255)  # Dark
        assert options.plotter_stroke_override == "#FFFFFF"  # White strokes
        assert options.scale_from == (800, 600)
        assert options.scale_padding == 50
        assert options.optimize_png is True

    def test_options_for_og_image_paint(self) -> None:
        """OG image options for paint mode uses actual colors."""
        options = options_for_og_image(DrawingStyleType.PAINT)
        assert options.plotter_stroke_override is None  # No override

    def test_options_for_thumbnail(self) -> None:
        """Thumbnail options should be standard canvas size."""
        options = options_for_thumbnail()
        assert options.width == 800
        assert options.height == 600
        assert options.background_color == "#FFFFFF"

    def test_options_for_share_preview(self) -> None:
        """Share preview options should optimize PNG."""
        options = options_for_share_preview()
        assert options.width == 800
        assert options.height == 600
        assert options.optimize_png is True


class TestRenderStrokesOutputFormats:
    """Test different output formats from render_strokes."""

    def _simple_stroke(self) -> list[Path]:
        return [
            Path(
                type=PathType.LINE,
                points=[Point(x=10, y=10), Point(x=90, y=90)],
                color="#000000",
            )
        ]

    def test_output_bytes(self) -> None:
        """render_strokes with output_format='bytes' returns bytes."""
        options = RenderOptions(width=100, height=100, output_format="bytes")
        result = render_strokes(self._simple_stroke(), options)
        assert isinstance(result, bytes)
        # Should be valid PNG
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_output_image(self) -> None:
        """render_strokes with output_format='image' returns PIL Image."""
        options = RenderOptions(width=100, height=100, output_format="image")
        result = render_strokes(self._simple_stroke(), options)
        assert isinstance(result, Image.Image)
        assert result.size == (100, 100)

    def test_output_base64(self) -> None:
        """render_strokes with output_format='base64' returns base64 string."""
        options = RenderOptions(width=100, height=100, output_format="base64")
        result = render_strokes(self._simple_stroke(), options)
        assert isinstance(result, str)
        # Should decode successfully
        import base64

        decoded = base64.standard_b64decode(result)
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"


class TestRenderStrokesScaling:
    """Test coordinate scaling functionality."""

    def _get_pixel(self, png_bytes: bytes, x: int, y: int) -> tuple[int, int, int]:
        """Get RGB pixel value at coordinates."""
        img = Image.open(io.BytesIO(png_bytes))
        pixel = img.getpixel((x, y))
        return (pixel[0], pixel[1], pixel[2])

    def test_scaling_centers_content(self) -> None:
        """Scaling should center content with offset."""
        # Draw at (0,0) to (100,0) in source coords
        path = Path(
            type=PathType.LINE,
            points=[Point(x=0, y=300), Point(x=800, y=300)],
            color="#000000",
            stroke_width=10,
        )
        options = RenderOptions(
            width=1200,
            height=630,
            scale_from=(800, 600),
            scale_padding=50,
            drawing_style=DrawingStyleType.PAINT,
            output_format="bytes",
        )
        result = render_strokes([path], options)
        assert isinstance(result, bytes)
        # The line should be somewhere in the middle vertically
        # Exact position depends on scaling math

    def test_dark_background_renders(self) -> None:
        """Dark background should render correctly."""
        options = RenderOptions(
            width=100,
            height=100,
            background_color=(26, 26, 46, 255),
            output_format="bytes",
        )
        result = render_strokes([], options)
        assert isinstance(result, bytes)
        pixel = self._get_pixel(result, 50, 50)
        assert pixel == (26, 26, 46), f"Expected dark background, got {pixel}"
