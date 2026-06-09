"""Signature tool for signing artwork."""

from __future__ import annotations

import re
from typing import Any

from claude_agent_sdk import tool

from code_monet.types import Path, PathType

from .callbacks import (
    get_add_strokes_callback,
    get_canvas_dimensions,
    get_draw_callback,
    inject_canvas_image,
)
from .quality_gate import finish_block_message

# Tiny "CM" monogram. The previous long cursive signature competed with the painting.
_SIGNATURE_SVG = """M 34 13 C 25 3 8 8 6 25 C 4 42 24 48 36 36
M 50 43 L 50 9 L 66 34 L 82 9 L 82 43"""
_SIGNATURE_WIDTH = 88.0
_SIGNATURE_HEIGHT = 50.0


def _transform_svg_path(d: str, scale: float, offset_x: float, offset_y: float) -> str:
    """Transform an SVG path by scaling and translating.

    Only handles absolute SVG commands (M, L, Q, C). The signature uses
    absolute coordinates only, so relative commands are not supported.

    Args:
        d: SVG path d-string with absolute commands only
        scale: Scale factor
        offset_x: X translation after scaling
        offset_y: Y translation after scaling

    Returns:
        Transformed d-string
    """
    # This transformer handles absolute SVG commands only (uppercase)
    # Split by commands, transform coordinate pairs
    result: list[str] = []
    tokens = re.findall(r"[MLQC]|[-+]?\d*\.?\d+", d)

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in "MLQC":
            result.append(token)
            i += 1
        else:
            # It's a number - check if it's X or Y based on position
            # In SVG, coordinates come in pairs (x, y)
            x = float(token)
            if i + 1 < len(tokens) and tokens[i + 1] not in "MLQCmlqc":
                y = float(tokens[i + 1])
                # Transform
                new_x = x * scale + offset_x
                new_y = y * scale + offset_y
                result.append(f"{new_x:.1f}")
                result.append(f"{new_y:.1f}")
                i += 2
            else:
                # Single number (shouldn't happen in well-formed paths)
                result.append(str(x * scale))
                i += 1

    return " ".join(result)


def _generate_signature_paths(
    position: str = "bottom_right",
    size: str = "medium",
    color: str | None = None,
) -> list[Path]:
    """Generate signature paths for "Code Monet" at the specified position.

    Args:
        position: Where to place the signature (bottom_right, bottom_left, bottom_center)
        size: Size of signature (small, medium, large)
        color: Optional color for the signature (hex string)

    Returns:
        List of Path objects for the signature
    """
    # Size scales. Even "large" stays modest; signatures should not become the subject.
    scales = {"small": 0.55, "medium": 0.75, "large": 1.0}
    scale = scales.get(size, 0.55)

    sig_width = _SIGNATURE_WIDTH * scale
    sig_height = _SIGNATURE_HEIGHT * scale

    # Position calculations using canvas dimensions from globals
    margin = 20.0
    dims = get_canvas_dimensions()
    canvas_w: float = float(dims[0])
    canvas_h: float = float(dims[1])
    offset_x: float
    offset_y: float
    if position == "bottom_left":
        offset_x = margin
        offset_y = canvas_h - margin - sig_height
    elif position == "bottom_center":
        offset_x = (canvas_w - sig_width) / 2
        offset_y = canvas_h - margin - sig_height
    else:  # bottom_right (default)
        offset_x = canvas_w - margin - sig_width
        offset_y = canvas_h - margin - sig_height

    # Parse and transform the signature SVG
    # Split into individual path commands
    paths: list[Path] = []

    # Each M command starts a new subpath in the signature
    subpaths = _SIGNATURE_SVG.strip().split("M ")
    for subpath in subpaths:
        if not subpath.strip():
            continue

        # Reconstruct with M prefix
        d_string = "M " + subpath.strip()

        # Transform coordinates by scaling and offsetting
        transformed = _transform_svg_path(d_string, scale, offset_x, offset_y)

        path = Path(
            type=PathType.SVG,
            points=[],
            d=transformed,
            color=color or "#3f3448",
            stroke_width=1.8 * scale,
            opacity=0.38,
        )
        paths.append(path)

    return paths


async def handle_sign_canvas(args: dict[str, Any]) -> dict[str, Any]:
    """Handle sign_canvas tool call.

    Adds a small "CM" monogram to the canvas.

    Args:
        args: Dictionary with optional 'position', 'size', and 'color'

    Returns:
        Tool result with confirmation and canvas image
    """
    position = args.get("position", "bottom_right")
    size = args.get("size", "small")
    color = args.get("color")
    block_message = finish_block_message()
    if block_message is not None:
        return {
            "content": [{"type": "text", "text": block_message}],
            "is_error": True,
        }

    # Validate position
    valid_positions = ["bottom_right", "bottom_left", "bottom_center"]
    if position not in valid_positions:
        position = "bottom_right"

    # Validate size
    valid_sizes = ["small", "medium", "large"]
    if size not in valid_sizes:
        size = "small"

    # Generate signature paths
    signature_paths = _generate_signature_paths(position, size, color)

    if not signature_paths:
        return {
            "content": [{"type": "text", "text": "Error: Failed to generate signature"}],
            "is_error": True,
        }

    # Add signature strokes to state
    _add_strokes_callback = get_add_strokes_callback()
    if _add_strokes_callback is not None:
        await _add_strokes_callback(signature_paths)

    # Trigger animation (don't mark done - let agent do that separately)
    _draw_callback = get_draw_callback()
    if _draw_callback is not None:
        await _draw_callback(signature_paths, False)

    # Build response
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"Signed the canvas with a small CM monogram at {position.replace('_', ' ')} ({size} size).",
        }
    ]

    # Inject canvas image to show the result
    inject_canvas_image(content)

    return {"content": content}


@tool(
    "sign_canvas",
    """Add a small, subtle CM monogram to the canvas.

Call this tool when you're satisfied with the piece, just before marking it done.
The signature must stay small and quiet. It identifies the work without
competing with the composition.

Position options:
- bottom_right (default): Traditional artist signature placement
- bottom_left: Alternative placement for right-heavy compositions
- bottom_center: Centered signature for symmetrical pieces

Size options:
- small (default): Subtle, unobtrusive (best for painterly work)
- medium: Balanced presence
- large: Bold statement (good for minimal compositions)""",
    {
        "type": "object",
        "properties": {
            "position": {
                "type": "string",
                "enum": ["bottom_right", "bottom_left", "bottom_center"],
                "description": "Where to place the signature",
                "default": "bottom_right",
            },
            "size": {
                "type": "string",
                "enum": ["small", "medium", "large"],
                "description": "Size of the signature",
                "default": "small",
            },
            "color": {
                "type": "string",
                "description": "Optional hex color for signature. If not specified, uses a subtle dark tone that complements the piece.",
            },
        },
        "required": [],
    },
)
async def sign_canvas(args: dict[str, Any]) -> dict[str, Any]:
    """Sign the canvas with 'Code Monet'."""
    return await handle_sign_canvas(args)
