"""The live performance stream: paintlib writes it, the asset route follows it."""

from __future__ import annotations

import io
import struct
import threading
import time
import uuid
from pathlib import Path as FilePath

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from code_monet.paintlib import Canvas
from code_monet.paintlib.performance import Frame, FrameScanner, read_frames
from code_monet.routes import paintings as paintings_routes

W, H = 160, 120


def _paint(cv: Canvas) -> None:
    cv.stage("ground")
    cv.ground("#d8c8a8")
    cv.stage("sky")
    sky = cv.rect_mask(0, 0, W, 60)
    cv.fill(sky, "#8899bb")
    cv.paint_region(sky, 40, "#556677", length=(8, 14), width=(3, 5))
    cv.stage("figure")
    cv.shape(parts=[("rect", 40, 70, 60, 100, "#442222")])


def _streamed(tmp_path: FilePath) -> tuple[list[Frame], np.ndarray]:
    cv = Canvas(W, H, seed=3)
    with (tmp_path / "performance.bin").open("wb") as f:
        cv.stream_to(f)
        _paint(cv)
        cv.export(tmp_path)
    frames = read_frames((tmp_path / "performance.bin").read_bytes())
    final = np.asarray(Image.open(tmp_path / "final.png").convert("RGB"))
    return frames, final


def _replay(frames: list[Frame]) -> np.ndarray:
    head = frames[0].meta
    pic = np.full((head["height"], head["width"], 3), 255, np.uint8)
    for f in frames:
        if f.meta["kind"] != "chunk":
            continue
        color = np.asarray(Image.open(io.BytesIO(f.color)).convert("RGB"))
        for _t, _d, ax, ay, w, h, x, y in f.patches():
            pic[y : y + h, x : x + w] = color[ay : ay + h, ax : ax + w]
    return pic


class TestStream:
    def test_header_chunks_end(self, tmp_path: FilePath) -> None:
        frames, _ = _streamed(tmp_path)
        kinds = [f.meta["kind"] for f in frames]
        assert kinds[0] == "header" and kinds[-1] == "end"
        assert set(kinds[1:-1]) == {"chunk"}
        assert frames[0].meta == {
            "kind": "header",
            "width": W,
            "height": H,
            "format": 1,
            "base": "blank",
        }
        stages = [f.meta["stage"] for f in frames if f.meta["kind"] == "chunk"]
        assert stages[0] == "ground" and "sky" in stages and stages[-1] == "figure"

    def test_patches_are_one_hand_in_paint_order(self, tmp_path: FilePath) -> None:
        frames, _ = _streamed(tmp_path)
        patches = [p for f in frames if f.meta["kind"] == "chunk" for p in f.patches()]
        assert len(patches) > 30
        for (t0, d0, *_), (t1, *_rest) in zip(patches, patches[1:], strict=False):
            assert t1 >= t0 + d0 - 1e-3, "one brush: a mark starts after the last lifts"
        assert frames[-1].meta["ms"] >= patches[-1][0] + patches[-1][1], "no patch ends late"

    def test_replay_reaches_the_final_picture(self, tmp_path: FilePath) -> None:
        frames, final = _streamed(tmp_path)
        err = np.abs(_replay(frames).astype(int) - final.astype(int))
        assert err.mean() < 4, "lossy colour atlases, but the picture is the final one"

    def test_draw_order_follows_the_stroke(self, tmp_path: FilePath) -> None:
        cv = Canvas(W, H, seed=1)
        with (tmp_path / "performance.bin").open("wb") as f:
            cv.stream_to(f)
            cv.stroke([(10, 60), (150, 60)], 12, "#223344", dry=0)
            cv.export(tmp_path)
        (chunk,) = read_frames((tmp_path / "performance.bin").read_bytes())[1:-1]
        order = np.asarray(Image.open(io.BytesIO(chunk.order)).convert("L")).astype(int)
        _t, _d, ax, ay, w, h, _x, _y = chunk.patches()[0]
        row = order[(ay + h // 2) // 4, ax // 4 : (ax + w) // 4]
        painted = row[row > 0]
        assert painted[0] < painted[-1], "the stroke paints from its start to its end"

    def test_failed_program_ends_with_error(self, tmp_path: FilePath) -> None:
        cv = Canvas(W, H)
        with (tmp_path / "performance.bin").open("wb") as f:
            cv.stream_to(f)
            cv.ground("#123456")
            cv.abort_stream()
        frames = read_frames((tmp_path / "performance.bin").read_bytes())
        assert frames[-1].meta == {"kind": "error"}


class TestFrameScanner:
    def test_detects_end_across_arbitrary_splits(self, tmp_path: FilePath) -> None:
        _streamed(tmp_path)
        data = (tmp_path / "performance.bin").read_bytes()
        for size in (1, 7, 4096):
            scanner = FrameScanner()
            for i in range(0, len(data) - 1, size):
                scanner.feed(data[i : min(i + size, len(data) - 1)])
            assert not scanner.ended, "not over before the last byte"
            scanner.feed(data[-1:])
            assert scanner.ended

    def test_garbage_ends_the_stream(self) -> None:
        scanner = FrameScanner()
        scanner.feed(b"\x03\x00\x00\x00abc")
        scanner.feed(b"\x00\x00\x00\x00" * 3)
        assert scanner.ended
        assert scanner.final is None, "garbage is not a proper end"

    def test_records_how_the_stream_ended(self, tmp_path: FilePath) -> None:
        _streamed(tmp_path)
        scanner = FrameScanner()
        scanner.feed((tmp_path / "performance.bin").read_bytes())
        assert scanner.final == "end"

    def test_a_huge_claimed_length_is_skipped_in_linear_time(self) -> None:
        # The program writes the stream: a part may claim ~2 GB and never arrive.
        head = b'{"kind":"chunk"}'
        scanner = FrameScanner()
        scanner.feed(struct.pack("<I", len(head)) + head + b"\xff\xff\xff\x7f")
        junk = b"x" * (1 << 16)
        t0 = time.perf_counter()
        for _ in range(1024):  # 64 MB
            scanner.feed(junk)
        assert time.perf_counter() - t0 < 2.0
        assert not scanner.ended

    def test_an_oversized_head_ends_the_stream(self) -> None:
        scanner = FrameScanner()
        scanner.feed(b"\xff\xff\xff\x7f")
        assert scanner.ended and scanner.final is None


class TestPerformanceRoute:
    def _client(
        self, tmp_path: FilePath, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[TestClient, FilePath, str]:
        user_id = str(uuid.uuid4())
        token = "c" * 32
        vdir = tmp_path / user_id / "paintings" / token
        vdir.mkdir(parents=True)
        monkeypatch.setattr(paintings_routes, "get_user_dir", lambda uid: tmp_path / uid)
        monkeypatch.setattr(paintings_routes, "_LIVE_POLL_S", 0.01)
        app = FastAPI()
        app.include_router(paintings_routes.router)
        return TestClient(app), vdir, f"/painting-assets/{user_id}/{token}/performance.bin"

    def test_complete_stream_is_immutable(
        self, tmp_path: FilePath, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, vdir, url = self._client(tmp_path, monkeypatch)
        _streamed(vdir)
        res = client.get(url)
        assert res.status_code == 200
        assert res.content == (vdir / "performance.bin").read_bytes()
        assert res.headers["cache-control"] == "public, max-age=31536000, immutable"

    def test_live_stream_follows_the_run_to_its_end(
        self, tmp_path: FilePath, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, vdir, url = self._client(tmp_path, monkeypatch)
        _streamed(tmp_path)
        data = (tmp_path / "performance.bin").read_bytes()
        cut = len(data) // 2
        (vdir / "performance.bin").write_bytes(data[:cut])

        def finish_later() -> None:
            time.sleep(0.2)
            with (vdir / "performance.bin").open("ab") as f:
                f.write(data[cut:])

        threading.Thread(target=finish_later).start()
        res = client.get(url)
        assert res.headers["cache-control"] == "no-store"
        assert res.content == data

    def test_a_stream_that_broke_off_is_not_cached(
        self, tmp_path: FilePath, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, vdir, url = self._client(tmp_path, monkeypatch)
        (vdir / "performance.bin").write_bytes(b"\x03\x00\x00\x00abc" + b"\x00" * 12)
        res = client.get(url)
        assert res.status_code == 200
        assert res.headers["cache-control"] == "no-store"

    def test_a_linked_stream_is_not_served(
        self, tmp_path: FilePath, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A running program can write its output directory; it must not swap the
        # stream for a link to something else.
        client, vdir, url = self._client(tmp_path, monkeypatch)
        _streamed(tmp_path)
        (vdir / "performance.bin").symlink_to(tmp_path / "performance.bin")
        assert client.get(url).status_code == 404
        (vdir / "performance.bin").unlink()
        (vdir / "performance.bin").hardlink_to(tmp_path / "performance.bin")
        assert client.get(url).status_code == 404

    def test_live_stream_stops_when_the_run_is_discarded(
        self, tmp_path: FilePath, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, vdir, url = self._client(tmp_path, monkeypatch)
        _streamed(tmp_path)
        data = (tmp_path / "performance.bin").read_bytes()
        (vdir / "performance.bin").write_bytes(data[:100])

        def discard_later() -> None:
            time.sleep(0.2)
            (vdir / "performance.bin").unlink()

        threading.Thread(target=discard_later).start()
        res = client.get(url)
        assert res.content == data[:100]


class TestBrushPlans:
    """Area ops are laid in by planned strokes whose union is exactly their pixels."""

    def _region(self) -> tuple[np.ndarray, np.ndarray]:
        yy, xx = np.mgrid[0:200, 0:600]
        inside = (xx - 300) ** 2 / 300**2 + (yy - 100) ** 2 / 100**2 < 1
        ys, xs = np.nonzero(inside)
        return xs, ys

    def test_lay_in_covers_every_pixel_with_broad_strokes(self) -> None:
        from code_monet.paintlib import brushplan

        xs, ys = self._region()
        plan = brushplan.plan("lay", xs, ys, seed=1)
        assert len(plan.strokes) > 4, "a region is laid in by several strokes"
        assert plan.labels.min() == 0 and plan.labels.max() == len(plan.strokes) - 1
        assert len(np.unique(plan.labels)) == len(plan.strokes), "no empty strokes"
        assert ((plan.frac >= 0) & (plan.frac <= 1)).all()
        # A stroke is a local band, not scattered pixels.
        for k in range(len(plan.strokes)):
            sel = plan.labels == k
            assert np.ptp(ys[sel]) < 120 and np.ptp(xs[sel]) < 450

    def test_lay_in_travels_along_each_stroke(self) -> None:
        from code_monet.paintlib import brushplan

        xs, ys = self._region()
        plan = brushplan.plan("lay", xs, ys, seed=2)
        k = int(np.bincount(plan.labels).argmax())
        sel = plan.labels == k
        corr = np.corrcoef(xs[sel], plan.frac[sel])[0, 1]
        assert abs(corr) > 0.8, "draw order runs along the stroke"

    def test_shape_is_outlined_before_it_is_filled(self) -> None:
        from code_monet.paintlib import brushplan

        ys, xs = np.nonzero(np.ones((60, 80), bool))
        plan = brushplan.plan("shape", xs, ys, seed=3)
        edge = (xs < 3) | (xs > 76) | (ys < 3) | (ys > 56)
        assert plan.labels[edge].max() < plan.labels[~edge].min()

    def test_priming_is_instant(self, tmp_path: FilePath) -> None:
        frames, _ = _streamed(tmp_path)
        first = frames[1]
        assert first.meta["stage"] == "ground"
        t, dur, *_ = first.patches()[0]
        assert (t, dur) == (0.0, 0.0), "the performance starts on the primed canvas"


class TestPainterOrder:
    def test_marks_are_laid_patch_by_patch_not_scattered(self) -> None:
        cv = Canvas(800, 600, seed=4)
        pts: list[tuple[float, float]] = []
        original = cv._record_mark

        def spy(op: list[float]) -> None:
            pts.append(((op[2] + op[4]) / 2, (op[3] + op[5]) / 2))  # the dab's centre
            original(op)

        cv._record_mark = spy  # type: ignore[method-assign]
        cv.paint_region(cv.rect_mask(0, 0, 800, 600), 600, "#335577", length=(10, 20), width=(4, 8))
        p = np.array(pts)
        step = np.hypot(*np.diff(p, axis=0).T)
        shuffled = p[np.random.default_rng(0).permutation(len(p))]
        random_step = np.hypot(*np.diff(shuffled, axis=0).T)
        assert np.median(step) < 0.2 * np.median(random_step)


class TestRegionMarks:
    """paint_region's marks are diffed in groups, yet each is still its own stroke."""

    def test_marks_are_recorded_in_groups_one_stroke_each(self, tmp_path: FilePath) -> None:
        cv = Canvas(W, H, seed=5)
        diffs = 0
        original = cv._performance._take_changes

        def count(*args: object) -> tuple[np.ndarray, np.ndarray]:
            nonlocal diffs
            diffs += 1
            return original(*args)  # type: ignore[arg-type]

        with (tmp_path / "performance.bin").open("wb") as f:
            cv.stream_to(f)
            cv._performance._take_changes = count  # type: ignore[method-assign]
            laid = cv.paint_region(
                cv.rect_mask(0, 0, W, H), 120, "#335577", length=(8, 14), width=(3, 5)
            )
            cv._performance._take_changes = original  # type: ignore[method-assign]
            cv.export(tmp_path)
        frames = read_frames((tmp_path / "performance.bin").read_bytes())
        patches = sum(len(f.patches()) for f in frames if f.meta["kind"] == "chunk")

        assert laid > 100
        assert diffs <= laid // 10, "marks share a diff instead of one each"
        # Overpainted marks can vanish; the rest each land as their own timed stroke.
        assert laid * 0.8 <= patches <= laid + 10
