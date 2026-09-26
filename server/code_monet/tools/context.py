"""Per-agent tool context: everything a drawing tool call may read or change.

One server process runs many users' agents concurrently. Each agent owns one
ToolContext and its tools are bound to it (`ToolSpec.bind`), so a tool call can
only reach the workspace, canvas, reference image, and finish gate of the agent
that issued it. There is deliberately no module-level tool state.
"""

from __future__ import annotations

import base64
import io
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path as FilePath
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import SdkMcpTool

from .quality_gate import QualityGateState

if TYPE_CHECKING:
    from code_monet.program_painting import PaintResult
    from code_monet.types import Path

logger = logging.getLogger(__name__)

DrawCallback = Callable[["list[Path]", bool], Awaitable[None]]
GetCanvasCallback = Callable[[], bytes]
AddStrokesCallback = Callable[["list[Path]"], Awaitable[None]]
PaintCallback = Callable[[], "Awaitable[PaintResult]"]

_REFERENCE_PROMPT_MAX_SIZE = 512


@dataclass
class ToolContext:
    """One agent's tool state.

    Turn bindings (`bind_turn`) connect the tools to the agent's workspace for the
    current turn. Piece state (finish gate, reference image) persists across turns
    until `reset_piece`.
    """

    # Turn bindings
    draw: DrawCallback | None = None
    get_canvas: GetCanvasCallback | None = None
    add_strokes: AddStrokesCallback | None = None
    paint: PaintCallback | None = None
    workspace_dir: str | None = None
    canvas_width: int = 800
    canvas_height: int = 600

    # Piece state
    gate: QualityGateState = field(default_factory=QualityGateState)
    reference_path: str | None = None

    def bind_turn(
        self,
        *,
        workspace_dir: str,
        canvas_width: int,
        canvas_height: int,
        get_canvas: GetCanvasCallback,
        add_strokes: AddStrokesCallback,
        draw: DrawCallback,
        paint: PaintCallback | None = None,
    ) -> None:
        """Connect the tools to this agent's workspace for a turn.

        Args:
            workspace_dir: The agent's workspace directory (imagine saves references here)
            canvas_width: Canvas width in pixels
            canvas_height: Canvas height in pixels
            get_canvas: Current canvas as image bytes (view_canvas, critique)
            add_strokes: Adds strokes to state before the tool returns
            draw: Collects drawn paths for animation (paths, done_flag)
            paint: Runs the painting program and publishes the version (paint mode)
        """
        self.workspace_dir = workspace_dir
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.get_canvas = get_canvas
        self.add_strokes = add_strokes
        self.draw = draw
        self.paint = paint

    def reset_piece(self) -> None:
        """Forget the finished/cleared piece's finish gate and reference image."""
        self.gate.reset()
        self.reference_path = None

    def active_reference_path(self) -> str | None:
        """Path of the latest reference image, if one exists on disk."""
        if self.reference_path is None or not FilePath(self.reference_path).is_file():
            return None
        return self.reference_path

    def active_reference_png(self) -> bytes | None:
        """Latest reference image as a prompt-sized PNG, or None."""
        path = self.active_reference_path()
        if path is None:
            return None
        try:
            from PIL import Image

            img = Image.open(path)
            img.thumbnail((_REFERENCE_PROMPT_MAX_SIZE, _REFERENCE_PROMPT_MAX_SIZE))
            buffer = io.BytesIO()
            img.convert("RGB").save(buffer, "PNG", optimize=True)
            return buffer.getvalue()
        except Exception as e:
            logger.warning(f"Failed to load reference image {path}: {e}")
            return None

    def inject_canvas_image(self, content: list[dict[str, Any]]) -> None:
        """Append the current canvas image to tool response content, if available."""
        if self.get_canvas is None:
            return
        try:
            content.append(image_content_from_png(self.get_canvas()))
        except Exception as e:
            logger.warning(f"Failed to get canvas image: {e}")


ToolHandler = Callable[[ToolContext, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolSpec:
    """A drawing tool's schema and handler, independent of any agent."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler

    def bind(self, ctx: ToolContext) -> SdkMcpTool[Any]:
        """This tool as an MCP tool that always acts on `ctx`."""
        handler = self.handler

        async def run(args: dict[str, Any]) -> dict[str, Any]:
            return await handler(ctx, args)

        return SdkMcpTool(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            handler=run,
        )


def image_mime_type(data: bytes) -> str:
    """Detect PNG vs JPEG from magic bytes (canvas images may be either)."""
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    return "image/png"


def image_content_from_png(image_bytes: bytes) -> dict[str, Any]:
    """Build MCP image content for a PNG or JPEG payload."""
    return {
        "type": "image",
        "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
        "mimeType": image_mime_type(image_bytes),
    }
