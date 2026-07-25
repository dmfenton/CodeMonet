"""Drawing style definitions."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class DrawingStyleType(StrEnum):
    """Drawing style modes."""

    PLOTTER = "plotter"  # Monochrome pen plotter style (black lines)
    PAINT = "paint"  # Full color painting style


class StrokeStyle(BaseModel):
    """Style properties for a stroke.

    Used both as path-level style and as style defaults.
    """

    color: str = "#1a1a2e"  # Hex color (default: dark)
    stroke_width: float = 2.5  # Stroke width in canvas units
    opacity: float = 1.0  # 0-1 alpha value
    stroke_linecap: Literal["round", "butt", "square"] = "round"
    stroke_linejoin: Literal["round", "miter", "bevel"] = "round"


class DrawingStyleConfig(BaseModel):
    """Configuration for a drawing style.

    Defines the capabilities and defaults for each style mode.
    """

    type: DrawingStyleType
    name: str  # Human-readable name
    description: str  # For agent prompt

    # Default styles
    agent_stroke: StrokeStyle  # Default style for agent strokes
    human_stroke: StrokeStyle  # Default style for human strokes

    # Capabilities
    supports_color: bool = False  # Can paths have custom colors?
    supports_variable_width: bool = False  # Can paths have custom widths?
    supports_opacity: bool = False  # Can paths have custom opacity?

    # Color palette (if restricted, None = any color)
    color_palette: list[str] | None = None


# Pre-defined drawing styles
PLOTTER_STYLE = DrawingStyleConfig(
    type=DrawingStyleType.PLOTTER,
    name="Plotter",
    description="Monochrome pen plotter style with crisp black lines",
    agent_stroke=StrokeStyle(
        color="#1a1a2e",  # Dark
        stroke_width=2.5,
        opacity=1.0,
    ),
    human_stroke=StrokeStyle(
        color="#0066CC",  # Blue for visibility
        stroke_width=2.5,
        opacity=1.0,
    ),
    supports_color=False,
    supports_variable_width=False,
    supports_opacity=False,
)

PAINT_STYLE = DrawingStyleConfig(
    type=DrawingStyleType.PAINT,
    name="Paint",
    description="Full color painting style with expressive brush strokes",
    agent_stroke=StrokeStyle(
        color="#1a1a2e",  # Default dark, but can be overridden
        stroke_width=8.0,  # Thicker for brush effect
        opacity=0.85,
    ),
    human_stroke=StrokeStyle(
        color="#e94560",  # Rose
        stroke_width=8.0,  # Thicker for brush effect
        opacity=0.85,
    ),
    supports_color=True,
    supports_variable_width=True,
    supports_opacity=True,
    # Curated color palette for the agent
    color_palette=[
        "#1a1a2e",  # Dark (near black)
        "#e94560",  # Rose/crimson
        "#7b68ee",  # Violet
        "#4ecdc4",  # Teal
        "#ffd93d",  # Gold
        "#ff6b6b",  # Coral
        "#4ade80",  # Green
        "#3b82f6",  # Blue
        "#f97316",  # Orange
        "#a855f7",  # Purple
        "#ffffff",  # White
    ],
)

# Style registry
DRAWING_STYLES: dict[DrawingStyleType, DrawingStyleConfig] = {
    DrawingStyleType.PLOTTER: PLOTTER_STYLE,
    DrawingStyleType.PAINT: PAINT_STYLE,
}


def get_style_config(style_type: DrawingStyleType) -> DrawingStyleConfig:
    """Get the configuration for a drawing style."""
    return DRAWING_STYLES[style_type]
