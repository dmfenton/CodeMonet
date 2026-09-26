"""Painting programs are untrusted: the run gets no server environment, and only
server-written version files are read back or published."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path as FilePath

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from code_monet.program_painting import PaintFailure, run_painting_program
from code_monet.routes import paintings as paintings_routes
from code_monet.types import DrawingStyleType
from code_monet.workspace import WorkspaceState
from code_monet.workspace.assets import version_asset

TOKEN = "a" * 32

# Fails on purpose so the run reports what the program saw.
PROBE = """
import json, os, sys
seen = {
    "env": dict(os.environ),
    "cwd": os.getcwd(),
    "isolated": sys.flags.isolated,
    "modules": sorted(m for m in sys.modules if m.startswith("code_monet")),
}
raise RuntimeError("PROBE " + json.dumps(seen))
"""


@pytest.fixture
def workspace(tmp_path: FilePath) -> WorkspaceState:
    user_dir = tmp_path / str(uuid.uuid4())
    user_dir.mkdir()
    state = WorkspaceState(user_id=user_dir.name, user_dir=user_dir)
    state._loaded = True
    state.canvas.width, state.canvas.height = 40, 30
    state.canvas.drawing_style = DrawingStyleType.PAINT
    return state


class TestPaintEnvironment:
    @pytest.mark.asyncio
    async def test_program_sees_no_server_environment(
        self, workspace: WorkspaceState, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("JWT_SECRET", "jwt-canary")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-canary")
        monkeypatch.setenv("PYTHONPATH", "/nonexistent")
        workspace.studio_program.parent.mkdir(parents=True)
        workspace.studio_program.write_text(PROBE)

        result = await run_painting_program(workspace)

        assert isinstance(result, PaintFailure)
        assert "PROBE" in result.error
        assert "canary" not in result.error
        seen = json.loads(result.error.split("PROBE ", 1)[1].splitlines()[0])
        seen["env"].pop("__CF_USER_TEXT_ENCODING", None)  # added by macOS to every process
        assert set(seen["env"]) == {"PATH", "HOME", "TMPDIR", "LANG"}
        assert seen["env"]["PATH"] == os.defpath
        assert seen["isolated"] == 1
        # Only the paint library: no server config (which loads secrets) or SDK.
        assert all(
            m == "code_monet" or m.startswith("code_monet.paintlib") for m in seen["modules"]
        )
        run_dir = FilePath(seen["env"]["HOME"])
        assert seen["env"]["TMPDIR"] == str(run_dir)
        assert FilePath(seen["cwd"]).resolve() == run_dir.resolve()
        assert run_dir.name.startswith("paint-run-")
        assert not run_dir.exists()


def _version_dir(user_dir: FilePath, token: str = TOKEN) -> FilePath:
    vdir = user_dir / "paintings" / token
    vdir.mkdir(parents=True)
    return vdir


class TestVersionAsset:
    def test_regular_file_is_returned(self, tmp_path: FilePath) -> None:
        user_dir = tmp_path / "u"
        (_version_dir(user_dir) / "final.png").write_bytes(b"png")

        assert (
            version_asset(user_dir, TOKEN, "final.png")
            == user_dir / "paintings" / TOKEN / "final.png"
        )

    def test_user_dir_behind_server_link_is_allowed(self, tmp_path: FilePath) -> None:
        real = tmp_path / "volume" / "u"
        (_version_dir(real) / "final.png").write_bytes(b"png")
        (tmp_path / "data").symlink_to(tmp_path / "volume")

        assert version_asset(tmp_path / "data" / "u", TOKEN, "final.png") is not None

    def test_missing_file_is_refused(self, tmp_path: FilePath) -> None:
        _version_dir(tmp_path / "u")

        assert version_asset(tmp_path / "u", TOKEN, "final.png") is None

    def test_symlinked_file_is_refused_even_within_the_version(self, tmp_path: FilePath) -> None:
        vdir = _version_dir(tmp_path / "u")
        (vdir / "reveal.json").write_text("{}")
        (vdir / "final.png").symlink_to(vdir / "reveal.json")

        assert version_asset(tmp_path / "u", TOKEN, "final.png") is None

    def test_symlinked_version_directory_is_refused(self, tmp_path: FilePath) -> None:
        elsewhere = _version_dir(tmp_path / "elsewhere")
        (elsewhere / "final.png").write_bytes(b"png")
        user_dir = tmp_path / "u"
        (user_dir / "paintings").mkdir(parents=True)
        (user_dir / "paintings" / TOKEN).symlink_to(elsewhere)

        assert version_asset(user_dir, TOKEN, "final.png") is None

    def test_symlinked_paintings_directory_is_refused(self, tmp_path: FilePath) -> None:
        (_version_dir(tmp_path / "elsewhere") / "final.png").write_bytes(b"png")
        user_dir = tmp_path / "u"
        user_dir.mkdir()
        (user_dir / "paintings").symlink_to(tmp_path / "elsewhere" / "paintings")

        assert version_asset(user_dir, TOKEN, "final.png") is None

    def test_hard_link_is_refused(self, tmp_path: FilePath) -> None:
        secret = tmp_path / "code_monet.db"
        secret.write_bytes(b"sqlite")
        vdir = _version_dir(tmp_path / "u")
        os.link(secret, vdir / "final.png")

        assert version_asset(tmp_path / "u", TOKEN, "final.png") is None

    def test_path_escape_is_refused(self, tmp_path: FilePath) -> None:
        user_dir = tmp_path / "u"
        _version_dir(user_dir)
        (tmp_path / "secret.png").write_bytes(b"png")

        assert version_asset(user_dir, "..", "../../secret.png") is None


class TestAssetReaders:
    def test_route_refuses_hard_linked_asset(
        self, tmp_path: FilePath, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_id = str(uuid.uuid4())
        vdir = _version_dir(tmp_path / user_id)
        (vdir / "reveal.json").write_text("{}")
        secret = tmp_path / "code_monet.db"
        secret.write_bytes(b"sqlite")
        os.link(secret, vdir / "painting.py")
        monkeypatch.setattr(paintings_routes, "get_user_dir", lambda uid: tmp_path / uid)
        app = FastAPI()
        app.include_router(paintings_routes.router)
        client = TestClient(app)
        base = f"/painting-assets/{user_id}/{TOKEN}"

        assert client.get(f"{base}/reveal.json").status_code == 200
        assert client.get(f"{base}/painting.py").status_code == 404

    def test_gallery_raster_ignores_symlinked_final(
        self, workspace: WorkspaceState, tmp_path: FilePath
    ) -> None:
        other = tmp_path / "other.png"
        other.write_bytes(b"png")
        vdir = workspace.paintings_dir / TOKEN
        vdir.mkdir(parents=True)
        (vdir / "final.png").symlink_to(other)

        assert workspace.raster_final({"image_token": TOKEN}) is None
        (vdir / "final.png").unlink()
        (vdir / "final.png").write_bytes(b"png")
        assert workspace.raster_final({"image_token": TOKEN}) == (TOKEN, str(vdir / "final.png"))
