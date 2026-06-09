"""Stroke queue operations."""

from __future__ import annotations

import logging

from code_monet.interpolation import interpolate_path
from code_monet.types import Path, PendingStrokeDict

logger = logging.getLogger(__name__)


def interpolate_paths_to_pending(
    paths: list[Path],
    batch_id: int,
    steps_per_unit: float,
) -> tuple[list[PendingStrokeDict], int]:
    """Interpolate paths and convert to pending stroke format.

    Args:
        paths: List of paths to interpolate.
        batch_id: Batch ID for these strokes.
        steps_per_unit: Interpolation density (from settings).

    Returns:
        Tuple of (pending_strokes, total_point_count).
    """
    pending: list[PendingStrokeDict] = []
    total_points = 0

    for path in paths:
        points = interpolate_path(path, steps_per_unit)
        total_points += len(points)
        pending.append(
            {
                "batch_id": batch_id,
                "path": path.model_dump(),
                "points": [{"x": p.x, "y": p.y} for p in points],
            }
        )

    return pending, total_points


def enforce_pending_limit(
    pending_strokes: list[PendingStrokeDict],
    new_count: int,
    max_pending: int,
    user_id: str,
) -> list[PendingStrokeDict]:
    """Enforce maximum pending strokes limit by dropping oldest.

    Args:
        pending_strokes: Current pending strokes list.
        new_count: Number of new strokes being added.
        max_pending: Maximum allowed pending strokes.
        user_id: User ID for logging.

    Returns:
        Updated pending strokes list with oldest dropped if needed.
    """
    overflow = len(pending_strokes) + new_count - max_pending
    if overflow > 0:
        logger.warning(
            f"User {user_id}: pending strokes limit reached ({max_pending}), "
            f"dropping {overflow} oldest"
        )
        return pending_strokes[overflow:]
    return pending_strokes
