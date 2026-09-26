"""Piece history: painting versions, prompt, and stroke count across state, gallery, and APIs."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path as FilePath
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from code_monet.auth.dependencies import get_current_user
from code_monet.db import User
from code_monet.main import _init_message, _painting_ref
from code_monet.orchestrator import AgentOrchestrator
from code_monet.routes import gallery as gallery_routes
from code_monet.routes import paintings as paintings_routes
from code_monet.types import DrawingStyleType, PaintingVersion, Path, PathType, Point
from code_monet.user_handlers import handle_new_canvas
from code_monet.workspace import WorkspaceState
from code_monet.workspace.gallery import piece_detail_fields, piece_stroke_count

VERSION_RECORD_KEYS = {"version", "token", "image_width", "image_height", "stages", "ops"}
VERSION_REF_KEYS = {
    "version",
    "asset_base",
    "image_width",
    "image_height",
    "stages",
    "ops",
    "created_at",
}


def _new_state(user_dir: FilePath) -> WorkspaceState:
    (user_dir / "gallery").mkdir(parents=True, exist_ok=True)
    state = WorkspaceState(user_id=user_dir.name, user_dir=user_dir)
    state._loaded = True
    state.canvas.drawing_style = DrawingStyleType.PAINT
    return state


@pytest.fixture
def workspace(tmp_path: FilePath) -> WorkspaceState:
    return _new_state(tmp_path / str(uuid.uuid4()))


async def _record(
    state: WorkspaceState, ops: int, stages: list[str] | None = None
) -> PaintingVersion:
    """Record a version with a real final.png on disk (as run_painting_program would)."""
    token = uuid.uuid4().hex
    vdir = state.paintings_dir / token
    vdir.mkdir(parents=True)
    (vdir / "final.png").write_bytes(b"png")
    return await state.record_painting_version(
        token, 320, 240, stages if stages is not None else ["ground"], ops=ops
    )


def _gallery_json(state: WorkspaceState, piece_number: int) -> dict:
    return json.loads((state._user_dir / "gallery" / f"piece_{piece_number:06d}.json").read_text())


def _human_stroke() -> Path:
    return Path(type=PathType.LINE, points=[Point(x=1, y=1), Point(x=5, y=5)], author="human")


class TestWorkspaceVersionHistory:
    @pytest.mark.asyncio
    async def test_versions_accumulate_and_painting_is_latest(
        self, workspace: WorkspaceState
    ) -> None:
        v1 = await _record(workspace, ops=10)
        v2 = await _record(workspace, ops=25)

        assert [v.version for v in workspace.painting_versions] == [1, 2]
        assert workspace.painting_versions == [v1, v2]
        assert workspace.painting == v2
        assert v2.ops == 25

    @pytest.mark.asyncio
    async def test_round_trip_persists_versions_and_prompt(self, workspace: WorkspaceState) -> None:
        await workspace.new_canvas(prompt="a stormy sea")
        await _record(workspace, ops=10)
        await _record(workspace, ops=25)

        loaded = WorkspaceState(workspace.user_id, workspace._user_dir)
        await loaded._load_from_file()

        assert loaded.painting_versions == workspace.painting_versions
        assert loaded.painting == workspace.painting
        assert loaded.current_piece_prompt == "a stormy sea"

    @pytest.mark.asyncio
    async def test_old_state_seeds_versions_from_current_painting(self, tmp_path: FilePath) -> None:
        user_dir = tmp_path / str(uuid.uuid4())
        user_dir.mkdir()
        painting = {
            "piece_number": 3,
            "version": 4,
            "token": "a" * 32,
            "image_width": 320,
            "image_height": 240,
            "stages": ["ground"],
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        (user_dir / "workspace.json").write_text(json.dumps({"painting": painting}))

        state = WorkspaceState(user_dir.name, user_dir)
        await state._load_from_file()

        assert state.painting is not None
        assert state.painting.version == 4 and state.painting.ops == 0
        assert state.painting_versions == [state.painting]
        assert state.current_piece_prompt is None

    @pytest.mark.asyncio
    async def test_old_state_without_painting_loads_no_versions(self, tmp_path: FilePath) -> None:
        user_dir = tmp_path / str(uuid.uuid4())
        user_dir.mkdir()
        (user_dir / "workspace.json").write_text(json.dumps({"painting": None}))

        state = WorkspaceState(user_dir.name, user_dir)
        await state._load_from_file()

        assert state.painting is None
        assert state.painting_versions == []

    @pytest.mark.asyncio
    async def test_new_canvas_and_clear_reset_versions(self, workspace: WorkspaceState) -> None:
        await _record(workspace, ops=10)
        await workspace.new_canvas()
        assert workspace.painting_versions == []
        assert workspace.painting is None

        await _record(workspace, ops=10)
        await workspace.clear_canvas()
        assert workspace.painting_versions == []

        restarted = await _record(workspace, ops=5)
        assert restarted.version == 1


def _handler_workspace(state: WorkspaceState) -> MagicMock:
    workspace = MagicMock()
    workspace.user_id = state.user_id
    workspace.state = state
    workspace.agent.resume = AsyncMock()
    workspace.connections.broadcast = AsyncMock()
    workspace.start_agent_loop = AsyncMock()
    return workspace


class TestPromptLifecycle:
    @pytest.mark.asyncio
    async def test_prompt_belongs_to_the_new_piece(self, workspace: WorkspaceState) -> None:
        handler_ws = _handler_workspace(workspace)

        await handle_new_canvas(handler_ws, {"direction": "a stormy sea"})
        assert workspace.current_piece_prompt == "a stormy sea"
        first_piece = workspace.piece_number
        await _record(workspace, ops=10)

        await handle_new_canvas(handler_ws, {"direction": "a quiet pond"})

        assert _gallery_json(workspace, first_piece)["prompt"] == "a stormy sea"
        assert workspace.current_piece_prompt == "a quiet pond"
        handler_ws.agent.add_nudge.assert_called_with("a quiet pond")

    @pytest.mark.asyncio
    async def test_new_canvas_without_direction_clears_prompt(
        self, workspace: WorkspaceState
    ) -> None:
        handler_ws = _handler_workspace(workspace)
        await handle_new_canvas(handler_ws, {"direction": "a stormy sea"})

        await handle_new_canvas(handler_ws, {})

        assert workspace.current_piece_prompt is None

    @pytest.mark.asyncio
    async def test_clear_clears_prompt(self, workspace: WorkspaceState) -> None:
        await workspace.new_canvas(prompt="a stormy sea")

        await workspace.clear_canvas()

        assert workspace.current_piece_prompt is None


class TestGalleryPieceJson:
    @pytest.mark.asyncio
    async def test_raster_piece_records_prompt_and_versions(
        self, workspace: WorkspaceState
    ) -> None:
        await workspace.new_canvas(prompt="a stormy sea")
        piece = workspace.piece_number
        v1 = await _record(workspace, ops=10, stages=["ground"])
        v2 = await _record(workspace, ops=25, stages=["ground", "sky"])

        await workspace.save_to_gallery()

        data = _gallery_json(workspace, piece)
        assert data["prompt"] == "a stormy sea"
        assert data["image_token"] == v2.token
        assert [set(v) for v in data["versions"]] == [VERSION_RECORD_KEYS | {"created_at"}] * 2
        assert data["versions"] == [
            {
                "version": v.version,
                "token": v.token,
                "image_width": 320,
                "image_height": 240,
                "stages": v.stages,
                "ops": v.ops,
                "created_at": v.created_at,
            }
            for v in (v1, v2)
        ]

    @pytest.mark.asyncio
    async def test_vector_piece_has_prompt_but_no_versions(self, workspace: WorkspaceState) -> None:
        await workspace.add_strokes([_human_stroke()])

        await workspace.save_to_gallery()

        data = _gallery_json(workspace, workspace.piece_number)
        assert data["prompt"] is None
        assert "versions" not in data

    @pytest.mark.asyncio
    async def test_raster_stroke_count_is_final_version_ops(
        self, workspace: WorkspaceState
    ) -> None:
        await _record(workspace, ops=10)
        await _record(workspace, ops=25)
        await workspace.add_strokes([_human_stroke()])
        await workspace.save_to_gallery()

        [entry] = await workspace.list_gallery()

        assert entry.format == "raster"
        assert entry.stroke_count == 25

    @pytest.mark.asyncio
    async def test_legacy_and_vector_pieces_count_strokes(self, workspace: WorkspaceState) -> None:
        await workspace.add_strokes([_human_stroke(), _human_stroke()])
        await workspace.save_to_gallery()
        [entry] = await workspace.list_gallery()
        assert entry.stroke_count == 2

        legacy = {"strokes": [{}], "format": "raster", "image_token": "a" * 32}
        assert piece_stroke_count(legacy) == 1


class TestPieceDetailFields:
    def test_legacy_raster_piece_synthesizes_single_version(self) -> None:
        data = {
            "piece_number": 4,
            "title": "Old Sea",
            "strokes": [],
            "created_at": "2026-01-01T00:00:00+00:00",
            "format": "raster",
            "image_token": "b" * 32,
            "image_width": 1600,
            "image_height": 1200,
        }

        fields = piece_detail_fields(data, "user-1", raster=True)

        assert fields == {
            "title": "Old Sea",
            "prompt": None,
            "stroke_count": 0,
            "versions": [
                {
                    "version": 1,
                    "asset_base": f"/painting-assets/user-1/{'b' * 32}/",
                    "image_width": 1600,
                    "image_height": 1200,
                    "stages": [],
                    "ops": 0,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        }

    def test_strokes_piece_has_no_versions(self) -> None:
        fields = piece_detail_fields({"strokes": [{}]}, "user-1", raster=False)

        assert fields["versions"] == []
        assert fields["stroke_count"] == 1


class TestOwnerPieceEndpoint:
    @pytest.fixture
    def client(self, workspace: WorkspaceState, monkeypatch: pytest.MonkeyPatch) -> TestClient:
        async def get_user_state(_user: User) -> WorkspaceState:
            return workspace

        monkeypatch.setattr(gallery_routes, "get_user_state", get_user_state)
        app = FastAPI()
        app.include_router(gallery_routes.router)
        app.dependency_overrides[get_current_user] = lambda: User(
            id=workspace.user_id, email="owner@example.com", password_hash="unused"
        )
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_raster_piece_detail(self, workspace: WorkspaceState, client: TestClient) -> None:
        await workspace.new_canvas(prompt="a stormy sea")
        workspace.current_piece_title = "Storm"
        piece = workspace.piece_number
        await _record(workspace, ops=10)
        v2 = await _record(workspace, ops=25)
        await workspace.save_to_gallery()

        data = client.get(f"/gallery/{piece}/strokes").json()

        assert data["title"] == "Storm"
        assert data["prompt"] == "a stormy sea"
        assert data["stroke_count"] == 25
        assert data["drawing_style"] == "paint"
        assert data["format"] == "raster"
        assert [v["version"] for v in data["versions"]] == [1, 2]
        assert set(data["versions"][1]) == VERSION_REF_KEYS
        assert data["versions"][1]["asset_base"] == v2.asset_base(workspace.user_id)
        assert data["versions"][1]["ops"] == 25

    @pytest.mark.asyncio
    async def test_legacy_raster_piece_synthesizes_version(
        self, workspace: WorkspaceState, client: TestClient
    ) -> None:
        v = await _record(workspace, ops=10)
        await workspace.save_to_gallery()
        path = workspace._user_dir / "gallery" / "piece_000000.json"
        legacy = json.loads(path.read_text())
        del legacy["versions"], legacy["prompt"]
        path.write_text(json.dumps(legacy))

        data = client.get("/gallery/0/strokes").json()

        assert data["prompt"] is None
        assert data["versions"] == [
            {
                "version": 1,
                "asset_base": v.asset_base(workspace.user_id),
                "image_width": 320,
                "image_height": 240,
                "stages": [],
                "ops": 0,
                "created_at": legacy["created_at"],
            }
        ]

    @pytest.mark.asyncio
    async def test_strokes_piece_has_empty_versions(
        self, workspace: WorkspaceState, client: TestClient
    ) -> None:
        await workspace.add_strokes([_human_stroke()])
        await workspace.save_to_gallery()

        data = client.get("/gallery/0/strokes").json()

        assert data["format"] == "strokes"
        assert data["versions"] == []
        assert data["stroke_count"] == 1
        assert data["title"] is None


class TestPublicPieceEndpoint:
    @pytest.fixture
    def public_workspace(self, tmp_path: FilePath) -> Iterator[tuple[WorkspaceState, TestClient]]:
        user_id = str(uuid.uuid4())
        state = _new_state(tmp_path / user_id)
        user = MagicMock(id=user_id, gallery_public=True)
        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        session_ctx.__aexit__ = AsyncMock(return_value=None)
        with (
            patch("code_monet.routes.public_gallery.settings") as mock_settings,
            patch("code_monet.routes.public_gallery.repository") as mock_repo,
            patch("code_monet.routes.public_gallery.get_session", return_value=session_ctx),
        ):
            mock_settings.workspace_base_dir = str(tmp_path)
            mock_repo.get_user_by_id = AsyncMock(return_value=user)
            from code_monet.main import app

            yield state, TestClient(app)

    @pytest.mark.asyncio
    async def test_raster_piece_detail(
        self, public_workspace: tuple[WorkspaceState, TestClient]
    ) -> None:
        state, client = public_workspace
        await state.new_canvas(prompt="a stormy sea")
        state.current_piece_title = "Storm"
        await _record(state, ops=10)
        await _record(state, ops=25)
        await state.save_to_gallery()

        data = client.get(f"/public/gallery/{state.user_id}/piece_000001/strokes").json()

        assert data["title"] == "Storm"
        assert data["prompt"] == "a stormy sea"
        assert data["stroke_count"] == 25
        assert data["drawing_style"] == "paint"
        assert [v["version"] for v in data["versions"]] == [1, 2]
        assert set(data["versions"][0]) == VERSION_REF_KEYS
        assert data["versions"][0]["asset_base"].startswith(f"/painting-assets/{state.user_id}/")

    @pytest.mark.asyncio
    async def test_legacy_raster_piece_synthesizes_version(
        self, public_workspace: tuple[WorkspaceState, TestClient]
    ) -> None:
        state, client = public_workspace
        v = await _record(state, ops=10)
        await state.save_to_gallery()
        path = state._user_dir / "gallery" / "piece_000000.json"
        legacy = json.loads(path.read_text())
        del legacy["versions"], legacy["prompt"]
        path.write_text(json.dumps(legacy))

        data = client.get(f"/public/gallery/{state.user_id}/piece_000000/strokes").json()

        assert data["prompt"] is None
        assert [(x["version"], x["asset_base"], x["ops"]) for x in data["versions"]] == [
            (1, v.asset_base(state.user_id), 0)
        ]

    @pytest.mark.asyncio
    async def test_strokes_piece_has_empty_versions(
        self, public_workspace: tuple[WorkspaceState, TestClient]
    ) -> None:
        state, client = public_workspace
        state.canvas.drawing_style = DrawingStyleType.PLOTTER
        await state.add_strokes([_human_stroke()])
        await state.save_to_gallery()

        data = client.get(f"/public/gallery/{state.user_id}/piece_000000/strokes").json()

        assert data["format"] == "strokes"
        assert data["versions"] == []
        assert data["drawing_style"] == "plotter"
        assert data["stroke_count"] == 1


class TestInitPayload:
    @pytest.mark.asyncio
    async def test_painting_ref_carries_versions_and_prompt(
        self, workspace: WorkspaceState
    ) -> None:
        await workspace.new_canvas(prompt="a stormy sea")
        await _record(workspace, ops=10)
        v2 = await _record(workspace, ops=25)

        ref = _painting_ref(workspace)

        assert ref is not None
        assert ref["version"] == 2 and ref["asset_base"] == v2.asset_base(workspace.user_id)
        assert ref["prompt"] == "a stormy sea"
        assert [v["version"] for v in ref["versions"]] == [1, 2]
        assert all(set(v) == VERSION_REF_KEYS for v in ref["versions"])

    @pytest.mark.asyncio
    async def test_init_carries_title_and_prompt(self, workspace: WorkspaceState) -> None:
        await workspace.new_canvas(prompt="a stormy sea")
        workspace.current_piece_title = "Storm"

        init = await _init_message(workspace, paused=False)

        assert init["type"] == "init"
        assert init["title"] == "Storm"
        assert init["prompt"] == "a stormy sea"
        assert init["painting"] is None


class TestPaintingVersionMessage:
    @pytest.mark.asyncio
    async def test_broadcast_carries_ops(self, workspace: WorkspaceState) -> None:
        agent = MagicMock()
        agent.get_state.return_value = workspace
        broadcaster = MagicMock()
        broadcaster.broadcast = AsyncMock()
        orchestrator = AgentOrchestrator(agent=agent, broadcaster=broadcaster)
        version = await _record(workspace, ops=42)

        await orchestrator._publish_painting_version(version)

        [message] = broadcaster.broadcast.await_args.args
        assert message.type == "painting_version"
        assert message.ops == 42
        assert message.model_dump()["ops"] == 42


class TestProgramAsset:
    def test_serves_painting_py_as_text(
        self, tmp_path: FilePath, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_id = str(uuid.uuid4())
        token = "a" * 32
        vdir = tmp_path / user_id / "paintings" / token
        vdir.mkdir(parents=True)
        (vdir / "painting.py").write_text("cv.ground('#fff')\n")
        (vdir / "human.json").write_text("[]")
        monkeypatch.setattr(paintings_routes, "get_user_dir", lambda uid: tmp_path / uid)
        app = FastAPI()
        app.include_router(paintings_routes.router)
        client = TestClient(app)

        ok = client.get(f"/painting-assets/{user_id}/{token}/painting.py")

        assert ok.status_code == 200
        assert ok.text == "cv.ground('#fff')\n"
        assert ok.headers["content-type"] == "text/plain; charset=utf-8"
        assert ok.headers["cache-control"] == "public, max-age=31536000, immutable"
        base = f"/painting-assets/{user_id}"
        assert client.get(f"{base}/{token}/human.json").status_code == 404
        assert client.get(f"{base}/{token}/other.py").status_code == 404
        assert client.get(f"{base}/{'b' * 32}/painting.py").status_code == 404
        assert client.get(f"{base}/not-a-token/painting.py").status_code == 404
