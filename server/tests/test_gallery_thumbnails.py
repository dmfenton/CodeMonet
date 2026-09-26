"""Gallery thumbnails are small, persisted, and available to older pieces."""

import asyncio
import io
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import aiofiles.os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from code_monet.auth.dependencies import get_current_user
from code_monet.db import User
from code_monet.routes import gallery as gallery_routes
from code_monet.types import Path as StrokePath
from code_monet.types import PathType, Point
from code_monet.workspace import WorkspaceState


def _state(tmp_path: Path) -> WorkspaceState:
    user_dir = tmp_path / str(uuid.uuid4())
    (user_dir / "gallery").mkdir(parents=True)
    state = WorkspaceState(user_id=user_dir.name, user_dir=user_dir)
    state._loaded = True
    state.canvas.width = 1600
    state.canvas.height = 1200
    return state


@pytest.mark.asyncio
async def test_saved_piece_prepares_small_thumbnail_and_reuses_it(tmp_path: Path) -> None:
    state = _state(tmp_path)
    await state.add_strokes(
        [StrokePath(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=1600, y=1200)])]
    )
    await state.save_to_gallery()

    thumbnail_path = state._gallery_dir / "piece_000000.thumb.png"
    assert thumbnail_path.exists()
    with patch(
        "code_monet.workspace.render_strokes_async", side_effect=AssertionError("rerendered")
    ):
        data = await state.gallery_thumbnail(0)
    assert data == thumbnail_path.read_bytes()
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (640, 480)


@pytest.mark.asyncio
async def test_older_piece_is_cached_after_first_request(tmp_path: Path) -> None:
    state = _state(tmp_path)
    piece_path = state._gallery_dir / "piece_001.json"
    piece_path.write_text(
        json.dumps(
            {
                "piece_number": 1,
                "width": 800,
                "height": 600,
                "drawing_style": "plotter",
                "strokes": [
                    StrokePath(
                        type=PathType.LINE, points=[Point(x=0, y=0), Point(x=800, y=600)]
                    ).model_dump()
                ],
            }
        )
    )

    first = await state.gallery_thumbnail(1)
    with patch(
        "code_monet.workspace.render_strokes_async", side_effect=AssertionError("rerendered")
    ):
        second = await state.gallery_thumbnail(1)
    assert first == second
    assert (state._gallery_dir / "piece_000001.thumb.png").read_bytes() == first


@pytest.mark.asyncio
async def test_gallery_list_reuses_metadata_without_reading_strokes(tmp_path: Path) -> None:
    state = _state(tmp_path)
    await state.add_strokes(
        [StrokePath(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=1600, y=1200)])]
    )
    await state.save_to_gallery()
    first = await state.list_gallery()

    assert (state._gallery_dir / "piece_000000.meta").exists()
    with patch("code_monet.workspace.gallery.json.loads", side_effect=AssertionError("full read")):
        assert await state.list_gallery() == first


@pytest.mark.asyncio
async def test_owner_thumbnail_route_serves_saved_thumbnail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _state(tmp_path)
    await state.add_strokes(
        [StrokePath(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=1600, y=1200)])]
    )
    await state.save_to_gallery()

    async def get_state(_user: User) -> WorkspaceState:
        return state

    monkeypatch.setattr(gallery_routes, "get_user_state", get_state)
    app = FastAPI()
    app.include_router(gallery_routes.router)
    app.dependency_overrides[get_current_user] = lambda: User(
        id=state.user_id, email="owner@example.com", password_hash="unused"
    )
    with TestClient(app) as client:
        response = client.get("/gallery/thumbnail/piece_000000.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.size == (640, 480)


@pytest.mark.asyncio
async def test_portrait_thumbnail_caps_longest_edge(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.canvas.width = 600
    state.canvas.height = 900
    await state.add_strokes(
        [StrokePath(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=600, y=900)])]
    )
    await state.save_to_gallery()

    data = await state.gallery_thumbnail(0)
    assert data is not None
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (427, 640)


@pytest.mark.asyncio
async def test_resave_waits_for_same_piece_thumbnail_render(tmp_path: Path) -> None:
    state = _state(tmp_path)
    stroke = StrokePath(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=1600, y=1200)])
    await state.add_strokes([stroke])
    await state.save_to_gallery()
    (state._gallery_dir / "piece_000000.thumb.png").unlink()

    rendering = asyncio.Event()
    finish_render = asyncio.Event()

    async def render(strokes: list[StrokePath], _options: object) -> bytes:
        if len(strokes) == 1:
            rendering.set()
            await finish_render.wait()
        return b"old" if len(strokes) == 1 else b"new"

    with patch("code_monet.workspace.render_strokes_async", side_effect=render):
        old_request = asyncio.create_task(state.gallery_thumbnail(0))
        await rendering.wait()
        await state.add_strokes([stroke])
        resave = asyncio.create_task(state.save_to_gallery())
        await asyncio.sleep(0)
        assert not resave.done()
        finish_render.set()
        await old_request
        await resave

    assert (state._gallery_dir / "piece_000000.thumb.png").read_bytes() == b"new"


@pytest.mark.asyncio
async def test_resave_waits_for_metadata_publication(tmp_path: Path) -> None:
    state = _state(tmp_path)
    stroke = StrokePath(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=1600, y=1200)])
    await state.add_strokes([stroke])
    await state.save_to_gallery()
    first = await state.list_gallery()
    assert first[0].title is None
    (state._gallery_dir / "piece_000000.meta").unlink()

    publishing = asyncio.Event()
    finish_publish = asyncio.Event()
    real_replace = aiofiles.os.replace

    async def replace(source: Path, destination: Path) -> None:
        if destination.suffix == ".meta":
            publishing.set()
            await finish_publish.wait()
        await real_replace(source, destination)

    with patch("code_monet.workspace.gallery.aiofiles.os.replace", side_effect=replace):
        old_listing = asyncio.create_task(state.list_gallery())
        await publishing.wait()
        state.current_piece_title = "New title"
        resave = asyncio.create_task(state.save_to_gallery())
        await asyncio.sleep(0)
        assert not resave.done()
        finish_publish.set()
        await old_listing
        await resave

    assert (await state.list_gallery())[0].title == "New title"
