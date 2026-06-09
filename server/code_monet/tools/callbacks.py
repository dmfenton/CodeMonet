"""Global callbacks for tool communication with the agent."""

from __future__ import annotations

import base64
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from code_monet.types import Path

logger = logging.getLogger(__name__)

# Type aliases for callbacks
DrawCallback = Callable[["list[Path]", bool], Awaitable[None]]
GetCanvasCallback = Callable[[], bytes]
AddStrokesCallback = Callable[["list[Path]"], Awaitable[None]]
WorkspaceDirCallback = Callable[[], str]
PieceTitleCallback = Callable[[str], Awaitable[None]]

# Global callbacks - will be set by the agent
_draw_callback: DrawCallback | None = None
_get_canvas_callback: GetCanvasCallback | None = None
_add_strokes_callback: AddStrokesCallback | None = None
_get_workspace_dir_callback: WorkspaceDirCallback | None = None
_set_piece_title_callback: PieceTitleCallback | None = None

# Global canvas dimensions
_canvas_width: int = 800
_canvas_height: int = 600


def set_draw_callback(callback: DrawCallback | None) -> None:
    """Set the callback function for drawing paths."""
    global _draw_callback
    _draw_callback = callback


def set_get_canvas_callback(callback: GetCanvasCallback | None) -> None:
    """Set the callback function for getting canvas image."""
    global _get_canvas_callback
    _get_canvas_callback = callback


def set_add_strokes_callback(callback: AddStrokesCallback | None) -> None:
    """Set the callback function for adding strokes to state.

    This callback adds strokes to state synchronously (before the tool returns)
    so the canvas image can include the new strokes.
    """
    global _add_strokes_callback
    _add_strokes_callback = callback


def set_workspace_dir_callback(callback: WorkspaceDirCallback | None) -> None:
    """Set the callback function for getting the workspace directory.

    Used by generate_image to save reference images.
    """
    global _get_workspace_dir_callback
    _get_workspace_dir_callback = callback


def set_piece_title_callback(callback: PieceTitleCallback | None) -> None:
    """Set the callback function for saving the piece title."""
    global _set_piece_title_callback
    _set_piece_title_callback = callback


def set_canvas_dimensions(width: int, height: int) -> None:
    """Set the canvas dimensions for Python code execution."""
    global _canvas_width, _canvas_height
    _canvas_width = width
    _canvas_height = height


def get_draw_callback() -> DrawCallback | None:
    """Get the current draw callback."""
    return _draw_callback


def get_canvas_callback() -> GetCanvasCallback | None:
    """Get the current canvas callback."""
    return _get_canvas_callback


def get_add_strokes_callback() -> AddStrokesCallback | None:
    """Get the current add_strokes callback."""
    return _add_strokes_callback


def get_workspace_dir_callback() -> WorkspaceDirCallback | None:
    """Get the current workspace directory callback."""
    return _get_workspace_dir_callback


def get_piece_title_callback() -> PieceTitleCallback | None:
    """Get the current piece title callback."""
    return _set_piece_title_callback


def get_canvas_dimensions() -> tuple[int, int]:
    """Get the current canvas dimensions."""
    return _canvas_width, _canvas_height


def image_content_from_png(png_bytes: bytes) -> dict[str, Any]:
    """Build MCP image content for a PNG payload."""
    return {
        "type": "image",
        "data": base64.standard_b64encode(png_bytes).decode("utf-8"),
        "mimeType": "image/png",
    }


def inject_canvas_image(content: list[dict[str, Any]]) -> None:
    """Inject current canvas image into response content if callback is set."""
    if _get_canvas_callback is None:
        return
    try:
        png_bytes = _get_canvas_callback()
        content.append(image_content_from_png(png_bytes))
    except Exception as e:
        logger.warning(f"Failed to get canvas image: {e}")
