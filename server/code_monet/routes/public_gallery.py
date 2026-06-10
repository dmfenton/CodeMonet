"""Public gallery endpoints for unauthenticated access."""

import json
import re
from pathlib import Path as FilePath
from typing import Any

import aiofiles
import aiofiles.os
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from code_monet.config import settings
from code_monet.db import get_session, repository
from code_monet.rendering import options_for_og_image, options_for_thumbnail, render_strokes_async
from code_monet.types import DrawingStyleType, Path

router = APIRouter()

# Regex pattern for validating UUIDs
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


async def _load_public_piece(
    user_id: str, piece_id: str
) -> tuple[list[Path], DrawingStyleType, int, int]:
    """Load strokes and style for a public gallery piece with validation.

    Args:
        user_id: UUID of the user who owns the piece
        piece_id: Piece identifier (e.g., "piece_000001")

    Returns:
        Tuple of (strokes list, drawing style, width, height)

    Raises:
        HTTPException: For invalid input, unauthorized access, or missing pieces
    """
    # Validate user_id is UUID format (prevent path traversal)
    if not _UUID_PATTERN.match(user_id):
        raise HTTPException(status_code=400, detail="Invalid user_id")

    # Validate piece_id format (alphanumeric, underscore, hyphen only)
    if not piece_id.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid piece_id")

    # Verify user has opted into public gallery
    async with get_session() as session:
        user = await repository.get_user_by_id(session, user_id)
        if not user or not user.gallery_public:
            raise HTTPException(status_code=404, detail="Gallery not found")

    # Load piece file with path traversal protection
    workspace_base = FilePath(settings.workspace_base_dir).resolve()
    piece_file = (workspace_base / user_id / "gallery" / f"{piece_id}.json").resolve()

    if not str(piece_file).startswith(str(workspace_base)):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not piece_file.exists():
        raise HTTPException(status_code=404, detail="Piece not found")

    try:
        data = json.loads(piece_file.read_text())
        strokes = [Path(**s) for s in data.get("strokes", [])]
        # Parse drawing style with fallback to plotter
        style_str = data.get("drawing_style", "plotter")
        try:
            drawing_style = DrawingStyleType(style_str)
        except ValueError:
            drawing_style = DrawingStyleType.PLOTTER
        return strokes, drawing_style, data.get("width", 800), data.get("height", 600)
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to load piece: {e}") from e


@router.get("/public/gallery")
async def get_public_gallery(limit: int = Query(default=12, le=50)) -> list[dict[str, Any]]:
    """Get public gallery showcasing artwork from users who opted in.

    Returns pieces for the homepage - no authentication required.
    Shows artwork from all users who have set gallery_public=True.
    """
    pieces: list[dict[str, Any]] = []
    workspace_base = FilePath(settings.workspace_base_dir).resolve()

    if not workspace_base.exists():
        return []

    # Get all users with public galleries
    async with get_session() as session:
        public_users = await repository.list_users_with_public_gallery(session)

    if not public_users:
        return []

    # Load gallery pieces from all public users
    for user in public_users:
        gallery_dir = workspace_base / str(user.id) / "gallery"
        if not gallery_dir.exists():
            continue

        # Scan piece files directly (async I/O to avoid blocking)
        for entry_name in await aiofiles.os.listdir(gallery_dir):
            if not entry_name.startswith("piece_") or not entry_name.endswith(".json"):
                continue
            try:
                async with aiofiles.open(gallery_dir / entry_name) as f:
                    data = json.loads(await f.read())
                piece_entry: dict[str, Any] = {
                    "id": f"piece_{data.get('piece_number', 0):06d}",
                    "user_id": str(user.id),
                    "piece_number": data.get("piece_number", 0),
                    "stroke_count": len(data.get("strokes", [])),
                    "width": data.get("width", 800),
                    "height": data.get("height", 600),
                    "created_at": data.get("created_at", ""),
                }
                if data.get("title"):
                    piece_entry["title"] = data["title"]
                pieces.append(piece_entry)
            except (json.JSONDecodeError, OSError):
                pass

    # Sort by created_at descending (most recent first across all users)
    pieces.sort(key=lambda p: p.get("created_at", ""), reverse=True)

    return pieces[:limit]


@router.get("/public/gallery/{user_id}/{piece_id}/strokes")
async def get_public_piece_strokes(user_id: str, piece_id: str) -> dict[str, Any]:
    """Get strokes for a specific gallery piece.

    Returns the full stroke data for rendering on the homepage.
    Only returns data if the user has opted into public gallery.
    """
    # Validate user_id is a valid UUID format to prevent path traversal
    if not _UUID_PATTERN.match(user_id):
        raise HTTPException(status_code=400, detail="Invalid user_id")

    # Validate piece_id format (alphanumeric, underscore, hyphen only)
    if not piece_id.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid piece_id")

    # Verify the user has opted into public gallery
    async with get_session() as session:
        user = await repository.get_user_by_id(session, user_id)
        if not user or not user.gallery_public:
            raise HTTPException(status_code=404, detail="Gallery not found")

    workspace_base = FilePath(settings.workspace_base_dir).resolve()
    gallery_dir = workspace_base / user_id / "gallery"
    piece_file = (gallery_dir / f"{piece_id}.json").resolve()

    # Ensure the resolved path stays within the workspace (prevent path traversal)
    if not str(piece_file).startswith(str(workspace_base)):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not gallery_dir.exists():
        raise HTTPException(status_code=404, detail="Gallery not found")

    if not piece_file.exists():
        raise HTTPException(status_code=404, detail="Piece not found")

    try:
        data = json.loads(piece_file.read_text())
        return {
            "id": piece_id,
            "strokes": data.get("strokes", []),
            "piece_number": data.get("piece_number", 0),
            "canvas_width": data.get("width", 800),
            "canvas_height": data.get("height", 600),
            "created_at": data.get("created_at", ""),
        }
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to load piece: {e}") from e


@router.get("/public/gallery/{user_id}/{piece_id}/thumbnail.png")
async def get_public_piece_thumbnail(user_id: str, piece_id: str) -> Response:
    """Get thumbnail PNG for a gallery piece.

    Renders gallery piece strokes to PNG using the saved canvas dimensions.
    Only returns image if user has opted into public gallery.
    """
    strokes, drawing_style, width, height = await _load_public_piece(user_id, piece_id)

    options = options_for_thumbnail(drawing_style, width, height)
    result = await render_strokes_async(strokes, options)
    assert isinstance(result, bytes)

    return Response(
        content=result,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},  # 7 days
    )


@router.get("/public/gallery/{user_id}/{piece_id}/og-image.png")
async def get_public_piece_og_image(user_id: str, piece_id: str) -> Response:
    """Get OG image for social sharing.

    Renders gallery piece strokes to 1200x630 PNG (optimal OG image size).
    Only returns image if user has opted into public gallery.
    """
    strokes, drawing_style, width, height = await _load_public_piece(user_id, piece_id)

    options = options_for_og_image(drawing_style, width, height)
    result = await render_strokes_async(strokes, options)
    assert isinstance(result, bytes)

    return Response(
        content=result,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},  # 7 days
    )
