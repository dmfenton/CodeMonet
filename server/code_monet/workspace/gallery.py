"""Gallery file operations."""

from __future__ import annotations

import json
import logging
from pathlib import Path as FilePath

import aiofiles
import aiofiles.os

from code_monet.types import DrawingStyleType, GalleryEntry, Path, SavedCanvas

logger = logging.getLogger(__name__)


def parse_drawing_style(style_str: str) -> DrawingStyleType:
    """Parse drawing style string with fallback to plotter."""
    try:
        return DrawingStyleType(style_str)
    except ValueError:
        return DrawingStyleType.PLOTTER


async def scan_gallery_entries(gallery_dir: FilePath) -> list[GalleryEntry]:
    """Scan gallery directory and return metadata entries.

    Args:
        gallery_dir: Path to user's gallery directory.

    Returns:
        List of GalleryEntry objects sorted by piece number.
    """
    if not await aiofiles.os.path.exists(gallery_dir):
        return []

    result = []
    for entry in await aiofiles.os.listdir(gallery_dir):
        if not entry.startswith("piece_") or not entry.endswith(".json"):
            continue

        piece_file = gallery_dir / entry
        try:
            async with aiofiles.open(piece_file) as f:
                data = json.loads(await f.read())

            piece_number = data.get("piece_number")
            if piece_number is None:
                continue

            piece_id = f"piece_{piece_number:06d}"
            result.append(
                GalleryEntry(
                    id=piece_id,
                    created_at=data.get("created_at", ""),
                    piece_number=piece_number,
                    stroke_count=len(data.get("strokes", [])),
                    width=data.get("width", 800),
                    height=data.get("height", 600),
                    drawing_style=parse_drawing_style(data.get("drawing_style", "plotter")),
                    title=data.get("title"),
                    thumbnail_token=piece_id,
                )
            )
        except (json.JSONDecodeError, OSError):
            continue

    result.sort(key=lambda p: p.piece_number)
    return result


async def scan_gallery_with_strokes(gallery_dir: FilePath) -> list[SavedCanvas]:
    """Scan gallery directory and return full canvas data including strokes.

    This loads all strokes for each piece - use sparingly.
    For listings, prefer scan_gallery_entries() which returns metadata only.

    Args:
        gallery_dir: Path to user's gallery directory.

    Returns:
        List of SavedCanvas objects sorted by piece number.
    """
    if not await aiofiles.os.path.exists(gallery_dir):
        return []

    pieces: list[SavedCanvas] = []
    for entry in await aiofiles.os.listdir(gallery_dir):
        if not entry.startswith("piece_") or not entry.endswith(".json"):
            continue

        piece_file = gallery_dir / entry
        try:
            async with aiofiles.open(piece_file) as f:
                data = json.loads(await f.read())

            piece_number = data.get("piece_number")
            if piece_number is None:
                logger.warning(f"Gallery file {entry} missing piece_number, skipping")
                continue

            pieces.append(
                SavedCanvas(
                    id=f"piece_{piece_number:06d}",
                    strokes=[Path.model_validate(s) for s in data.get("strokes", [])],
                    created_at=data.get("created_at", ""),
                    piece_number=piece_number,
                    width=data.get("width", 800),
                    height=data.get("height", 600),
                    drawing_style=parse_drawing_style(data.get("drawing_style", "plotter")),
                    title=data.get("title"),
                )
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Skipping corrupted gallery file {entry}: {e}")
            continue

    pieces.sort(key=lambda p: p.piece_number)
    return pieces


async def load_gallery_piece(
    gallery_dir: FilePath, piece_number: int
) -> tuple[list[Path], DrawingStyleType, int, int] | None:
    """Load strokes, drawing style, and dimensions from a gallery piece.

    Args:
        gallery_dir: Path to user's gallery directory.
        piece_number: Piece number to load.

    Returns:
        Tuple of (strokes, drawing_style, width, height) or None if not found.
    """
    # Try both 3-digit and 6-digit formats for backwards compatibility
    for fmt in [f"piece_{piece_number:06d}.json", f"piece_{piece_number:03d}.json"]:
        piece_file = gallery_dir / fmt
        if await aiofiles.os.path.exists(piece_file):
            try:
                async with aiofiles.open(piece_file) as f:
                    data = json.loads(await f.read())

                strokes = [Path.model_validate(s) for s in data.get("strokes", [])]
                drawing_style = parse_drawing_style(data.get("drawing_style", "plotter"))
                return (
                    strokes,
                    drawing_style,
                    data.get("width", 800),
                    data.get("height", 600),
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load gallery piece {piece_number}: {e}")
                return None

    return None
