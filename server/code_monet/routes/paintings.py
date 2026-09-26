"""Program-painting version assets (keyframes, final image, reveal log, program).

URLs carry an unguessable per-version token, so assets load in plain <img>
tags and native image views without auth headers, like share links.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from code_monet.workspace.assets import version_asset
from code_monet.workspace.persistence import get_user_dir

router = APIRouter()

_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_ASSET = re.compile(r"^(kf_\d{2}\.jpg|final\.png|preview\.jpg|reveal\.json|painting\.py)$")
_MEDIA = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".json": "application/json",
    ".py": "text/plain; charset=utf-8",
}


@router.get("/painting-assets/{user_id}/{token}/{file}")
async def get_painting_asset(user_id: str, token: str, file: str) -> FileResponse:
    if not _TOKEN.match(token) or not _ASSET.match(file):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        user_dir = get_user_dir(user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found") from e
    path = version_asset(user_dir, token, file)
    if path is None:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        path,
        media_type=_MEDIA[path.suffix],
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
