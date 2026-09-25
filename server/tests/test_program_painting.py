"""Program painting: running the agent's program, versions, assets, gallery."""

from __future__ import annotations

import json
import uuid
from pathlib import Path as FilePath

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from code_monet.program_painting import PaintFailure, PaintSuccess, run_painting_program
from code_monet.routes import paintings as paintings_routes
from code_monet.types import DrawingStyleType, Path, PathType, Point
from code_monet.workspace import WorkspaceState

PROGRAM = """
cv.stage("ground")
cv.ground("#d9c9a8")
cv.stage("sky")
cv.fill(cv.rect_mask(0, 0, W, H // 2), "#6d8fb0")
cv.stroke([(20, 20), (200, 60)], 12, "#ffffff")
"""


@pytest.fixture
async def workspace(tmp_path: FilePath) -> WorkspaceState:
    user_dir = tmp_path / str(uuid.uuid4())
    (user_dir / "gallery").mkdir(parents=True)
    state = WorkspaceState(user_id=user_dir.name, user_dir=user_dir)
    state._loaded = True
    state.canvas.width, state.canvas.height = 160, 120
    state.canvas.drawing_style = DrawingStyleType.PAINT
    return state


def _write_program(state: WorkspaceState, source: str) -> None:
    state.studio_program.parent.mkdir(parents=True, exist_ok=True)
    state.studio_program.write_text(source)


class TestRunPaintingProgram:
    @pytest.mark.asyncio
    async def test_missing_program_asks_agent_to_write_it(self, workspace: WorkspaceState) -> None:
        result = await run_painting_program(workspace)
        assert isinstance(result, PaintFailure)
        assert "studio/painting.py" in result.error

    @pytest.mark.asyncio
    async def test_success_records_version_with_assets(self, workspace: WorkspaceState) -> None:
        _write_program(workspace, PROGRAM)

        result = await run_painting_program(workspace)

        assert isinstance(result, PaintSuccess), result
        v = result.version
        assert (v.version, v.image_width, v.image_height) == (1, 320, 240)
        assert v.stages == ["ground", "sky"]
        out = workspace.paintings_dir / v.token
        assert {p.name for p in out.iterdir()} >= {
            "kf_00.jpg",
            "kf_01.jpg",
            "final.png",
            "preview.jpg",
            "reveal.json",
            "painting.py",
        }
        reveal = json.loads((out / "reveal.json").read_text())
        ops = reveal["keyframes"][1]["ops"]
        assert ops[0][0] == "a" and ops[1][0] == "s"
        assert workspace.painting == v

    @pytest.mark.asyncio
    async def test_versions_increment_and_failures_leave_current(
        self, workspace: WorkspaceState
    ) -> None:
        _write_program(workspace, PROGRAM)
        first = await run_painting_program(workspace)
        assert isinstance(first, PaintSuccess)
        _write_program(workspace, "raise ValueError('bad brush')")

        failed = await run_painting_program(workspace)

        assert isinstance(failed, PaintFailure)
        assert "bad brush" in failed.error
        assert workspace.painting == first.version
        _write_program(workspace, PROGRAM)
        second = await run_painting_program(workspace)
        assert isinstance(second, PaintSuccess)
        assert second.version.version == 2


class TestRasterGallery:
    @pytest.mark.asyncio
    async def test_new_canvas_saves_raster_piece_and_resets(
        self, workspace: WorkspaceState
    ) -> None:
        _write_program(workspace, PROGRAM)
        result = await run_painting_program(workspace)
        assert isinstance(result, PaintSuccess)
        human = Path(type=PathType.LINE, points=[Point(x=1, y=1), Point(x=5, y=5)], author="human")
        await workspace.add_strokes([human])

        saved = await workspace.new_canvas(width=160, height=120)

        assert saved is not None
        raster = await workspace.gallery_raster(0)
        assert raster is not None and raster[0] == result.version.token
        assert workspace.painting is None
        assert not workspace.studio_program.exists()
        entries = await workspace.list_gallery()
        assert entries[0].format == "raster"

    @pytest.mark.asyncio
    async def test_workspace_render_uses_painting(self, workspace: WorkspaceState) -> None:
        from code_monet.rendering import render_workspace

        _write_program(workspace, PROGRAM)
        assert isinstance(await run_painting_program(workspace), PaintSuccess)

        img = render_workspace(workspace, output_format="image")

        assert isinstance(img, Image.Image)
        r, g, b = img.getpixel((80, 20))[:3]  # sky fill, not the white background
        assert b > r and (r, g, b) != (255, 255, 255)


class TestPaintingAssetRoute:
    def test_serves_whitelisted_assets_only(
        self, tmp_path: FilePath, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_id = str(uuid.uuid4())
        token = "a" * 32
        vdir = tmp_path / user_id / "paintings" / token
        vdir.mkdir(parents=True)
        (vdir / "reveal.json").write_text("{}")
        (vdir / "painting.py").write_text("secret")
        monkeypatch.setattr(paintings_routes, "get_user_dir", lambda uid: tmp_path / uid)
        app = FastAPI()
        app.include_router(paintings_routes.router)
        client = TestClient(app)

        ok = client.get(f"/painting-assets/{user_id}/{token}/reveal.json")
        assert ok.status_code == 200
        assert "immutable" in ok.headers["cache-control"]
        assert client.get(f"/painting-assets/{user_id}/{token}/painting.py").status_code == 404
        assert client.get(f"/painting-assets/{user_id}/{'b' * 32}/reveal.json").status_code == 404
        assert client.get(f"/painting-assets/{user_id}/..%2F..%2Fx/reveal.json").status_code == 404
