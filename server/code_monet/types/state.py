"""Application state models."""

from enum import StrEnum

from pydantic import BaseModel

from code_monet.types.paths import Path
from code_monet.types.styles import DrawingStyleType


class AgentStatus(StrEnum):
    """Agent status values."""

    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"  # Running code in sandbox
    DRAWING = "drawing"
    PAUSED = "paused"
    ERROR = "error"


class PauseReason(StrEnum):
    """Reason why the agent is paused.

    Used to determine whether to auto-resume on reconnect:
    - NONE: Agent is not paused (or was never paused)
    - USER: User explicitly paused - don't auto-resume
    - DISCONNECT: System paused due to no clients - auto-resume on reconnect
    - ERROR: System paused due to unrecoverable error - don't auto-resume
    """

    NONE = "none"
    USER = "user"
    DISCONNECT = "disconnect"
    ERROR = "error"


class CanvasState(BaseModel):
    """Canvas state."""

    width: int = 800
    height: int = 600
    strokes: list[Path] = []
    drawing_style: DrawingStyleType = DrawingStyleType.PLOTTER  # Active style


class AgentState(BaseModel):
    """Agent state."""

    status: AgentStatus = AgentStatus.IDLE
    monologue: str = ""
    notes: str = ""
    piece_number: int = 0


class GalleryEntry(BaseModel):
    """Gallery entry for listings (metadata only, no strokes)."""

    id: str
    created_at: str  # ISO timestamp
    piece_number: int
    stroke_count: int
    width: int = 800
    height: int = 600
    drawing_style: DrawingStyleType = DrawingStyleType.PLOTTER
    title: str | None = None  # Piece title (set by agent via name_piece tool)
    thumbnail_token: str | None = None  # Token for thumbnail URL (same as id)


class SavedCanvas(BaseModel):
    """Full saved canvas with strokes (for loading)."""

    id: str
    strokes: list[Path]
    created_at: str  # ISO timestamp
    piece_number: int
    width: int = 800
    height: int = 600
    drawing_style: DrawingStyleType = DrawingStyleType.PLOTTER
    title: str | None = None  # Piece title (set by agent via name_piece tool)

    @property
    def num_strokes(self) -> int:
        """Get stroke count."""
        return len(self.strokes)

    def to_gallery_entry(self) -> GalleryEntry:
        """Convert to gallery entry (metadata only)."""
        return GalleryEntry(
            id=self.id,
            created_at=self.created_at,
            piece_number=self.piece_number,
            stroke_count=self.num_strokes,
            width=self.width,
            height=self.height,
            drawing_style=self.drawing_style,
            title=self.title,
            thumbnail_token=self.id,  # Use id as token for thumbnail URL
        )


class GalleryState(BaseModel):
    """Gallery of saved canvases."""

    canvases: list[SavedCanvas] = []


class AppState(BaseModel):
    """Full application state."""

    canvas: CanvasState = CanvasState()
    agent: AgentState = AgentState()
    gallery: GalleryState = GalleryState()
