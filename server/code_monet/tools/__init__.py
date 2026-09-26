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
- paint: Run the painting program (paint mode)

Each tool is a `ToolSpec` whose handler takes the calling agent's `ToolContext`;
`create_drawing_server(ctx)` binds every tool to one agent's context.
"""

from claude_agent_sdk import create_sdk_mcp_server
from claude_agent_sdk.types import McpSdkServerConfig

from .context import ToolContext, ToolHandler, ToolSpec
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
from .paint import handle_paint, paint
from .path_parsing import parse_path_data
from .quality_gate import QualityGateState
from .signature import (
    _generate_signature_paths,
    _transform_svg_path,
    handle_sign_canvas,
    sign_canvas,
)
from .svg_generation import generate_svg, handle_generate_svg

DRAWING_TOOLS: tuple[ToolSpec, ...] = (
    draw_paths,
    mark_piece_done,
    generate_svg,
    view_canvas,
    critique_canvas,
    imagine,
    sign_canvas,
    name_piece,
    paint,
)


def create_drawing_server(ctx: ToolContext) -> McpSdkServerConfig:
    """Create the MCP server whose tools all act on one agent's context."""
    return create_sdk_mcp_server(
        name="drawing",
        version="1.0.0",
        tools=[spec.bind(ctx) for spec in DRAWING_TOOLS],
    )


__all__ = [
    # Server factory and per-agent context
    "create_drawing_server",
    "DRAWING_TOOLS",
    "QualityGateState",
    "ToolContext",
    "ToolHandler",
    "ToolSpec",
    # Path parsing
    "parse_path_data",
    # Handlers (for testing and the OpenAI backend)
    "handle_draw_paths",
    "handle_mark_piece_done",
    "handle_view_canvas",
    "handle_critique_canvas",
    "handle_generate_svg",
    "handle_imagine",
    "handle_sign_canvas",
    "handle_name_piece",
    "handle_paint",
    # Signature helpers (for testing)
    "_generate_signature_paths",
    "_transform_svg_path",
    # Tool specs
    "draw_paths",
    "mark_piece_done",
    "generate_svg",
    "view_canvas",
    "critique_canvas",
    "imagine",
    "sign_canvas",
    "name_piece",
    "paint",
]
