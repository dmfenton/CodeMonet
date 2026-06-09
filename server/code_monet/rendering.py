"""Centralized image rendering for canvas strokes.

This module provides a unified API for rendering strokes to images with
configurable options for background, dimensions, scaling, and output format.
"""

from __future__ import annotations

import asyncio
import base64
import io
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from PIL import Image, ImageDraw, ImageFilter

from code_monet.brushes import expand_brush_stroke
from code_monet.canvas import path_to_point_list
from code_monet.types import DrawingStyleType, Path, get_style_config

if TYPE_CHECKING:
    from code_monet.types import CanvasState
    from code_monet.workspace import WorkspaceState


def hex_to_rgba(hex_color: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    """Convert hex color and opacity to RGBA tuple.

    Args:
        hex_color: Hex color string like "#FF0000" or "FF0000"
        opacity: Opacity value from 0.0 to 1.0

    Returns:
        RGBA tuple (r, g, b, a) with values 0-255

    Raises:
        ValueError: If hex_color is not a valid 6-character hex string
    """
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"Invalid hex color: expected 6 characters, got {len(hex_color)}")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return (r, g, b, int(opacity * 255))


def image_to_base64(img: Image.Image) -> str:
    """Convert PIL Image to base64 string."""
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")


@dataclass(frozen=True)
class RenderOptions:
    """Configuration for stroke rendering.

    Attributes:
        width: Output image width in pixels
        height: Output image height in pixels
        background_color: Background color as hex string or RGBA tuple
        drawing_style: Style config for stroke appearance
        highlight_human: Render human strokes in highlight color
        plotter_stroke_override: Override stroke color (e.g., white on dark bg)
        expand_brushes: Expand legacy brush strokes into bristles
        scale_from: Source dimensions (w, h) for scaling strokes
        scale_padding: Padding when scaling
        output_format: Return type - "image" (PIL), "bytes", or "base64"
    optimize_png: Enable PNG optimization (slower but smaller)
        paint_antialias_scale: Supersampling scale for smoother paint strokes
    """

    width: int = 800
    height: int = 600
    background_color: str | tuple[int, int, int, int] = "#FFFFFF"
    drawing_style: DrawingStyleType = DrawingStyleType.PLOTTER
    highlight_human: bool = False
    plotter_stroke_override: str | None = None
    expand_brushes: bool = False
    scale_from: tuple[int, int] | None = None
    scale_padding: int = 0
    output_format: Literal["image", "bytes", "base64"] = "bytes"
    optimize_png: bool = False
    paint_antialias_scale: int = 1

    def _parse_background(self) -> tuple[int, int, int, int]:
        """Parse background_color to RGBA tuple."""
        if isinstance(self.background_color, tuple):
            return self.background_color
        return hex_to_rgba(self.background_color, 1.0)


@dataclass
class _ScaleTransform:
    """Computed scale and offset for transforming coordinates."""

    scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0

    def apply(self, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Apply scale and offset to point list."""
        if self.scale == 1.0 and self.offset_x == 0.0 and self.offset_y == 0.0:
            return points
        return [(x * self.scale + self.offset_x, y * self.scale + self.offset_y) for x, y in points]


def _compute_transform(options: RenderOptions) -> _ScaleTransform:
    """Compute scale transform from options."""
    if options.scale_from is None:
        return _ScaleTransform()

    src_w, src_h = options.scale_from
    target_w = options.width - 2 * options.scale_padding
    target_h = options.height - 2 * options.scale_padding

    scale = min(target_w / src_w, target_h / src_h)
    offset_x = (options.width - src_w * scale) / 2
    offset_y = (options.height - src_h * scale) / 2

    return _ScaleTransform(scale=scale, offset_x=offset_x, offset_y=offset_y)


def _scale_points(points: list[tuple[float, float]], scale: int) -> list[tuple[float, float]]:
    return [(x * scale, y * scale) for x, y in points]


def _paint_stroke_blur(path: Path, stroke_width: int) -> float:
    match path.brush:
        case "airbrush":
            base = 3.2
        case "watercolor":
            base = 2.4
        case "charcoal":
            base = 0.9
        case "oil_round":
            base = 0.72
        case "oil_filbert":
            base = 0.82
        case "oil_flat":
            base = 1.35
        case "dry_brush":
            base = 0.42
        case "palette_knife":
            base = 0.12
        case _:
            base = 0.32
    if path.brush in {"airbrush", "watercolor", "oil_flat", "oil_filbert"} and stroke_width >= 16:
        return max(base, min(6.0, stroke_width * 0.09))
    return base


def _is_blending_brush(brush: str | None) -> bool:
    return brush in {"airbrush", "watercolor", "oil_flat", "oil_filbert"}


def _draw_paint_texture(
    layer: Image.Image,
    points: list[tuple[float, float]],
    rgba: tuple[int, int, int, int],
    stroke_width: int,
    brush: str | None,
) -> None:
    """Add painterly broken color and light-catching texture to a stroke layer."""
    if len(points) < 2 or stroke_width < 3:
        return

    draw = ImageDraw.Draw(layer)
    blending_brush = _is_blending_brush(brush)
    broad_mark = stroke_width >= 16
    alpha_scale = 0.045 if blending_brush and broad_mark else 0.08 if blending_brush else 0.13
    texture_alpha = max(2, min(24, int(rgba[3] * alpha_scale)))
    texture_width_scale = (
        0.07 if blending_brush and broad_mark else 0.12 if blending_brush else 0.16
    )
    width = max(1, int(stroke_width * texture_width_scale))

    # Stable pseudo-random texture from stroke geometry, so renders are repeatable.
    seed = int(sum((x * 17.0 + y * 31.0) for x, y in points)) & 0xFFFFFFFF
    import random

    rng = random.Random(seed)
    pass_count = {
        "dry_brush": 3,
        "splatter": 6,
        "palette_knife": 2,
        "watercolor": 1,
        "airbrush": 1,
        "oil_flat": 1,
    }.get(brush or "", 2)
    if blending_brush and broad_mark:
        pass_count = 0

    for _ in range(pass_count):
        jitter = (
            stroke_width * rng.uniform(0.02, 0.10)
            if blending_brush and broad_mark
            else stroke_width * rng.uniform(0.06, 0.20)
            if blending_brush
            else stroke_width * rng.uniform(0.08, 0.28)
        )
        jittered = [
            (
                x + rng.uniform(-jitter, jitter),
                y + rng.uniform(-jitter, jitter),
            )
            for x, y in points
        ]
        jitter_low, jitter_high = (-6, 12) if blending_brush else (-18, 24)
        color = (
            max(0, min(255, int(rgba[0] + rng.uniform(jitter_low, jitter_high)))),
            max(0, min(255, int(rgba[1] + rng.uniform(jitter_low, jitter_high)))),
            max(0, min(255, int(rgba[2] + rng.uniform(jitter_low, jitter_high)))),
            texture_alpha,
        )
        if not (blending_brush and broad_mark) and len(jittered) > 3 and rng.random() < 0.7:
            start = rng.randrange(0, len(jittered) - 2)
            end = rng.randrange(start + 2, len(jittered) + 1)
            jittered = jittered[start:end]
        _draw_brush_polyline(draw, jittered, color, width, brush)

    if brush in {"oil_round", "oil_filbert", "palette_knife"} and rng.random() < 0.45:
        light = (
            max(0, min(255, int(rgba[0] + rng.uniform(8, 28)))),
            max(0, min(255, int(rgba[1] + rng.uniform(8, 28)))),
            max(0, min(255, int(rgba[2] + rng.uniform(8, 28)))),
            max(2, min(10, int(rgba[3] * 0.035))),
        )
        _draw_brush_polyline(
            draw,
            points,
            light,
            max(1, int(stroke_width * 0.08)),
            brush,
        )


def _draw_brush_polyline(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    fill: tuple[int, int, int, int],
    width: int,
    brush: str | None,
) -> None:
    if brush in {"oil_round", "oil_filbert", "marker", "ink"}:
        _draw_rounded_polyline(draw, points, fill, width)
        return
    draw.line(points, fill=fill, width=width, joint="curve")


def _draw_rounded_polyline(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    fill: tuple[int, int, int, int],
    width: int,
) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill=fill, width=width, joint="curve")
    radius = width / 2
    for x, y in (points[0], points[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def _render_paint_stroke(
    img: Image.Image,
    path: Path,
    points: list[tuple[float, float]],
    rgba: tuple[int, int, int, int],
    stroke_width: int,
    scale: int,
) -> Image.Image:
    scaled_size = (img.width * scale, img.height * scale)
    scaled_points = _scale_points(points, scale)
    scaled_width = max(1, stroke_width * scale)

    layer = Image.new("RGBA", scaled_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    scaled_rgba = rgba
    _draw_brush_polyline(draw, scaled_points, scaled_rgba, scaled_width, path.brush)
    _draw_paint_texture(layer, scaled_points, scaled_rgba, scaled_width, path.brush)

    blur = _paint_stroke_blur(path, stroke_width) * scale
    if blur > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(radius=blur))

    layer = layer.resize(img.size, Image.Resampling.LANCZOS)
    return Image.alpha_composite(img, layer)


def _render_paint_stroke_reusing_layer(
    img: Image.Image,
    layer: Image.Image,
    path: Path,
    points: list[tuple[float, float]],
    rgba: tuple[int, int, int, int],
    stroke_width: int,
) -> Image.Image:
    layer.paste((0, 0, 0, 0), (0, 0, img.width, img.height))
    draw = ImageDraw.Draw(layer)
    _draw_brush_polyline(draw, points, rgba, stroke_width, path.brush)
    _draw_paint_texture(layer, points, rgba, stroke_width, path.brush)

    blur = _paint_stroke_blur(path, stroke_width)
    composited_layer = layer.filter(ImageFilter.GaussianBlur(radius=blur)) if blur > 0 else layer
    return Image.alpha_composite(img, composited_layer)


def _render_filled_path(
    img: Image.Image,
    points: list[tuple[float, float]],
    fill: tuple[int, int, int, int],
) -> Image.Image:
    if len(points) < 3:
        return img
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.polygon(points, fill=fill)
    return Image.alpha_composite(img, layer)


def render_strokes(
    strokes: list[Path],
    options: RenderOptions | None = None,
) -> Image.Image | bytes | str:
    """Core sync function to render strokes to an image.

    Args:
        strokes: List of Path objects to render
        options: Render configuration (uses defaults if None)

    Returns:
        PIL Image, PNG bytes, or base64 string depending on options.output_format
    """
    if options is None:
        options = RenderOptions()

    style_config = get_style_config(options.drawing_style)
    transform = _compute_transform(options)

    # Create image with background
    bg_rgba = options._parse_background()
    img = Image.new("RGBA", (options.width, options.height), bg_rgba)

    # In paint mode, each stroke is composited individually so translucent
    # layers accumulate like paint. Plotter mode uses one shared layer.
    per_stroke_compositing = options.drawing_style == DrawingStyleType.PAINT

    shared_layer = Image.new("RGBA", (options.width, options.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shared_layer)

    # Build list of paths, expanding brush strokes if needed
    paths_to_render: list[Path] = []
    if options.expand_brushes:
        for path in strokes:
            if path.brush:
                paths_to_render.extend(
                    expand_brush_stroke(
                        path,
                        canvas_width=options.width,
                        canvas_height=options.height,
                    )
                )
            else:
                paths_to_render.append(path)
    else:
        paths_to_render = strokes

    for path in paths_to_render:
        points = path_to_point_list(path)
        if len(points) < 2:
            continue

        # Get effective style
        effective_style = path.get_effective_style(style_config)

        # Determine stroke color
        if options.plotter_stroke_override and options.drawing_style == DrawingStyleType.PLOTTER:
            rgba = hex_to_rgba(options.plotter_stroke_override, effective_style.opacity)
        elif options.highlight_human and path.author == "human":
            rgba = hex_to_rgba(style_config.human_stroke.color, effective_style.opacity)
        else:
            rgba = hex_to_rgba(effective_style.color, effective_style.opacity)

        # Apply scaling
        scaled_points = transform.apply(points)
        fill_color = path.fill
        if fill_color:
            if not per_stroke_compositing:
                img = Image.alpha_composite(img, shared_layer)
                shared_layer = Image.new("RGBA", (options.width, options.height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(shared_layer)
            fill_opacity = (
                path.fill_opacity if path.fill_opacity is not None else effective_style.opacity
            )
            img = _render_filled_path(img, scaled_points, hex_to_rgba(fill_color, fill_opacity))

        if effective_style.stroke_width <= 0:
            continue

        stroke_width = max(1, int(effective_style.stroke_width * transform.scale))

        if per_stroke_compositing:
            antialias_scale = max(1, options.paint_antialias_scale)
            if path.brush is None:
                shared_layer.paste((0, 0, 0, 0), (0, 0, options.width, options.height))
                draw = ImageDraw.Draw(shared_layer)
                draw.line(scaled_points, fill=rgba, width=stroke_width)
                img = Image.alpha_composite(img, shared_layer)
            elif antialias_scale == 1:
                img = _render_paint_stroke_reusing_layer(
                    img, shared_layer, path, scaled_points, rgba, stroke_width
                )
            else:
                img = _render_paint_stroke(
                    img,
                    path,
                    scaled_points,
                    rgba,
                    stroke_width,
                    antialias_scale,
                )
        else:
            draw.line(scaled_points, fill=rgba, width=stroke_width)

    if not per_stroke_compositing:
        img = Image.alpha_composite(img, shared_layer)
    img = img.convert("RGB")

    # Return in requested format
    if options.output_format == "image":
        return img

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=options.optimize_png)
    png_bytes = buffer.getvalue()

    if options.output_format == "base64":
        return base64.standard_b64encode(png_bytes).decode("utf-8")

    return png_bytes


async def render_strokes_async(
    strokes: list[Path],
    options: RenderOptions | None = None,
) -> Image.Image | bytes | str:
    """Async wrapper for render_strokes (runs in thread pool)."""
    return await asyncio.to_thread(render_strokes, strokes, options)


# =============================================================================
# Convenience functions for common use cases
# =============================================================================


def render_canvas(
    canvas: CanvasState,
    *,
    highlight_human: bool = False,
    expand_brushes: bool = False,
    output_format: Literal["image", "bytes", "base64"] = "bytes",
) -> Image.Image | bytes | str:
    """Render a CanvasState to an image.

    Convenience wrapper that extracts dimensions and style from canvas.
    """
    options = RenderOptions(
        width=canvas.width,
        height=canvas.height,
        drawing_style=canvas.drawing_style,
        highlight_human=highlight_human,
        expand_brushes=expand_brushes,
        output_format=output_format,
    )
    return render_strokes(canvas.strokes, options)


def render_workspace(
    state: WorkspaceState,
    *,
    highlight_human: bool = True,
    output_format: Literal["image", "bytes", "base64"] = "bytes",
) -> Image.Image | bytes | str:
    """Render a WorkspaceState's canvas to an image."""
    return render_canvas(
        state.canvas,
        highlight_human=highlight_human,
        output_format=output_format,
    )


async def render_workspace_async(
    state: WorkspaceState,
    *,
    highlight_human: bool = True,
    output_format: Literal["image", "bytes", "base64"] = "bytes",
) -> Image.Image | bytes | str:
    """Async wrapper for render_workspace."""
    return await asyncio.to_thread(
        render_workspace, state, highlight_human=highlight_human, output_format=output_format
    )


# =============================================================================
# Preset factories for common rendering scenarios
# =============================================================================


def options_for_agent_view(canvas: CanvasState) -> RenderOptions:
    """Options for rendering canvas for agent viewing.

    - Highlights human strokes
    - Uses direct painterly stroke rendering so AI sees mass, not bristle rails
    - Returns PIL Image for direct use
    """
    return RenderOptions(
        width=canvas.width,
        height=canvas.height,
        drawing_style=canvas.drawing_style,
        highlight_human=True,
        expand_brushes=False,
        output_format="image",
    )


def options_for_og_image(
    drawing_style: DrawingStyleType = DrawingStyleType.PLOTTER,
    source_width: int = 800,
    source_height: int = 600,
) -> RenderOptions:
    """Options for Open Graph social sharing images.

    - 1200x630 (optimal OG size)
    - Dark background matching site theme
    - White strokes for plotter mode visibility
    - Scales from source canvas dimensions with padding
    """
    return RenderOptions(
        width=1200,
        height=630,
        background_color=(26, 26, 46, 255),  # Dark background
        drawing_style=drawing_style,
        plotter_stroke_override="#FFFFFF" if drawing_style == DrawingStyleType.PLOTTER else None,
        scale_from=(source_width, source_height),
        scale_padding=50,
        optimize_png=True,
    )


def options_for_thumbnail(
    drawing_style: DrawingStyleType = DrawingStyleType.PLOTTER,
    width: int = 800,
    height: int = 600,
) -> RenderOptions:
    """Options for gallery thumbnails.

    - Uses saved canvas dimensions
    - White background
    """
    return RenderOptions(
        width=width,
        height=height,
        background_color="#FFFFFF",
        drawing_style=drawing_style,
        expand_brushes=False,
    )


def options_for_share_preview(
    drawing_style: DrawingStyleType = DrawingStyleType.PLOTTER,
    width: int = 800,
    height: int = 600,
) -> RenderOptions:
    """Options for share link preview images.

    - Uses saved canvas dimensions
    - White background
    - PNG optimization for smaller files
    """
    return RenderOptions(
        width=width,
        height=height,
        background_color="#FFFFFF",
        drawing_style=drawing_style,
        expand_brushes=False,
        optimize_png=True,
    )
