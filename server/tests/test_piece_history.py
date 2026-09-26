"""Piece history: painting versions, prompt, and stroke count across state, gallery, and APIs."""

from __future__ import annotations

import asyncio
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
from code_monet.program_painting import PaintFailure, PaintSuccess, run_painting_program
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
    version = await state.record_painting_version(
        token,
        320,
        240,
        stages if stages is not None else ["ground"],
        ops=ops,
        generation=state.painting_generation,
    )
    assert version is not None
    return version


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

    @pytest.mark.asyncio
    async def test_save_dual_writes_legacy_painting_key(self, workspace: WorkspaceState) -> None:
        await workspace.save()
        data = json.loads((workspace._user_dir / "workspace.json").read_text())
        assert data["painting"] is None and data["painting_versions"] == []

        await _record(workspace, ops=10)
        v2 = await _record(workspace, ops=25)

        data = json.loads((workspace._user_dir / "workspace.json").read_text())
        assert [v["version"] for v in data["painting_versions"]] == [1, 2]
        assert data["painting"] == v2.model_dump()

    @pytest.mark.asyncio
    async def test_malformed_persisted_versions_are_skipped(self, tmp_path: FilePath) -> None:
        user_dir = tmp_path / str(uuid.uuid4())
        user_dir.mkdir()
        good = {
            "piece_number": 3,
            "version": 2,
            "token": "a" * 32,
            "image_width": 320,
            "image_height": 240,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        versions = [{"version": "x"}, "junk", None, good]
        (user_dir / "workspace.json").write_text(
            json.dumps({"piece_number": 3, "painting_versions": versions})
        )

        state = WorkspaceState(user_dir.name, user_dir)
        await state._load_from_file()

        assert [v.version for v in state.painting_versions] == [2]
        assert state.piece_number == 3

    @pytest.mark.asyncio
    async def test_non_list_persisted_versions_load_empty(self, tmp_path: FilePath) -> None:
        user_dir = tmp_path / str(uuid.uuid4())
        user_dir.mkdir()
        (user_dir / "workspace.json").write_text(json.dumps({"painting_versions": {"a": 1}}))

        state = WorkspaceState(user_dir.name, user_dir)
        await state._load_from_file()

        assert state.painting_versions == []

    @pytest.mark.asyncio
    async def test_run_finishing_during_new_canvas_save_is_discarded(
        self, workspace: WorkspaceState
    ) -> None:
        await _record(workspace, ops=5)
        generation = workspace.painting_generation
        original_save = workspace.save_to_gallery
        raced: list[PaintingVersion | None] = []

        async def save_while_run_finishes() -> str | None:
            raced.append(
                await workspace.record_painting_version(
                    "d" * 32, 320, 240, [], ops=2, generation=generation
                )
            )
            return await original_save()

        with patch.object(workspace, "save_to_gallery", save_while_run_finishes):
            await workspace.new_canvas(prompt="next")

        assert raced == [None]
        assert workspace.painting_versions == []
        saved = json.loads((workspace._user_dir / "gallery" / "piece_000000.json").read_text())
        assert [v["ops"] for v in saved["versions"]] == [5]

    @pytest.mark.asyncio
    async def test_stale_generation_is_not_recorded(self, workspace: WorkspaceState) -> None:
        generation = workspace.painting_generation
        await workspace.clear_canvas()

        stale = await workspace.record_painting_version(
            "c" * 32, 320, 240, [], ops=1, generation=generation
        )

        assert stale is None
        assert workspace.painting_versions == []


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
    async def test_malformed_versions_fall_back_to_final_image(
        self, workspace: WorkspaceState, client: TestClient
    ) -> None:
        v = await _record(workspace, ops=10)
        await workspace.save_to_gallery()
        path = workspace._user_dir / "gallery" / "piece_000000.json"
        piece = json.loads(path.read_text())
        piece["versions"] = [{"version": "not-a-number"}, "junk"]
        path.write_text(json.dumps(piece))

        response = client.get("/gallery/0/strokes")

        assert response.status_code == 200
        data = response.json()
        assert [(x["version"], x["asset_base"]) for x in data["versions"]] == [
            (1, v.asset_base(workspace.user_id))
        ]
        assert data["stroke_count"] == 0

    @pytest.mark.asyncio
    async def test_missing_piece_is_404(self, client: TestClient) -> None:
        assert client.get("/gallery/7/strokes").status_code == 404

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
            mock_repo.list_users_with_public_gallery = AsyncMock(return_value=[user])
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
    async def test_listing_includes_drawing_style(
        self, public_workspace: tuple[WorkspaceState, TestClient]
    ) -> None:
        state, client = public_workspace
        await _record(state, ops=10)
        await state.save_to_gallery()

        [entry] = client.get("/public/gallery").json()

        assert entry["drawing_style"] == "paint"
        assert entry["stroke_count"] == 10

    @pytest.mark.asyncio
    async def test_listing_skips_unreadable_piece(
        self, public_workspace: tuple[WorkspaceState, TestClient]
    ) -> None:
        state, client = public_workspace
        await _record(state, ops=10)
        await state.save_to_gallery()
        bad = {"piece_number": "abc", "versions": ["junk"], "strokes": 5}
        (state._user_dir / "gallery" / "piece_000009.json").write_text(json.dumps(bad))

        response = client.get("/public/gallery")

        assert response.status_code == 200
        assert [e["piece_number"] for e in response.json()] == [0]

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
        assert "prompt" not in ref  # Clients read the top-level init.prompt
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
        assert ok.headers["x-content-type-options"] == "nosniff"
        base = f"/painting-assets/{user_id}"
        assert client.get(f"{base}/{token}/human.json").status_code == 404
        assert client.get(f"{base}/{token}/other.py").status_code == 404
        assert client.get(f"{base}/{'b' * 32}/painting.py").status_code == 404
        assert client.get(f"{base}/not-a-token/painting.py").status_code == 404

    def test_refuses_symlinked_assets(
        self, tmp_path: FilePath, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_id = str(uuid.uuid4())
        secret = tmp_path / "secret.txt"
        secret.write_text("TOKEN=hunter2\n")
        paintings = tmp_path / user_id / "paintings"
        vdir = paintings / ("a" * 32)
        vdir.mkdir(parents=True)
        (vdir / "painting.py").symlink_to(secret)
        (vdir / "final.png").symlink_to(secret)
        real = tmp_path / "elsewhere"
        real.mkdir()
        (real / "reveal.json").write_text("{}")
        (paintings / ("b" * 32)).symlink_to(real)
        monkeypatch.setattr(paintings_routes, "get_user_dir", lambda uid: tmp_path / uid)
        app = FastAPI()
        app.include_router(paintings_routes.router)
        client = TestClient(app)
        base = f"/painting-assets/{user_id}"

        assert client.get(f"{base}/{'a' * 32}/painting.py").status_code == 404
        assert client.get(f"{base}/{'a' * 32}/final.png").status_code == 404
        assert client.get(f"{base}/{'b' * 32}/reveal.json").status_code == 404


class TestGalleryRobustness:
    def test_malformed_versions_read_as_final_image(self) -> None:
        data = {
            "piece_number": 2,
            "strokes": [{}],
            "image_token": "d" * 32,
            "image_width": 1600,
            "image_height": 1200,
            "versions": [{"version": 1, "token": 5}, None],
        }

        fields = piece_detail_fields(data, "user-1", raster=True)

        assert [v["asset_base"] for v in fields["versions"]] == [
            f"/painting-assets/user-1/{'d' * 32}/"
        ]
        assert fields["stroke_count"] == 1

    def test_unusable_final_image_yields_no_versions(self) -> None:
        data = {"image_token": "d" * 32, "image_width": "wide", "versions": "junk"}

        assert piece_detail_fields(data, "user-1", raster=True)["versions"] == []
        assert piece_stroke_count({"versions": ["junk"], "strokes": "junk"}) == 0

    @pytest.mark.asyncio
    async def test_scan_skips_bad_piece(self, workspace: WorkspaceState) -> None:
        await workspace.add_strokes([_human_stroke()])
        await workspace.save_to_gallery()
        gallery = workspace._user_dir / "gallery"
        (gallery / "piece_000008.json").write_text(json.dumps({"piece_number": "abc"}))
        (gallery / "piece_000009.json").write_text(
            json.dumps({"piece_number": 9, "versions": ["junk"], "width": "wide"})
        )

        entries = await workspace.list_gallery()

        assert [e.piece_number for e in entries] == [0]


class _FakeProc:
    """Paint-runner stand-in: runs `during` while "painting", then exports and succeeds."""

    returncode = 0

    def __init__(self, during: object, args: tuple[str, ...]) -> None:
        self._during = during
        self._out_dir = FilePath(args[args.index("--out") + 1])

    async def communicate(self) -> tuple[bytes, bytes]:
        await self._during()  # type: ignore[operator]
        keyframes = [{"label": "ground", "image": "kf_00.jpg", "ops": [["a", 0, 0, 1, 1]] * 3}]
        reveal = {"width": 320, "height": 240, "keyframes": keyframes}
        (self._out_dir / "reveal.json").write_text(json.dumps(reveal))
        return b"", b""


class TestPaintRunGuards:
    def _program(self, state: WorkspaceState, source: str = "cv.ground('#fff')\n") -> None:
        state.studio_program.parent.mkdir(parents=True, exist_ok=True)
        state.studio_program.write_text(source)

    def _fake_runner(self, monkeypatch: pytest.MonkeyPatch, during: object) -> list[list[str]]:
        calls: list[list[str]] = []

        async def create_subprocess_exec(*args: str, **_: object) -> _FakeProc:
            calls.append(list(args))
            return _FakeProc(during, args)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)
        return calls

    @pytest.mark.asyncio
    async def test_uninterrupted_run_records_published_program(
        self, workspace: WorkspaceState, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._program(workspace, "cv.ground('#abc')\n")

        async def nothing() -> None:
            return None

        calls = self._fake_runner(monkeypatch, nothing)

        result = await run_painting_program(workspace)

        assert isinstance(result, PaintSuccess), result
        published = workspace.paintings_dir / result.version.token / "painting.py"
        assert published.read_text() == "cv.ground('#abc')\n"
        [args] = calls
        run_program = FilePath(args[args.index("--program") + 1])
        assert run_program != published
        assert not run_program.exists()  # throwaway execution copy is cleaned up
        assert workspace.painting_versions == [result.version]

    @pytest.mark.asyncio
    async def test_program_rewriting_itself_cannot_change_what_is_published(
        self, workspace: WorkspaceState, tmp_path: FilePath, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._program(workspace, "cv.ground('#abc')\n")
        secret = tmp_path / "secret.txt"
        secret.write_text("TOKEN=hunter2\n")
        calls: list[list[str]] = []

        async def tamper() -> None:
            args = calls[-1]
            FilePath(args[args.index("--program") + 1]).write_text("SUBSTITUTED\n")
            out_dir = FilePath(args[args.index("--out") + 1])
            (out_dir / "painting.py").symlink_to(secret)

        async def create_subprocess_exec(*args: str, **_: object) -> _FakeProc:
            calls.append(list(args))
            return _FakeProc(tamper, args)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)

        result = await run_painting_program(workspace)

        assert isinstance(result, PaintSuccess), result
        published = workspace.paintings_dir / result.version.token / "painting.py"
        assert not published.is_symlink()
        assert published.read_text() == "cv.ground('#abc')\n"
        assert secret.read_text() == "TOKEN=hunter2\n"

    @pytest.mark.parametrize("reset", ["clear", "new_canvas"])
    @pytest.mark.asyncio
    async def test_run_finishing_after_reset_is_discarded(
        self, workspace: WorkspaceState, monkeypatch: pytest.MonkeyPatch, reset: str
    ) -> None:
        self._program(workspace)

        async def reset_canvas() -> None:
            if reset == "clear":
                await workspace.clear_canvas()
            else:
                await workspace.new_canvas(prompt="next piece")

        self._fake_runner(monkeypatch, reset_canvas)

        result = await run_painting_program(workspace)

        assert isinstance(result, PaintFailure)
        assert result.error == (
            "The canvas was reset while this program ran; its result was discarded."
        )
        assert workspace.painting_versions == []
        assert list(workspace.paintings_dir.iterdir()) == []

    @pytest.mark.asyncio
    async def test_symlinked_program_is_refused(
        self, workspace: WorkspaceState, tmp_path: FilePath, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = tmp_path / "secret.py"
        secret.write_text("SECRET = 1\n")
        workspace.studio_program.parent.mkdir(parents=True, exist_ok=True)
        workspace.studio_program.symlink_to(secret)
        calls = self._fake_runner(monkeypatch, AsyncMock())

        result = await run_painting_program(workspace)

        assert isinstance(result, PaintFailure)
        assert "symlink" in result.error
        assert calls == []
        assert not workspace.paintings_dir.exists() or not any(workspace.paintings_dir.iterdir())
