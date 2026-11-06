"""Gallery file operations."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
import weakref
from pathlib import Path as FilePath
from typing import Any, TypedDict

import aiofiles
import aiofiles.os

from code_monet.rendering import RenderOptions, render_strokes_async
from code_monet.types import DrawingStyleType, GalleryEntry, PaintingVersion, Path, SavedCanvas
from code_monet.workspace.assets import version_asset

logger = logging.getLogger(__name__)

# What a malformed gallery record raises when read (pydantic's ValidationError
# and json.JSONDecodeError are ValueErrors).
_MALFORMED = (ValueError, TypeError, AttributeError)


class PieceDetailFields(TypedDict):
    """Piece metadata shared by the owner and public piece detail payloads."""

    title: str | None
    prompt: str | None
    stroke_count: int
    versions: list[dict[str, Any]]  # Serialized PaintingVersionRef, oldest first


def gallery_version_record(version: PaintingVersion) -> dict[str, Any]:
    """A painting version as stored in gallery piece JSON (piece_number is the piece's)."""
    return version.model_dump(exclude={"piece_number"})


def piece_versions(data: dict[str, Any]) -> list[PaintingVersion]:
    """Rendered versions of a raster gallery piece, oldest first.

    Pieces saved before version history was recorded carry only the final
    `image_token`; they read as a single version with unknown stages and ops.
    """
    piece_number = data.get("piece_number", 0)
    stored = data.get("versions")
    if isinstance(stored, list) and stored:
        try:
            return [
                PaintingVersion.model_validate({**v, "piece_number": piece_number}) for v in stored
            ]
        except _MALFORMED as e:
            logger.warning(f"Piece {piece_number}: malformed versions, using final image: {e}")
    return _final_image_version(data, piece_number)


def _final_image_version(data: dict[str, Any], piece_number: Any) -> list[PaintingVersion]:
    """The piece's final image as its only version (unknown stages and ops)."""
    token = data.get("image_token")
    if not isinstance(token, str):
        return []
    try:
        return [
            PaintingVersion(
                piece_number=piece_number,
                version=1,
                token=token,
                image_width=data.get("image_width", 0),
                image_height=data.get("image_height", 0),
                created_at=data.get("created_at", ""),
            )
        ]
    except _MALFORMED as e:
        logger.warning(f"Piece {piece_number}: malformed final image record: {e}")
        return []


def piece_stroke_count(data: dict[str, Any]) -> int:
    """Marks in the finished picture.

    Every painting version re-renders the whole program, so a raster piece's
    count is its final version's ops; vector pieces count their strokes.
    """
    versions = data.get("versions")
    if isinstance(versions, list) and versions and isinstance(versions[-1], dict):
        ops = versions[-1].get("ops")
        if isinstance(ops, int):
            return ops
    strokes = data.get("strokes")
    return len(strokes) if isinstance(strokes, list) else 0


def piece_detail_fields(data: dict[str, Any], user_id: str, *, raster: bool) -> PieceDetailFields:
    """Title, prompt, stroke count, and (raster only) version refs for a piece payload."""
    versions = piece_versions(data) if raster else []
    return PieceDetailFields(
        title=data.get("title"),
        prompt=data.get("prompt"),
        stroke_count=piece_stroke_count(data),
        versions=[v.ref(user_id).model_dump() for v in versions],
    )


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
        metadata_file = piece_file.with_suffix(".meta")
        try:
            if await aiofiles.os.path.exists(metadata_file):
                piece_stat = await aiofiles.os.stat(piece_file)
                metadata_stat = await aiofiles.os.stat(metadata_file)
                if metadata_stat.st_mtime_ns >= piece_stat.st_mtime_ns:
                    async with aiofiles.open(metadata_file) as f:
                        try:
                            result.append(GalleryEntry.model_validate_json(await f.read()))
                            continue
                        except ValueError:
                            logger.warning(
                                "Rebuilding malformed gallery metadata %s", metadata_file
                            )

            async with aiofiles.open(piece_file) as f:
                data = json.loads(await f.read())

            piece_number = data.get("piece_number")
            if piece_number is None:
                continue

            piece_id = f"piece_{piece_number:06d}"
            gallery_entry = GalleryEntry(
                id=piece_id,
                created_at=data.get("created_at", ""),
                piece_number=piece_number,
                stroke_count=piece_stroke_count(data),
                width=data.get("width", 800),
                height=data.get("height", 600),
                drawing_style=parse_drawing_style(data.get("drawing_style", "plotter")),
                title=data.get("title"),
                thumbnail_token=piece_id,
                format=data.get("format", "strokes"),
            )
            result.append(gallery_entry)
            temporary_file = metadata_file.with_name(f"{metadata_file.name}.{uuid.uuid4().hex}.tmp")
            try:
                async with aiofiles.open(temporary_file, "w") as f:
                    await f.write(gallery_entry.model_dump_json())
                await aiofiles.os.replace(temporary_file, metadata_file)
            finally:
                if await aiofiles.os.path.exists(temporary_file):
                    await aiofiles.os.remove(temporary_file)
        except (OSError, *_MALFORMED) as e:
            logger.warning(f"Skipping unreadable gallery file {entry}: {e}")
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
        except (KeyError, *_MALFORMED) as e:
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

                return parse_gallery_piece(data)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load gallery piece {piece_number}: {e}")
                return None

    return None


def parse_gallery_piece(
    data: dict[str, Any],
) -> tuple[list[Path], DrawingStyleType, int, int]:
    """(strokes, drawing_style, width, height) from gallery piece JSON."""
    return (
        [Path.model_validate(s) for s in data.get("strokes", [])],
        parse_drawing_style(data.get("drawing_style", "plotter")),
        data.get("width", 800),
        data.get("height", 600),
    )


async def read_gallery_piece_json(
    gallery_dir: FilePath, piece_number: int
) -> dict[str, Any] | None:
    """Raw gallery piece JSON (6- or 3-digit filename), or None if missing/corrupt."""
    for fmt in [f"piece_{piece_number:06d}.json", f"piece_{piece_number:03d}.json"]:
        piece_file = gallery_dir / fmt
        if await aiofiles.os.path.exists(piece_file):
            try:
                async with aiofiles.open(piece_file) as f:
                    data: dict[str, Any] = json.loads(await f.read())
                return data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read gallery piece {piece_number}: {e}")
                return None
    return None


_PIECE_ID_PATTERN = re.compile(r"piece_([0-9]+)")
THUMBNAIL_MAX_SIDE = 640

# One lock per (user dir, piece), shared by every WorkspaceState instance and
# the public route, so a resave and a thumbnail render never interleave and
# concurrent first requests render once. Weak values drop idle locks.
_thumbnail_locks: weakref.WeakValueDictionary[tuple[str, int], asyncio.Lock] = (
    weakref.WeakValueDictionary()
)


def parse_piece_id(piece_id: str) -> int | None:
    """Piece number from an id like "piece_000012", or None if malformed."""
    match = _PIECE_ID_PATTERN.fullmatch(piece_id)
    return int(match.group(1)) if match else None


def gallery_thumbnail_lock(user_dir: FilePath, piece_number: int) -> asyncio.Lock:
    """The lock guarding a piece's JSON rewrite and its thumbnail sidecar."""
    key = (str(user_dir.resolve()), piece_number)
    lock = _thumbnail_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _thumbnail_locks[key] = lock
    return lock


async def gallery_thumbnail(user_dir: FilePath, piece_number: int) -> bytes | None:
    """Small persisted thumbnail for a gallery piece, rendered on first use.

    The thumbnail is re-rendered when the piece JSON is newer than it.
    """
    async with gallery_thumbnail_lock(user_dir, piece_number):
        return await _gallery_thumbnail_unlocked(user_dir, piece_number)


async def _gallery_thumbnail_unlocked(user_dir: FilePath, piece_number: int) -> bytes | None:
    gallery_dir = user_dir / "gallery"
    data_path = gallery_dir / f"piece_{piece_number:06d}.json"
    if not await aiofiles.os.path.exists(data_path):
        data_path = gallery_dir / f"piece_{piece_number:03d}.json"
    if not await aiofiles.os.path.exists(data_path):
        return None
    thumbnail_path = gallery_dir / f"piece_{piece_number:06d}.thumb.png"
    if await aiofiles.os.path.exists(thumbnail_path):
        thumbnail_stat, data_stat = await asyncio.gather(
            aiofiles.os.stat(thumbnail_path), aiofiles.os.stat(data_path)
        )
        if thumbnail_stat.st_mtime_ns >= data_stat.st_mtime_ns:
            async with aiofiles.open(thumbnail_path, "rb") as thumbnail_file:
                return await thumbnail_file.read()

    data = await read_gallery_piece_json(gallery_dir, piece_number)
    if data is None:
        return None
    strokes, style, width, height = parse_gallery_piece(data)
    if width <= 0 or height <= 0:
        return None
    token = data.get("image_token")
    raster = version_asset(user_dir, token, "final.png") if isinstance(token, str) else None
    if not strokes and raster is None:
        return None

    scale = min(1, THUMBNAIL_MAX_SIDE / max(width, height))
    result = await render_strokes_async(
        strokes,
        RenderOptions(
            width=max(1, round(width * scale)),
            height=max(1, round(height * scale)),
            drawing_style=style,
            scale_from=(width, height),
            base_image=str(raster) if raster else None,
        ),
    )
    assert isinstance(result, bytes)

    # A unique temporary name keeps simultaneous first requests for an old
    # piece from racing over the same temporary file.
    temporary_path = thumbnail_path.with_name(f"{thumbnail_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        async with aiofiles.open(temporary_path, "wb") as thumbnail_file:
            await thumbnail_file.write(result)
        await aiofiles.os.replace(temporary_path, thumbnail_path)
    finally:
        if await aiofiles.os.path.exists(temporary_path):
            await aiofiles.os.remove(temporary_path)
    return result
