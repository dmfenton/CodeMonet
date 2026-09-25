"""Tool callback setup for the drawing agent."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from code_monet.tools import (
    set_add_strokes_callback,
    set_canvas_dimensions,
    set_draw_callback,
    set_get_canvas_callback,
    set_paint_callback,
    set_piece_title_callback,
    set_workspace_dir_callback,
)

if TYPE_CHECKING:
    from code_monet.program_painting import PaintResult
    from code_monet.types import Path
    from code_monet.workspace import WorkspaceState


def setup_tool_callbacks(
    state: WorkspaceState,
    get_canvas_png: Callable[[], bytes],
    canvas_width: int,
    canvas_height: int,
    on_paths_collected: Callable[[list[Path], bool], Coroutine[Any, Any, None]],
    run_paint: Callable[[], Coroutine[Any, Any, PaintResult]] | None = None,
) -> None:
    """Set up all tool callbacks for an agent turn.

    Args:
        state: The workspace state
        get_canvas_png: Callback to get current canvas as PNG bytes
        canvas_width: Canvas width in pixels
        canvas_height: Canvas height in pixels
        on_paths_collected: Callback when paths are drawn (paths, done_flag)
        run_paint: Runs the painting program and publishes the version (paint mode)
    """
    set_paint_callback(run_paint)

    # Set up draw callback to collect paths for the PostToolUse hook (animation)
    set_draw_callback(on_paths_collected)

    # Set up canvas callback for view_canvas tool
    set_get_canvas_callback(get_canvas_png)

    # Set up add_strokes callback to update state immediately (before tool returns)
    # This allows the canvas image to include new strokes in the tool result
    set_add_strokes_callback(state.add_strokes)

    # Set up workspace directory callback for generate_image tool
    def get_workspace_dir() -> str:
        return state.workspace_dir

    set_workspace_dir_callback(get_workspace_dir)

    # Set up piece title callback for name_piece tool
    async def set_piece_title(title: str) -> None:
        state.current_piece_title = title
        await state.save()

    set_piece_title_callback(set_piece_title)

    # Set canvas dimensions
    set_canvas_dimensions(canvas_width, canvas_height)
