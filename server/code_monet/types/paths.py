"""Path model for drawable strokes."""

from typing import Any, Literal

from pydantic import BaseModel

from code_monet.types.brushes import BrushPreset, get_brush_preset
from code_monet.types.geometry import PathType, Point
from code_monet.types.styles import DrawingStyleConfig, DrawingStyleType, StrokeStyle


class Path(BaseModel):
    """A drawable path.

    Style properties (color, stroke_width, opacity, brush) are optional.
    When None, they're excluded from serialization and clients use style defaults.
    """

    type: PathType
    points: list[Point] = []  # Empty for SVG paths
    d: str | None = None  # SVG path d-string (for type=svg)
    author: Literal["agent", "human"] = "agent"

    # Style properties (optional - use style defaults if not set)
    color: str | None = None  # Hex color
    stroke_width: float | None = None  # Stroke width
    opacity: float | None = None  # 0-1 alpha
    fill: str | None = None  # Hex fill color for closed paths
    fill_opacity: float | None = None  # 0-1 fill alpha

    # Brush preset (paint mode only)
    brush: str | None = None  # Brush preset name (e.g., "oil_round", "watercolor")

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize path, excluding None values by default.

        This prevents sending null style properties to clients, which would
        otherwise be misinterpreted as explicit values instead of "use default".
        """
        # Default to exclude_none=True unless explicitly overridden
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)

    def get_brush_preset(self) -> BrushPreset | None:
        """Get the brush preset for this path, if any."""
        if self.brush:
            return get_brush_preset(self.brush)
        return None

    def get_effective_style(self, style_config: DrawingStyleConfig) -> StrokeStyle:
        """Get the effective style for this path, merging with defaults.

        Args:
            style_config: The active drawing style configuration

        Returns:
            Complete stroke style with all properties resolved
        """
        default = style_config.agent_stroke if self.author == "agent" else style_config.human_stroke

        # In plotter mode, always use defaults (ignore path-level styles)
        if style_config.type == DrawingStyleType.PLOTTER:
            return default

        # In paint mode, allow overrides
        return StrokeStyle(
            color=self.color if self.color and style_config.supports_color else default.color,
            stroke_width=(
                self.stroke_width
                if self.stroke_width is not None and style_config.supports_variable_width
                else default.stroke_width
            ),
            opacity=(
                self.opacity
                if self.opacity is not None and style_config.supports_opacity
                else default.opacity
            ),
            stroke_linecap=default.stroke_linecap,
            stroke_linejoin=default.stroke_linejoin,
        )
