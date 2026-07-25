"""Core geometry types."""

from enum import StrEnum
from typing import Any, TypedDict

from pydantic import BaseModel


class PointDict(TypedDict):
    """Dictionary representation of a point."""

    x: float
    y: float


class PendingStrokeDict(TypedDict):
    """Dictionary representation of a pending stroke for animation."""

    batch_id: int
    path: dict[str, Any]  # Serialized Path model
    points: list[PointDict]


class Point(BaseModel):
    """A 2D point."""

    x: float
    y: float


class PathType(StrEnum):
    """Types of drawable paths."""

    LINE = "line"
    QUADRATIC = "quadratic"
    CUBIC = "cubic"
    POLYLINE = "polyline"
    SVG = "svg"  # Raw SVG path d-string


def clamp_value(value: float, low: float, high: float) -> float:
    """Clamp a value to a range [low, high]."""
    return max(low, min(high, value))
