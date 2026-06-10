"""WebSocket message types."""

from typing import Any, Literal

from pydantic import BaseModel

from code_monet.types.geometry import Point
from code_monet.types.paths import Path
from code_monet.types.state import GalleryEntry
from code_monet.types.styles import DrawingStyleConfig, DrawingStyleType

# Server -> Client messages


class HumanStrokeMessage(BaseModel):
    """Human user completed a stroke (broadcast to sync other clients)."""

    type: Literal["human_stroke"] = "human_stroke"
    path: Path


class PausedMessage(BaseModel):
    """Pause state change notification."""

    type: Literal["paused"] = "paused"
    paused: bool


class ClearMessage(BaseModel):
    """Canvas cleared."""

    type: Literal["clear"] = "clear"


class NewCanvasMessage(BaseModel):
    """New canvas created, old one saved to gallery."""

    type: Literal["new_canvas"] = "new_canvas"
    saved_id: str | None = None  # ID of saved canvas, None if was empty
    canvas_width: int = 800
    canvas_height: int = 600


class GalleryUpdateMessage(BaseModel):
    """Gallery was updated."""

    type: Literal["gallery_update"] = "gallery_update"
    canvases: list[GalleryEntry]


class LoadCanvasMessage(BaseModel):
    """Load a canvas from gallery."""

    type: Literal["load_canvas"] = "load_canvas"
    strokes: list[Path]
    piece_number: int
    canvas_width: int = 800
    canvas_height: int = 600
    drawing_style: DrawingStyleType = DrawingStyleType.PLOTTER
    style_config: DrawingStyleConfig | None = None


class ThinkingDeltaMessage(BaseModel):
    """Incremental thinking text (delta only, not accumulated)."""

    type: Literal["thinking_delta"] = "thinking_delta"
    text: str  # Only the new text since last message
    iteration: int = 1  # Which iteration (1-5)


class CodeExecutionMessage(BaseModel):
    """Code execution started or completed."""

    type: Literal["code_execution"] = "code_execution"
    status: Literal["started", "completed"]
    tool_name: str | None = None  # e.g., "draw_paths", "generate_svg", "view_canvas"
    tool_input: dict[str, Any] | None = None  # Tool input for context (e.g., path count, code)
    stdout: str | None = None
    stderr: str | None = None
    return_code: int | None = None
    iteration: int = 1


class ErrorMessage(BaseModel):
    """Error occurred during agent execution."""

    type: Literal["error"] = "error"
    message: str
    details: str | None = None


class PieceStateMessage(BaseModel):
    """Piece state update (count and completion status)."""

    type: Literal["piece_state"] = "piece_state"
    number: int
    completed: bool  # True if piece just finished


class IterationMessage(BaseModel):
    """Agent iteration update."""

    type: Literal["iteration"] = "iteration"
    current: int  # Current iteration number (1-5)
    max: int = 5  # Maximum iterations


class AgentStrokesReadyMessage(BaseModel):
    """Agent strokes are ready to be fetched via REST API."""

    type: Literal["agent_strokes_ready"] = "agent_strokes_ready"
    count: int  # Number of strokes ready
    batch_id: int  # For ordering/deduplication
    piece_number: int  # Canvas/piece number to prevent cross-canvas rendering


# Client -> Server messages


class ClientStrokeMessage(BaseModel):
    """Human stroke from client."""

    type: Literal["stroke"] = "stroke"
    points: list[Point]


class ClientNudgeMessage(BaseModel):
    """Human nudge from client."""

    type: Literal["nudge"] = "nudge"
    text: str


class ClientControlMessage(BaseModel):
    """Control message from client."""

    type: Literal["clear", "pause", "resume"]


class ClientNewCanvasMessage(BaseModel):
    """New canvas request from client."""

    type: Literal["new_canvas"] = "new_canvas"
    direction: str | None = None  # Optional direction for the agent
    drawing_style: DrawingStyleType | None = None  # Optional style for the new canvas
    canvas_width: int | None = None
    canvas_height: int | None = None


class ClientAnimationDoneMessage(BaseModel):
    """Client finished animating the current stroke batch."""

    type: Literal["animation_done"] = "animation_done"
    batch_id: int


# Union types for message routing

ServerMessage = (
    HumanStrokeMessage
    | ThinkingDeltaMessage
    | PausedMessage
    | ClearMessage
    | NewCanvasMessage
    | GalleryUpdateMessage
    | LoadCanvasMessage
    | CodeExecutionMessage
    | ErrorMessage
    | PieceStateMessage
    | IterationMessage
    | AgentStrokesReadyMessage
)

ClientMessage = (
    ClientStrokeMessage
    | ClientNudgeMessage
    | ClientControlMessage
    | ClientNewCanvasMessage
    | ClientAnimationDoneMessage
)


# Agent streaming events


class AgentPathsEvent(BaseModel):
    """Paths produced during agent turn - draw these immediately."""

    type: Literal["paths"] = "paths"
    paths: list[Path]


class AgentTurnComplete(BaseModel):
    """Agent turn completed."""

    type: Literal["turn_complete"] = "turn_complete"
    thinking: str
    done: bool  # True if piece is complete


AgentEvent = AgentPathsEvent | AgentTurnComplete
