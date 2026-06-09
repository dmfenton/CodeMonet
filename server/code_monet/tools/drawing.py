"""Drawing tools: draw_paths, mark_piece_done, view_canvas."""

from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import tool

from code_monet.types import Path

from .callbacks import (
    get_add_strokes_callback,
    get_canvas_callback,
    get_canvas_dimensions,
    get_draw_callback,
    image_content_from_png,
    inject_canvas_image,
)
from .path_parsing import parse_path_data
from .quality_gate import (
    finish_block_message,
    note_drawing,
    record_mark_piece_done_attempt,
    required_generate_svg_helpers,
)

logger = logging.getLogger(__name__)

AUTO_CANVAS_IMAGE_PATH_LIMIT = 160

VIEW_CANVAS_AUDIT_TEXT = (
    "Inspect the actual rendered canvas. Report visible failures first, not intentions. "
    "Before signing or naming, verify: required subject nouns are present; dominant silhouette "
    "reads at thumbnail size; key counter-shape is clear; lower/foreground sectors are not empty "
    "when the reference needs structure; small figures/objects are readable silhouettes with "
    "contact; no accidental scaffolds, long closure lines, flat caps, or generic helper shapes "
    "are dominating. If any item fails, revise before finishing."
)


async def handle_draw_paths(args: dict[str, Any]) -> dict[str, Any]:
    """Handle draw_paths tool call (testable without decorator).

    Args:
        args: Dictionary with 'paths' (array of path objects) and optional 'done' (bool)

    Returns:
        Tool result with success/error status
    """
    paths_data = args.get("paths", [])
    done = args.get("done", False)
    block_done_message = finish_block_message() if done else None
    effective_done = done and block_done_message is None

    if not isinstance(paths_data, list):
        return {
            "content": [{"type": "text", "text": "Error: paths must be an array"}],
            "is_error": True,
        }

    required_helpers = required_generate_svg_helpers()
    if paths_data and required_helpers:
        helper_list = ", ".join(f"`{helper}(...)`" for helper in required_helpers)
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Quality gate blocked draw_paths before drawing. "
                        "The last critique requires a structural helper-based repair; "
                        f"use generate_svg with {helper_list} instead."
                    ),
                }
            ],
            "is_error": True,
        }

    # Parse paths
    parsed_paths: list[Path] = []
    errors: list[str] = []
    canvas_width, canvas_height = get_canvas_dimensions()

    for i, path_data in enumerate(paths_data):
        if not isinstance(path_data, dict):
            errors.append(f"Path {i}: must be an object")
            continue

        path = parse_path_data(
            path_data,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
        if path is None:
            errors.append(f"Path {i}: invalid format (need type and points)")
        else:
            parsed_paths.append(path)

    # Add strokes to state immediately (so canvas image includes them)
    _add_strokes_callback = get_add_strokes_callback()
    _draw_callback = get_draw_callback()

    logger.info(
        f"draw_paths: {len(parsed_paths)} paths, add_strokes={'set' if _add_strokes_callback else 'None'}"
    )
    if parsed_paths and _add_strokes_callback is not None:
        await _add_strokes_callback(parsed_paths)
    note_drawing(len(parsed_paths))

    # Call the draw callback for animation (strokes already in state)
    logger.info(f"draw_paths: triggering animation, callback={'set' if _draw_callback else 'None'}")
    if parsed_paths and _draw_callback is not None:
        await _draw_callback(parsed_paths, effective_done)

    # Build response content
    content: list[dict[str, Any]] = []

    # Report errors if any
    if errors:
        content.append(
            {
                "type": "text",
                "text": f"Parsed {len(parsed_paths)} paths with {len(errors)} errors:\n"
                + "\n".join(errors),
            }
        )
        if len(parsed_paths) == 0:
            return {"content": content, "is_error": True}
    else:
        content.append(
            {
                "type": "text",
                "text": f"Successfully drew {len(parsed_paths)} paths."
                + (" Piece marked as complete." if effective_done else ""),
            }
        )

    if block_done_message is not None:
        content[0]["text"] += f" {block_done_message}"

    # Inject canvas image for small batches. Large batches can exceed SDK transport limits;
    # the agent can call view_canvas explicitly when it needs visual inspection.
    if 0 < len(parsed_paths) <= AUTO_CANVAS_IMAGE_PATH_LIMIT:
        inject_canvas_image(content)
    elif parsed_paths:
        content[0]["text"] += " Canvas image omitted for dense batch; call view_canvas to inspect."

    return {"content": content}


async def handle_mark_piece_done() -> dict[str, Any]:
    """Handle mark_piece_done tool call (testable without decorator).

    Returns:
        Tool result confirming the piece is done
    """
    _draw_callback = get_draw_callback()
    block_message = finish_block_message()
    if block_message is not None:
        record_mark_piece_done_attempt(False)
        return {
            "content": [{"type": "text", "text": block_message}],
            "is_error": True,
        }

    if _draw_callback is not None:
        await _draw_callback([], True)
    record_mark_piece_done_attempt(True)

    return {
        "content": [{"type": "text", "text": "Piece marked as complete."}],
    }


async def handle_view_canvas() -> dict[str, Any]:
    """Handle view_canvas tool call (testable without decorator).

    Returns:
        Tool result with the current canvas image
    """
    _get_canvas_callback = get_canvas_callback()
    if _get_canvas_callback is None:
        return {
            "content": [{"type": "text", "text": "Error: Canvas not available"}],
            "is_error": True,
        }

    try:
        png_bytes = _get_canvas_callback()

        return {
            "content": [
                {"type": "text", "text": VIEW_CANVAS_AUDIT_TEXT},
                image_content_from_png(png_bytes),
            ],
        }
    except Exception as e:
        logger.warning(f"Failed to get canvas image: {e}")
        return {
            "content": [{"type": "text", "text": f"Error: Failed to render canvas: {e}"}],
            "is_error": True,
        }


@tool(
    "draw_paths",
    """Draw paths on the current canvas. Coordinates must be within the canvas bounds from the turn prompt.

The paths array supports dense coherent batches. Use many paths in one call when you already know the marks,
especially for hatching, foam, foliage, crowds, city texture, waves, and other high-detail subjects.

Closed svg paths can be filled. Use fill and fill_opacity for solid grounds, silhouettes, color masses,
water/sky planes, shadows, and poster-like shapes. Set stroke_width to 0 for a filled shape with no outline.

In Paint mode, you can specify a brush preset for realistic paint effects:
- oil_round: Classic round brush with visible bristle texture (good for blending)
- oil_flat: Flat brush with parallel marks (good for blocking shapes)
- oil_filbert: Rounded flat brush (good for organic shapes)
- watercolor: Translucent with soft edges (good for washes)
- dry_brush: Scratchy, broken strokes (good for texture)
- palette_knife: Sharp edges, thick paint (good for impasto)
- ink: Pressure-sensitive with elegant taper (good for calligraphy)
- pencil: Thin, consistent lines (good for sketching)
- charcoal: Smudgy edges with texture (good for value studies)
- marker: Solid color with slight edge bleed
- airbrush: Very soft edges (good for gradients)
- splatter: Random dots around stroke (good for effects)""",
    {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "description": "Array of path objects to draw. Dense batches with dozens or hundreds of paths are supported when the marks are intentional.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["line", "polyline", "quadratic", "cubic", "svg"],
                            "description": "Path type: line (2 pts), polyline (N pts), quadratic (3 pts), cubic (4 pts), svg (d-string)",
                        },
                        "points": {
                            "type": "array",
                            "description": "Array of points (for line, polyline, quadratic, cubic)",
                            "items": {
                                "type": "object",
                                "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                                "required": ["x", "y"],
                            },
                        },
                        "d": {
                            "type": "string",
                            "description": "SVG path d-string (for type=svg). Coordinates must be within canvas bounds. Close filled shapes with Z. Example: 'M 100 100 L 400 300 C 500 200 600 400 700 300 Z'",
                        },
                        "brush": {
                            "type": "string",
                            "enum": [
                                "oil_round",
                                "oil_flat",
                                "oil_filbert",
                                "watercolor",
                                "dry_brush",
                                "palette_knife",
                                "ink",
                                "pencil",
                                "charcoal",
                                "marker",
                                "airbrush",
                                "splatter",
                            ],
                            "description": "Brush preset for paint-like effects (Paint mode only). Each brush has unique texture and behavior.",
                        },
                        "color": {
                            "type": "string",
                            "description": "Hex color for the path (Paint mode only). Example: '#e94560'",
                        },
                        "stroke_width": {
                            "type": "number",
                            "description": "Stroke width 0-30 (Paint mode only). Use 0 for filled shapes with no outline.",
                        },
                        "opacity": {
                            "type": "number",
                            "description": "Opacity 0-1 (Paint mode only). Default: 1",
                        },
                        "fill": {
                            "type": "string",
                            "description": "Hex fill color for closed paths. Example: '#f7ead0'",
                        },
                        "fill_opacity": {
                            "type": "number",
                            "description": "Fill opacity 0-1. Default follows path opacity.",
                        },
                    },
                    "required": ["type"],
                },
            },
            "done": {
                "type": "boolean",
                "description": "Set to true when the piece is complete",
                "default": False,
            },
        },
        "required": ["paths"],
    },
)
async def draw_paths(args: dict[str, Any]) -> dict[str, Any]:
    """Draw paths on the canvas."""
    return await handle_draw_paths(args)


@tool(
    "mark_piece_done",
    "Signal that the current piece is complete. Call this when you're satisfied with the drawing.",
    {"type": "object", "properties": {}, "required": []},
)
async def mark_piece_done(_args: dict[str, Any]) -> dict[str, Any]:
    """Mark the current piece as complete."""
    return await handle_mark_piece_done()


@tool(
    "view_canvas",
    "View the current canvas state as an image. Your strokes appear in black, human strokes appear in blue. Call this anytime to see your work.",
    {"type": "object", "properties": {}, "required": []},
)
async def view_canvas(_args: dict[str, Any]) -> dict[str, Any]:
    """View the current canvas as an image."""
    return await handle_view_canvas()
