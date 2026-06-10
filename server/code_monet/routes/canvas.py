"""Canvas state and rendering endpoints."""

from typing import Any
from xml.etree import ElementTree as ET

from fastapi import APIRouter
from fastapi.responses import Response

from code_monet.auth.dependencies import CurrentUser
from code_monet.canvas import render_path_to_svg_d
from code_monet.db import User
from code_monet.registry import workspace_registry
from code_monet.rendering import RenderOptions, render_strokes_async, render_workspace_async
from code_monet.types import DrawingStyleType, Path, get_style_config
from code_monet.workspace import WorkspaceState

router = APIRouter()


async def get_user_state(user: User) -> WorkspaceState:
    """Get or create workspace state for a user."""
    workspace = workspace_registry.get(user.id)
    if workspace:
        return workspace.state
    # User not connected via WebSocket yet - load state directly
    return await WorkspaceState.load_for_user(user.id)


async def render_strokes_to_png(
    strokes: list[Path],
    width: int = 800,
    height: int = 600,
    drawing_style: DrawingStyleType = DrawingStyleType.PLOTTER,
) -> bytes:
    """Render strokes to PNG (async, non-blocking)."""
    options = RenderOptions(
        width=width,
        height=height,
        drawing_style=drawing_style,
        output_format="bytes",
    )
    result = await render_strokes_async(strokes, options)
    assert isinstance(result, bytes)
    return result


async def render_user_png(state: WorkspaceState, highlight_human: bool = True) -> bytes:
    """Render user's canvas to PNG (async, non-blocking).

    Offloads rendering to thread pool to avoid blocking the event loop.
    """
    result = await render_workspace_async(state, highlight_human=highlight_human)
    assert isinstance(result, bytes)
    return result


@router.get("/state")
async def get_state(user: CurrentUser) -> dict[str, Any]:
    """Get current canvas state for authenticated user."""
    state = await get_user_state(user)
    return {
        "canvas": state.canvas.model_dump(),
        "status": state.status.value,
        "piece_number": state.piece_number,
    }


@router.get("/canvas.png")
async def get_canvas_png(user: CurrentUser) -> Response:
    """Get user's canvas as PNG image."""
    state = await get_user_state(user)
    return Response(content=await render_user_png(state), media_type="image/png")


@router.get("/canvas.svg")
async def get_canvas_svg(user: CurrentUser) -> Response:
    """Get user's canvas as SVG image."""
    state = await get_user_state(user)
    canvas = state.canvas

    svg = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": str(canvas.width),
            "height": str(canvas.height),
            "viewBox": f"0 0 {canvas.width} {canvas.height}",
        },
    )
    ET.SubElement(svg, "rect", {"width": "100%", "height": "100%", "fill": "#FFFFFF"})

    style_config = get_style_config(canvas.drawing_style)
    for path in canvas.strokes:
        d = render_path_to_svg_d(path)
        if d:
            effective_style = path.get_effective_style(style_config)
            fill = path.fill or "none"
            fill_opacity = (
                path.fill_opacity if path.fill_opacity is not None else effective_style.opacity
            )
            stroke = effective_style.color if effective_style.stroke_width > 0 else "none"
            ET.SubElement(
                svg,
                "path",
                {
                    "d": d,
                    "stroke": stroke,
                    "stroke-width": str(effective_style.stroke_width),
                    "fill": fill,
                    "fill-opacity": str(fill_opacity),
                    "stroke-opacity": str(effective_style.opacity),
                    "stroke-linecap": effective_style.stroke_linecap,
                    "stroke-linejoin": effective_style.stroke_linejoin,
                },
            )

    return Response(content=ET.tostring(svg, encoding="unicode"), media_type="image/svg+xml")
