"""User gallery endpoints."""

import re
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response

from code_monet.auth.dependencies import CurrentUser
from code_monet.db import get_session, repository
from code_monet.routes.canvas import get_user_state, render_strokes_to_png
from code_monet.types import get_style_config

router = APIRouter()


@router.get("/gallery")
async def get_gallery_list(user: CurrentUser) -> list[dict[str, Any]]:
    """Get user's gallery pieces."""
    state = await get_user_state(user)
    entries = await state.list_gallery()
    return [entry.model_dump() for entry in entries]


@router.get("/gallery/{piece_number}/strokes")
async def get_gallery_piece_strokes(piece_number: int, user: CurrentUser) -> dict[str, Any]:
    """Get strokes for a gallery piece (read-only, no workspace mutation)."""
    state = await get_user_state(user)
    result = await state.load_from_gallery(piece_number)
    if not result:
        raise HTTPException(status_code=404, detail="Piece not found")
    strokes, drawing_style, width, height = result
    style_config = get_style_config(drawing_style)
    return {
        "strokes": [s.model_dump() for s in strokes],
        "piece_number": piece_number,
        "canvas_width": width,
        "canvas_height": height,
        "drawing_style": drawing_style.value,
        "style_config": style_config.model_dump(),
    }


@router.get("/gallery/thumbnail/{piece_id}.png")
async def get_gallery_thumbnail(piece_id: str, user: CurrentUser) -> Response:
    """Get gallery piece as thumbnail PNG. Requires auth.

    Args:
        piece_id: Gallery piece ID like "piece_000001"

    Returns:
        PNG image of the piece with long cache headers.
    """
    # Validate and parse piece_id (e.g., "piece_000001" -> 1)
    match = re.match(r"^piece_(\d+)$", piece_id)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid piece_id format")

    piece_number = int(match.group(1))

    state = await get_user_state(user)
    result = await state.load_from_gallery(piece_number)

    if result is None:
        raise HTTPException(status_code=404, detail="Piece not found")

    strokes, style, width, height = result
    if not strokes:
        raise HTTPException(status_code=404, detail="Piece has no strokes")

    png_bytes = await render_strokes_to_png(
        strokes, width=width, height=height, drawing_style=style
    )
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


@router.get("/settings/gallery")
async def get_gallery_settings(user: CurrentUser) -> dict[str, Any]:
    """Get user's gallery visibility settings."""
    async with get_session() as session:
        db_user = await repository.get_user_by_id(session, user.id)
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")
        return {"gallery_public": db_user.gallery_public}


@router.put("/settings/gallery")
async def update_gallery_settings(
    user: CurrentUser,
    gallery_public: bool = Body(..., embed=True),
) -> dict[str, Any]:
    """Update user's gallery visibility settings."""
    async with get_session() as session:
        success = await repository.set_gallery_public(session, user.id, gallery_public)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        await session.commit()
        return {"gallery_public": gallery_public}
