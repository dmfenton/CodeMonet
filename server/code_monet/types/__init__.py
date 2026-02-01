"""Type definitions for the drawing agent.

This package contains all type definitions organized into focused modules:
- geometry: Core geometry types (Point, PathType)
- brushes: Brush preset definitions
- styles: Drawing style configurations
- paths: Path model for drawable strokes
- state: Application state models
- messages: WebSocket message types
"""

# Re-export all public types for backwards compatibility
from code_monet.types.brushes import (
    BRUSH_PRESETS,
    DEFAULT_BRUSH,
    BrushPreset,
    get_brush_preset,
)
from code_monet.types.geometry import (
    PathType,
    PendingStrokeDict,
    Point,
    PointDict,
    clamp_value,
)
from code_monet.types.messages import (
    AgentEvent,
    AgentPathsEvent,
    AgentStrokesReadyMessage,
    AgentTurnComplete,
    ClearMessage,
    ClientControlMessage,
    ClientMessage,
    ClientNewCanvasMessage,
    ClientNudgeMessage,
    ClientStrokeMessage,
    CodeExecutionMessage,
    ErrorMessage,
    GalleryUpdateMessage,
    HumanStrokeMessage,
    IterationMessage,
    LoadCanvasMessage,
    NewCanvasMessage,
    PausedMessage,
    PieceStateMessage,
    ServerMessage,
    ThinkingDeltaMessage,
)
from code_monet.types.paths import Path
from code_monet.types.state import (
    AgentState,
    AgentStatus,
    AppState,
    CanvasState,
    GalleryEntry,
    GalleryState,
    PauseReason,
    SavedCanvas,
)
from code_monet.types.styles import (
    DRAWING_STYLES,
    PAINT_STYLE,
    PLOTTER_STYLE,
    DrawingStyleConfig,
    DrawingStyleType,
    StrokeStyle,
    get_style_config,
)

__all__ = [
    # Geometry
    "PathType",
    "PendingStrokeDict",
    "Point",
    "PointDict",
    "clamp_value",
    # Brushes
    "BRUSH_PRESETS",
    "BrushPreset",
    "DEFAULT_BRUSH",
    "get_brush_preset",
    # Styles
    "DRAWING_STYLES",
    "DrawingStyleConfig",
    "DrawingStyleType",
    "PAINT_STYLE",
    "PLOTTER_STYLE",
    "StrokeStyle",
    "get_style_config",
    # Paths
    "Path",
    # State
    "AgentState",
    "AgentStatus",
    "AppState",
    "CanvasState",
    "GalleryEntry",
    "GalleryState",
    "PauseReason",
    "SavedCanvas",
    # Messages
    "AgentEvent",
    "AgentPathsEvent",
    "AgentStrokesReadyMessage",
    "AgentTurnComplete",
    "ClearMessage",
    "ClientControlMessage",
    "ClientMessage",
    "ClientNewCanvasMessage",
    "ClientNudgeMessage",
    "ClientStrokeMessage",
    "CodeExecutionMessage",
    "ErrorMessage",
    "GalleryUpdateMessage",
    "HumanStrokeMessage",
    "IterationMessage",
    "LoadCanvasMessage",
    "NewCanvasMessage",
    "PausedMessage",
    "PieceStateMessage",
    "ServerMessage",
    "ThinkingDeltaMessage",
]
