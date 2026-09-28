"""Program-painting version assets (keyframes, final image, reveal log, program).

URLs carry an unguessable per-version token, so assets load in plain <img>
tags and native image views without auth headers, like share links.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from code_monet.paintlib.performance import FrameScanner
from code_monet.program_painting import PAINT_TIMEOUT_S
from code_monet.workspace.assets import version_asset
from code_monet.workspace.persistence import get_user_dir

router = APIRouter()

_ASSET = re.compile(
    r"^(kf_\d{2}\.jpg|final\.png|preview\.jpg|reveal\.json|painting\.py|performance\.bin)$"
)
_MEDIA = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".json": "application/json",
    ".py": "text/plain; charset=utf-8",
    ".bin": "application/octet-stream",
}
_PERFORMANCE = "performance.bin"
# A live performance is followed at most this long and this large; a run that
# stops writing (killed, discarded) ends the response once the file goes away.
_LIVE_MAX_S = PAINT_TIMEOUT_S + 30
_LIVE_MAX_BYTES = 256 * 1024 * 1024
_LIVE_POLL_S = 0.1
_READ = 1 << 16


@router.get("/painting-assets/{user_id}/{token}/{file}", response_model=None)
async def get_painting_asset(
    user_id: str, token: str, file: str
) -> FileResponse | StreamingResponse:
    if not _ASSET.match(file):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        user_dir = get_user_dir(user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found") from e
    path = version_asset(user_dir, token, file)
    if path is None:
        raise HTTPException(status_code=404, detail="Not found")
    if file == _PERFORMANCE and not await asyncio.to_thread(_performance_complete, path):
        return StreamingResponse(
            _follow(path),
            media_type=_MEDIA[".bin"],
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
    return FileResponse(
        path,
        media_type=_MEDIA[path.suffix],
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _performance_complete(path: Path) -> bool:
    scanner = FrameScanner()
    with path.open("rb") as f:
        while chunk := f.read(_READ):
            scanner.feed(chunk)
    return scanner.ended


async def _follow(path: Path) -> AsyncIterator[bytes]:
    """Stream a performance that is still being painted, as it grows."""
    scanner = FrameScanner()
    sent = 0
    deadline = time.monotonic() + _LIVE_MAX_S
    with path.open("rb") as f:
        while sent < _LIVE_MAX_BYTES and time.monotonic() < deadline:
            chunk = f.read(_READ)
            if chunk:
                scanner.feed(chunk)
                sent += len(chunk)
                yield chunk
                if scanner.ended:
                    return
                continue
            if not path.exists():
                return  # the run failed and its version was discarded
            await asyncio.sleep(_LIVE_POLL_S)
