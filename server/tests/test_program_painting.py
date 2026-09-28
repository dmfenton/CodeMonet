"""Program painting: running the agent's program, versions, assets, gallery."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path as FilePath

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from code_monet import sandbox
from code_monet.paintlib.performance import read_frames
from code_monet.program_painting import (
    LiveFailed,
    LiveStarted,
    PaintFailure,
    PaintLive,
    PaintSuccess,
    run_painting_program,
)
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

# A revision: paints over the canvas the previous version left.
REVISION = """
cv.stage("accent")
cv.stroke([(40, 180), (280, 180)], 14, "#aa2222", dry=0)
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
        sky = [op[0] for kf in reveal["keyframes"] if kf["label"] == "sky" for op in kf["ops"]]
        assert sky[0] == "a" and sky[1] == "s"
        assert v.ops == sum(len(kf["ops"]) for kf in reveal["keyframes"]) > 0
        assert result.preview_jpeg == (out / "preview.jpg").read_bytes()
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
        _write_program(workspace, REVISION)
        second = await run_painting_program(workspace)
        assert isinstance(second, PaintSuccess)
        assert second.version.version == 2


class TestLivePerformance:
    @pytest.mark.asyncio
    async def test_run_streams_live_into_its_version(self, workspace: WorkspaceState) -> None:
        _write_program(workspace, PROGRAM)
        events: list[PaintLive] = []

        async def on_live(event: PaintLive) -> None:
            events.append(event)
            assert workspace.live_painting == event, "joining viewers can find the live run"
            stream = workspace.paintings_dir / event.token / "performance.bin"
            assert stream.is_file(), "the stream exists when it is announced"

        result = await run_painting_program(workspace, on_live=on_live)

        assert isinstance(result, PaintSuccess)
        assert events == [LiveStarted(workspace.piece_number, result.version.token, 320, 240)]
        assert workspace.live_painting is None
        stream = workspace.paintings_dir / result.version.token / "performance.bin"
        frames = read_frames(stream.read_bytes())
        assert frames[0].meta["kind"] == "header" and frames[-1].meta["kind"] == "end"

    @pytest.mark.asyncio
    async def test_failed_run_tells_viewers_to_drop_it(self, workspace: WorkspaceState) -> None:
        _write_program(workspace, "cv.ground('#fff')\nraise ValueError('bad brush')")
        events: list[PaintLive] = []

        async def on_live(event: PaintLive) -> None:
            events.append(event)

        result = await run_painting_program(workspace, on_live=on_live)

        assert isinstance(result, PaintFailure)
        started, failed = events
        assert isinstance(started, LiveStarted)
        assert failed == LiveFailed(started.piece_number, started.token)
        assert not (workspace.paintings_dir / started.token).exists()
        assert workspace.live_painting is None

    @pytest.mark.asyncio
    async def test_cancelled_run_stops_and_tells_viewers(
        self, workspace: WorkspaceState, tmp_path: FilePath
    ) -> None:
        """A turn interrupted mid-paint kills the runner and drops the live stream."""
        import os

        pid_file = tmp_path / "runner.pid"
        _write_program(
            workspace,
            f"import os, time\nopen({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
            "time.sleep(60)",
        )
        events: list[PaintLive] = []

        async def on_live(event: PaintLive) -> None:
            events.append(event)

        run = asyncio.create_task(run_painting_program(workspace, on_live=on_live))
        for _ in range(200):
            if pid_file.exists() and pid_file.read_text():
                break
            await asyncio.sleep(0.05)
        pid = int(pid_file.read_text())

        run.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run

        started = events[0]
        assert isinstance(started, LiveStarted)
        out_dir = workspace.paintings_dir / started.token
        for _ in range(100):
            if len(events) == 2 and not out_dir.exists():
                break
            await asyncio.sleep(0.05)
        assert events[1] == LiveFailed(started.piece_number, started.token)
        assert not out_dir.exists()
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        assert workspace.live_painting is None


class TestRevisions:
    """A revision paints over the current canvas: its strokes are the new ones."""

    @pytest.mark.asyncio
    async def test_revision_paints_over_the_current_canvas(self, workspace: WorkspaceState) -> None:
        _write_program(workspace, PROGRAM)
        first = await run_painting_program(workspace)
        assert isinstance(first, PaintSuccess)
        v1 = workspace.paintings_dir / first.version.token
        assert workspace.studio_program.read_text().startswith("# Version 2 paints over")
        assert (workspace.studio_program.parent / "versions" / "v1.py").read_text() == PROGRAM

        _write_program(workspace, REVISION)
        second = await run_painting_program(workspace)

        assert isinstance(second, PaintSuccess)
        v2 = workspace.paintings_dir / second.version.token
        before = np.asarray(Image.open(v1 / "final.png").convert("RGB")).astype(int)
        after = np.asarray(Image.open(v2 / "final.png").convert("RGB")).astype(int)
        changed = np.abs(after - before).max(axis=2) > 2
        assert changed.any() and changed.mean() < 0.2, "only the new stroke changed"
        assert changed[:, :30].sum() == 0, "the rest of the picture is kept"
        frames = read_frames((v2 / "performance.bin").read_bytes())
        assert frames[0].meta["base"] == "previous"
        stages = {f.meta["stage"] for f in frames if f.meta["kind"] == "chunk"}
        assert stages == {"accent"}, "the performance is the revision's strokes only"
        assert second.version.ops > first.version.ops, "the picture's marks accumulate"
        assert json.loads((v2 / "reveal.json").read_text())["continues"] is True
        assert not (v1 / "canvas.npz").exists(), "only the latest canvas is kept"
        assert (v2 / "canvas.npz").is_file()

    @pytest.mark.asyncio
    async def test_a_revision_cannot_erase_the_canvas(self, workspace: WorkspaceState) -> None:
        _write_program(workspace, PROGRAM)
        first = await run_painting_program(workspace)
        assert isinstance(first, PaintSuccess)
        _write_program(workspace, 'cv.stage("ground")\ncv.ground("#203040")\n')

        refused = await run_painting_program(workspace)

        assert isinstance(refused, PaintFailure)
        assert "erasing is not allowed" in refused.error
        assert workspace.painting == first.version, "the picture is unchanged"

    @pytest.mark.asyncio
    async def test_failed_revision_keeps_the_program_to_fix(
        self, workspace: WorkspaceState
    ) -> None:
        _write_program(workspace, PROGRAM)
        assert isinstance(await run_painting_program(workspace), PaintSuccess)
        _write_program(workspace, "raise ValueError('bad brush')")

        failed = await run_painting_program(workspace)

        assert isinstance(failed, PaintFailure)
        assert "bad brush" in workspace.studio_program.read_text()

    @pytest.mark.asyncio
    async def test_new_piece_starts_on_a_blank_canvas(self, workspace: WorkspaceState) -> None:
        _write_program(workspace, PROGRAM)
        assert isinstance(await run_painting_program(workspace), PaintSuccess)
        latest = workspace.paintings_dir / workspace.painting.token  # type: ignore[union-attr]
        await workspace.new_canvas()
        assert not (workspace.studio_program.parent / "versions").exists()
        assert not (latest / "canvas.npz").exists(), "a finished piece keeps no canvas state"
        _write_program(workspace, REVISION)

        fresh = await run_painting_program(workspace)

        assert isinstance(fresh, PaintSuccess)
        out = workspace.paintings_dir / fresh.version.token
        frames = read_frames((out / "performance.bin").read_bytes())
        assert frames[0].meta["base"] == "blank"
        assert json.loads((out / "reveal.json").read_text())["continues"] is False


# The program shares the runner's process: it can print after the runner, end
# the process early, or rewrite the exported files on the way out.
_OUT_DIR = "sys.argv[sys.argv.index('--out') + 1]"
_REWRITE_REVEAL = f"""
import atexit, os, sys
out = {_OUT_DIR}
atexit.register(lambda: open(os.path.join(out, "reveal.json"), "w").write(%r))
"""


class TestRunnerOutput:
    @pytest.mark.asyncio
    async def test_output_after_the_runner_does_not_matter(self, workspace: WorkspaceState) -> None:
        _write_program(
            workspace,
            "import atexit\nprint('{not json')\natexit.register(print, 'late')\n" + PROGRAM,
        )

        result = await run_painting_program(workspace)

        assert isinstance(result, PaintSuccess), result
        assert result.version.stages == ["ground", "sky"]

    @pytest.mark.parametrize("exit_call", ["import sys; sys.exit(0)", "import os; os._exit(0)"])
    @pytest.mark.asyncio
    async def test_exit_before_export_fails_and_cleans_up(
        self, workspace: WorkspaceState, exit_call: str
    ) -> None:
        _write_program(workspace, "print('partial', flush=True)\n" + exit_call + "\n" + PROGRAM)

        result = await run_painting_program(workspace)

        assert isinstance(result, PaintFailure), result
        assert "without exporting" in result.error
        assert "partial" in result.error
        assert list(workspace.paintings_dir.iterdir()) == []
        assert workspace.painting is None

    @pytest.mark.parametrize(
        "reveal",
        [
            "not json",
            "[]",
            '{"width": "320", "height": 240, "keyframes": []}',
            '{"width": 320, "height": 240, "keyframes": [{"label": "sky"}]}',
            '{"width": 1000000, "height": 240, "keyframes": []}',
            '{"width": 320, "height": 240, "keyframes": [{"label": "a", "image": "../x.jpg", "ops": []}]}',
            '{"width": 320, "height": 240, "keyframes": [{"label": "sky", "ops": []}]}',
            '{"width": 320, "height": 240, "keyframes": [{"label": "a", "image": "kf_00.jpg", '
            '"ops": [["s", 0, 1, 1]]}]}',
            '{"width": 320, "height": 240, "keyframes": [{"label": "a", "image": "kf_00.jpg", '
            '"ops": [["a", 0, 0, 1]]}]}',
            '{"width": 320, "height": 240, "keyframes": [{"label": "a", "image": "kf_00.jpg", '
            '"ops": [{"x": 1}]}]}',
            "[" * 100_000,
        ],
    )
    @pytest.mark.asyncio
    async def test_malformed_reveal_fails_and_cleans_up(
        self, workspace: WorkspaceState, reveal: str
    ) -> None:
        _write_program(workspace, PROGRAM)
        first = await run_painting_program(workspace)
        assert isinstance(first, PaintSuccess)
        _write_program(workspace, _REWRITE_REVEAL % reveal + REVISION)

        result = await run_painting_program(workspace)

        assert isinstance(result, PaintFailure), result
        assert "reveal.json is malformed" in result.error
        assert [p.name for p in workspace.paintings_dir.iterdir()] == [first.version.token]
        assert workspace.painting == first.version

    @pytest.mark.parametrize(
        "replace", ["os.mkfifo(p)", "os.mkdir(p)", "os.symlink('/etc/hosts', p)"]
    )
    @pytest.mark.asyncio
    async def test_reveal_that_is_not_a_regular_file_fails(
        self, workspace: WorkspaceState, replace: str
    ) -> None:
        swap = f"""
import atexit, os, sys
p = os.path.join({_OUT_DIR}, "reveal.json")
atexit.register(lambda: (os.unlink(p), {replace}))
"""
        _write_program(workspace, swap + PROGRAM)

        result = await asyncio.wait_for(run_painting_program(workspace), timeout=60)

        assert isinstance(result, PaintFailure), result
        assert "Could not read the painting's reveal.json" in result.error
        assert list(workspace.paintings_dir.iterdir()) == []

    @pytest.mark.asyncio
    async def test_tampered_human_input_fails_and_cleans_up(
        self, workspace: WorkspaceState
    ) -> None:
        swap = """
import atexit, os, sys
p = sys.argv[sys.argv.index('--human') + 1]
atexit.register(lambda: (os.unlink(p), os.mkdir(p)))
"""
        _write_program(workspace, swap + PROGRAM)

        result = await run_painting_program(workspace)

        assert isinstance(result, PaintFailure), result
        assert list(workspace.paintings_dir.iterdir()) == []

    @pytest.mark.parametrize(
        ("tamper", "message"),
        [
            ("os.unlink(j(out, 'preview.jpg'))", "preview.jpg"),
            (
                "(os.unlink(j(out, 'final.png')), os.symlink('/etc/hosts', j(out, 'final.png')))",
                "final.png is missing or not a regular file",
            ),
            ("os.unlink(j(out, 'kf_00.jpg'))", "kf_00.jpg is missing or not a regular file"),
            (
                "(os.rename(out, out + '.moved'), os.symlink(out + '.moved', out))",
                "output directory was moved or replaced",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_tampered_assets_fail_and_leave_no_version(
        self, workspace: WorkspaceState, tamper: str, message: str
    ) -> None:
        program = f"""
import atexit, os, sys
j = os.path.join
out = {_OUT_DIR}
atexit.register(lambda: {tamper})
"""
        _write_program(workspace, program + PROGRAM)

        result = await run_painting_program(workspace)

        if "os.rename(out" in tamper and sandbox.available():
            # The sandbox refuses renaming the output directory itself (no rights
            # on its parent), so the version is intact and nothing was moved.
            assert isinstance(result, PaintSuccess), result
            assert not any(p.name.endswith(".moved") for p in workspace.paintings_dir.iterdir())
            return
        assert isinstance(result, PaintFailure), result
        assert message in result.error
        left = list(workspace.paintings_dir.iterdir())
        assert all(p.name.endswith(".moved") for p in left)  # only what the program moved
        assert workspace.painting is None


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
        (vdir / "human.json").write_text("[]")
        monkeypatch.setattr(paintings_routes, "get_user_dir", lambda uid: tmp_path / uid)
        app = FastAPI()
        app.include_router(paintings_routes.router)
        client = TestClient(app)

        ok = client.get(f"/painting-assets/{user_id}/{token}/reveal.json")
        assert ok.status_code == 200
        assert "immutable" in ok.headers["cache-control"]
        assert client.get(f"/painting-assets/{user_id}/{token}/human.json").status_code == 404
        assert client.get(f"/painting-assets/{user_id}/{'b' * 32}/reveal.json").status_code == 404
        assert client.get(f"/painting-assets/{user_id}/..%2F..%2Fx/reveal.json").status_code == 404
