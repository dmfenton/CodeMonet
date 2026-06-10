"""MCP tools for the drawing agent.

This package provides all drawing tools used by the agent:
- draw_paths: Draw paths on the canvas
- mark_piece_done: Signal piece completion
- generate_svg: Generate paths via Python code
- view_canvas: View current canvas state
- critique_canvas: Strict visual finish gate
- imagine: Generate AI reference images
- sign_canvas: Add artist signature
- name_piece: Title the artwork
"""

from claude_agent_sdk import create_sdk_mcp_server

from .callbacks import inject_canvas_image as _inject_canvas_image
from .callbacks import (
    set_add_strokes_callback,
    set_canvas_dimensions,
    set_draw_callback,
    set_get_canvas_callback,
    set_piece_title_callback,
    set_workspace_dir_callback,
)
from .critique import critique_canvas, handle_critique_canvas
from .drawing import (
    draw_paths,
    handle_draw_paths,
    handle_mark_piece_done,
    handle_view_canvas,
    mark_piece_done,
    view_canvas,
)
from .image_generation import handle_imagine, imagine
from .naming import handle_name_piece, name_piece
from .path_parsing import parse_path_data
from .quality_gate import (
    consume_mark_piece_done_accepted,
    get_quality_gate_snapshot,
    is_finish_gate_blocked,
    quality_gate_prompt_context,
    record_critique_result,
    reset_quality_gate,
)
from .signature import (
    _generate_signature_paths,
    _transform_svg_path,
    handle_sign_canvas,
    sign_canvas,
)
from .svg_generation import generate_svg, handle_generate_svg


def create_drawing_server():
    """Create the MCP server with drawing tools."""
    return create_sdk_mcp_server(
        name="drawing",
        version="1.0.0",
        tools=[
            draw_paths,
            mark_piece_done,
            generate_svg,
            view_canvas,
            critique_canvas,
            imagine,
            sign_canvas,
            name_piece,
        ],
    )


__all__ = [
    # Server factory
    "create_drawing_server",
    # Callbacks
    "set_draw_callback",
    "set_get_canvas_callback",
    "set_add_strokes_callback",
    "set_workspace_dir_callback",
    "set_piece_title_callback",
    "set_canvas_dimensions",
    "_inject_canvas_image",
    # Path parsing
    "parse_path_data",
    "consume_mark_piece_done_accepted",
    "get_quality_gate_snapshot",
    "is_finish_gate_blocked",
    "quality_gate_prompt_context",
    "record_critique_result",
    "reset_quality_gate",
    # Drawing handlers (for testing)
    "handle_draw_paths",
    "handle_mark_piece_done",
    "handle_view_canvas",
    "handle_critique_canvas",
    "handle_generate_svg",
    "handle_imagine",
    "handle_sign_canvas",
    "handle_name_piece",
    # Signature helpers (for testing)
    "_generate_signature_paths",
    "_transform_svg_path",
    # Tool functions
    "draw_paths",
    "mark_piece_done",
    "generate_svg",
    "view_canvas",
    "critique_canvas",
    "imagine",
    "sign_canvas",
    "name_piece",
]
