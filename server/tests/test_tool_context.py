"""Tests for the per-agent ToolContext and ToolSpec binding."""

import io
from pathlib import Path as FilePath
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from code_monet.program_painting import PaintFailure, PaintResult
from code_monet.tools import (
    DRAWING_TOOLS,
    ToolContext,
    ToolSpec,
    create_drawing_server,
    handle_draw_paths,
)
from code_monet.types import Path


def _bind(ctx: ToolContext, **overrides: Any) -> None:
    bindings: dict[str, Any] = {
        "workspace_dir": "/ws",
        "canvas_width": 800,
        "canvas_height": 600,
        "get_canvas": MagicMock(return_value=b"png"),
        "add_strokes": AsyncMock(),
        "draw": AsyncMock(),
    }
    ctx.bind_turn(**{**bindings, **overrides})


def test_bind_turn_sets_every_turn_binding() -> None:
    ctx = ToolContext()
    get_canvas = MagicMock(return_value=b"png")
    add_strokes = AsyncMock()
    draw = AsyncMock()

    async def paint() -> PaintResult:
        return PaintFailure(error="x", seconds=0.0)

    ctx.bind_turn(
        workspace_dir="/custom/workspace",
        canvas_width=1024,
        canvas_height=768,
        get_canvas=get_canvas,
        add_strokes=add_strokes,
        draw=draw,
        paint=paint,
    )

    assert ctx.workspace_dir == "/custom/workspace"
    assert (ctx.canvas_width, ctx.canvas_height) == (1024, 768)
    assert ctx.get_canvas is get_canvas
    assert ctx.add_strokes is add_strokes
    assert ctx.draw is draw
    assert ctx.paint is paint


def test_rebinding_without_paint_clears_previous_paint_binding() -> None:
    ctx = ToolContext()
    _bind(ctx, paint=AsyncMock())

    _bind(ctx)

    assert ctx.paint is None


def test_turn_bindings_do_not_touch_piece_state(tmp_path: FilePath) -> None:
    ctx = ToolContext()
    ctx.gate.record_critique_result("VERDICT: FAIL\nFINDINGS:\n- mud")
    ctx.reference_path = str(tmp_path / "ref.png")

    _bind(ctx)

    assert ctx.gate.is_blocked()
    assert ctx.reference_path == str(tmp_path / "ref.png")


def test_reset_piece_clears_only_its_own_context(tmp_path: FilePath) -> None:
    reference = tmp_path / "ref.png"
    Image.new("RGB", (1024, 1024), "#336699").save(reference)
    ctx_a, ctx_b = ToolContext(), ToolContext()
    for ctx in (ctx_a, ctx_b):
        ctx.gate.record_critique_result("VERDICT: FAIL\nFINDINGS:\n- mud")
        ctx.reference_path = str(reference)

    ctx_a.reset_piece()

    assert not ctx_a.gate.is_blocked()
    assert ctx_a.gate.critique_history() == []
    assert ctx_a.active_reference_png() is None
    assert ctx_b.gate.is_blocked()
    reference_png = ctx_b.active_reference_png()
    assert reference_png is not None
    with Image.open(io.BytesIO(reference_png)) as thumb:
        assert max(thumb.size) == 512


def test_active_reference_ignores_missing_file(tmp_path: FilePath) -> None:
    ctx = ToolContext(reference_path=str(tmp_path / "gone.png"))

    assert ctx.active_reference_path() is None
    assert ctx.active_reference_png() is None


@pytest.mark.asyncio
async def test_tool_spec_bind_passes_its_context() -> None:
    seen: list[ToolContext] = []

    async def handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        seen.append(ctx)
        return {"content": [{"type": "text", "text": str(args)}]}

    spec = ToolSpec("probe", "Probe tool", {"type": "object", "properties": {}}, handler)
    ctx_a, ctx_b = ToolContext(), ToolContext()
    tool_a, tool_b = spec.bind(ctx_a), spec.bind(ctx_b)

    await tool_b.handler({})
    await tool_a.handler({})

    assert seen == [ctx_b, ctx_a]
    assert (tool_a.name, tool_a.description, tool_a.input_schema) == (
        spec.name,
        spec.description,
        spec.input_schema,
    )


def test_drawing_tools_keep_their_names() -> None:
    assert [spec.name for spec in DRAWING_TOOLS] == [
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


def test_each_server_is_bound_to_its_own_context() -> None:
    server_a = create_drawing_server(ToolContext())
    server_b = create_drawing_server(ToolContext())

    assert server_a["name"] == server_b["name"] == "drawing"
    assert server_a["instance"] is not server_b["instance"]


@pytest.mark.asyncio
async def test_draw_paths_uses_the_bound_context_canvas_bounds() -> None:
    small, large = ToolContext(), ToolContext()
    small_strokes: list[Path] = []
    large_strokes: list[Path] = []

    async def add_small(paths: list[Path]) -> None:
        small_strokes.extend(paths)

    async def add_large(paths: list[Path]) -> None:
        large_strokes.extend(paths)

    _bind(small, canvas_width=100, canvas_height=100, add_strokes=add_small)
    _bind(large, canvas_width=1000, canvas_height=1000, add_strokes=add_large)
    line = {"type": "line", "points": [{"x": 10, "y": 10}, {"x": 900, "y": 900}]}

    await handle_draw_paths(small, {"paths": [line]})
    await handle_draw_paths(large, {"paths": [line]})

    assert max(p.x for p in small_strokes[0].points) <= 100
    assert max(p.x for p in large_strokes[0].points) == 900
