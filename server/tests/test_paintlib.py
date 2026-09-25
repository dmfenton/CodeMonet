"""Tests for the pixel paint library (code_monet.paintlib)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from code_monet.paintlib import Canvas, cellular, fbm, mix, rgb, smoothstep

W, H = 160, 120


def _canvas(seed: int = 3) -> Canvas:
    cv = Canvas(W, H, seed=seed)
    cv.stage("ground")
    cv.ground("#d8c8a8")
    return cv


def _ops(cv: Canvas) -> list[list[Any]]:
    return cv._stages[-1].ops


def _check_op(op: list[Any]) -> None:
    kind = op[0]
    assert kind in ("s", "a")
    assert all(isinstance(v, int | float) for v in op[1:])
    if kind == "a":
        assert len(op) == 5
        x0, y0, x1, y1 = op[1:]
        assert 0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H
    else:
        pts = op[2:]
        assert op[1] > 0
        assert len(pts) % 2 == 0 and 4 <= len(pts) <= 16


def _paint_study(cv: Canvas) -> None:
    """A tiny painting touching every paint operation."""
    sky = cv.rect_mask(0, 0, W, 60)
    guide = cv.vgradient([(0, "#5d7390"), (120, "#e8d9b4")])
    ang = cv.vortex_angles(80, 60, squash=1.4)
    cv.stage("sky")
    cv.fill(sky, guide, alpha=0.8)
    cv.paint_region(sky, 60, guide, angle=ang, brush="flow", length=(20, 40), width=(3, 6))
    cv.smear(sky, ang, length=12)
    cv.stage("land")
    land = 1 - sky
    cv.paint_region(land, 80, guide, angle=0.3, length=(8, 14), width=(3, 5))
    cv.paint_region(land, 40, "#557744", angle=-1.0, brush="patch", length=(8, 12), width=(3, 4))
    cv.glaze(cv.ellipse_mask(100, 90, 20, 10), "#8899bb", alpha=0.5)
    cv.stage("figure")
    cv.shape(
        parts=[
            ("poly", [(40, 80), (46, 80), (46, 96), (40, 96)], "#442222"),
            ("ellipse", 43, 77, 3, 3, "#ddbb99"),
        ],
        model=0.4,
        reflect=0.3,
    )
    cv.sign(W - 30, H - 6, size=14)


class TestExport:
    """export writes keyframes, final, preview, and a well-formed reveal log."""

    def test_files_and_reveal_schema(self, tmp_path: Path) -> None:
        cv = _canvas()
        _paint_study(cv)
        info = cv.export(tmp_path)

        reveal = json.loads((tmp_path / "reveal.json").read_text())
        assert reveal["width"] == W and reveal["height"] == H
        assert info["width"] == W and info["height"] == H
        kfs = reveal["keyframes"]
        assert [k["label"] for k in kfs] == info["stages"] == ["ground", "sky", "land", "figure"]
        assert info["ops"] == sum(len(k["ops"]) for k in kfs)
        for i, kf in enumerate(kfs):
            assert kf["image"] == f"kf_{i:02d}.jpg"
            assert kf["ops"], "every keyframe carries at least one reveal op"
            for op in kf["ops"]:
                _check_op(op)
            with Image.open(tmp_path / kf["image"]) as im:
                assert im.size == (W, H)
        with Image.open(tmp_path / "final.png") as im:
            assert im.size == (W, H) and im.mode == "RGB"
        with Image.open(tmp_path / "preview.jpg") as im:
            assert im.size == (W, H)

    def test_preview_is_downscaled(self, tmp_path: Path) -> None:
        cv = Canvas(1400, 700, seed=1)
        cv.stage("ground")
        cv.ground("#aabbcc")
        cv.export(tmp_path, preview_width=700)
        with Image.open(tmp_path / "preview.jpg") as im:
            assert im.size == (700, 350)

    def test_final_matches_last_keyframe(self, tmp_path: Path) -> None:
        cv = _canvas()
        _paint_study(cv)
        cv.export(tmp_path)
        final = np.asarray(Image.open(tmp_path / "final.png"), np.float32)
        last = np.asarray(Image.open(tmp_path / "kf_03.jpg"), np.float32)
        assert np.abs(final - last).mean() < 3.0


MaskOp = Callable[[Canvas], object]
_mask_ops: dict[str, MaskOp] = {
    "fill": lambda cv: cv.fill(cv.rect_mask(10, 10, 60, 50), "#335577", rim=0.1, thick=0.3),
    "glaze": lambda cv: cv.glaze(cv.rect_mask(10, 10, 60, 50), "#8899aa", mottle=0.02),
    "wash": lambda cv: cv.wash(
        cv.poly_mask([(10, 10), (80, 20), (40, 70)], wobble=2), "#ffeecc", bloom=0.5
    ),
    "blur": lambda cv: cv.blur(cv.rect_mask(10, 10, 60, 50), 2.0),
    "smear": lambda cv: cv.smear(cv.rect_mask(10, 10, 60, 50), 0.5, length=10),
    "striate": lambda cv: cv.striate(cv.rect_mask(10, 10, 60, 50), cv.vortex_angles(40, 40)),
    "crackle": lambda cv: cv.crackle(0.05),
    "stroke": lambda cv: cv.stroke([(10, 10), (60, 30), (100, 20)], 8, "#aa3322", dry=0.4),
    "knife": lambda cv: cv.stroke([(10, 60), (70, 70)], 12, "#fffaf0", knife=True),
    "glaze_stroke": lambda cv: cv.stroke([(10, 90), (90, 100)], 10, "#665544", glaze=True),
    "dab": lambda cv: cv.dab(50, 50, 0.4, 30, 10, "#446633", curve=0.2),
    "dab_round": lambda cv: cv.dab(50, 50, 0.4, 30, 10, "#446633", tip="round"),
    "paint_region": lambda cv: cv.paint_region(
        cv.rect_mask(0, 0, W, H), 30, "#557799", length=(8, 16)
    ),
    "paint_region_patch": lambda cv: cv.paint_region(
        cv.rect_mask(0, 0, W, H), 30, "#557799", brush="patch", length=(8, 16), width=(3, 5)
    ),
    "paint_region_flow": lambda cv: cv.paint_region(
        cv.rect_mask(0, 0, W, H),
        10,
        cv.vgradient([(0, "#123"), (H, "#def")]),
        angle=cv.vortex_angles(80, 60),
        brush="flow",
        length=(20, 40),
        width=(3, 6),
        alpha=(0.4, 0.8),
        dry=(0.1, 0.5),
    ),
    "contour": lambda cv: cv.contour([(5, 60), (80, 40), (150, 70)], 3, "#3a4e8a"),
    "shape": lambda cv: cv.shape(
        polys=[([(20, 20), (40, 20), (30, 50)], "#222")],
        lines=[([(50, 20), (60, 60)], 2, "#333")],
        ellipses=[(90, 40, 8, 5, "#a33")],
        limbs=[([(100, 20), (110, 40), (105, 60)], [4, 3, 2], "#444")],
        model=0.4,
    ),
    "sign": lambda cv: cv.sign(100, 110, size=20),
}


class TestRevealOps:
    """Every paint operation records at least one well-formed reveal op."""

    @pytest.mark.parametrize("name", sorted(_mask_ops))
    def test_op_records(self, name: str) -> None:
        cv = _canvas()
        cv.stage(name)
        before = cv.rgb.copy()
        _mask_ops[name](cv)
        ops = _ops(cv)
        assert ops, f"{name} recorded no reveal op"
        for op in ops:
            _check_op(op)
        assert not np.allclose(before, cv.rgb), f"{name} changed no paint"

    def test_paint_region_records_one_op_per_mark(self) -> None:
        cv = _canvas()
        cv.stage("marks")
        n = cv.paint_region(cv.rect_mask(0, 0, W, H), 50, "#557799", length=(8, 16), width=(3, 6))
        assert n == 50
        assert len(_ops(cv)) == 50
        assert all(op[0] == "s" for op in _ops(cv))

    def test_off_canvas_mark_records_nothing(self) -> None:
        cv = _canvas()
        cv.stage("nothing")
        cv.dab(-500, -500, 0.0, 20, 6, "#000")
        cv.stroke([(-400, -400), (-300, -300)], 5, "#000")
        cv.fill(np.zeros((H, W), np.float32), "#000")
        assert _ops(cv) == []

    def test_smear_field_paints_nothing(self) -> None:
        cv = _canvas()
        cv.stage("design")
        f = cv.smear_field(cv.rect_mask(40, 40, 80, 80), 0.0, length=20)
        assert f.shape == (H, W)
        assert _ops(cv) == []


class TestStages:
    """Stages close into keyframes; long stages auto-split for layered reveals."""

    def test_keyframe_per_stage(self) -> None:
        cv = _canvas()
        cv.stage("a")
        cv.dab(40, 40, 0, 20, 6, "#123")
        cv.stage("empty")
        cv.stage("b")
        cv.dab(80, 40, 0, 20, 6, "#456")
        cv._close_stage()
        assert [k[0] for k in cv._keyframes] == ["ground", "a", "b"]
        for _, img, ops in cv._keyframes:
            assert img.shape == (H, W, 3)
            assert ops

    def test_long_stage_splits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from code_monet.paintlib import canvas as canvas_mod

        monkeypatch.setattr(canvas_mod, "_OPS_PER_KEYFRAME", 10)
        cv = _canvas()
        cv.stage("many")
        cv.paint_region(cv.rect_mask(0, 0, W, H), 35, "#557799", length=(8, 12), width=(3, 5))
        cv._close_stage()
        labels = [k[0] for k in cv._keyframes]
        assert labels.count("many") == 4

    def test_keyframes_capped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from code_monet.paintlib import canvas as canvas_mod

        monkeypatch.setattr(canvas_mod, "_MAX_KEYFRAMES", 3)
        cv = _canvas()
        for i in range(6):
            cv.stage(f"s{i}")
            cv.dab(20 + i * 20, 60, 0, 16, 5, "#345")
        info = cv.export(tmp_path)
        assert len(info["stages"]) == 3
        assert info["stages"][-1] == "s5"
        assert info["ops"] == 7
        assert not (tmp_path / "kf_03.jpg").exists()

    def test_direct_rgb_edit_gets_area_op(self) -> None:
        cv = _canvas()
        cv.stage("manual")
        cv.rgb[10:20, 30:50] = 0.0
        cv._close_stage()
        label, _, ops = cv._keyframes[-1]
        assert label == "manual"
        assert ops == [["a", 30, 10, 50, 20]]


class TestDeterminism:
    """A fixed seed reproduces the painting and its reveal log exactly."""

    def test_same_seed_same_painting(self, tmp_path: Path) -> None:
        outs = []
        for k in range(2):
            cv = _canvas(seed=11)
            _paint_study(cv)
            cv.crackle(0.05)
            info = cv.export(tmp_path / str(k))
            outs.append((cv.finished(), info, (tmp_path / str(k) / "reveal.json").read_text()))
        assert np.array_equal(outs[0][0], outs[1][0])
        assert outs[0][1] == outs[1][1]
        assert outs[0][2] == outs[1][2]

    def test_different_seed_differs(self) -> None:
        a, b = _canvas(seed=1), _canvas(seed=2)
        _paint_study(a)
        _paint_study(b)
        assert not np.array_equal(a.finished(), b.finished())


class TestHelpers:
    def test_rgb_forms(self) -> None:
        assert np.allclose(rgb("#ff8000"), [1.0, 128 / 255, 0.0])
        assert np.allclose(rgb("#f80"), [1.0, 136 / 255, 0.0])
        assert np.allclose(rgb([255, 0, 0]), [1.0, 0.0, 0.0])
        assert np.allclose(rgb([0.2, 0.4, 0.6]), [0.2, 0.4, 0.6])

    def test_mix_broadcasts_colors_over_mask(self) -> None:
        t = np.zeros((H, W), np.float32)
        t[:, W // 2 :] = 1
        out = mix("#000000", np.array([1.0, 1.0, 1.0]), t)
        assert out.shape == (H, W, 3)
        assert out[0, 0].max() == 0 and out[0, -1].min() == 1

    def test_masks_are_bounded(self) -> None:
        cv = Canvas(W, H, seed=0)
        for m in (
            cv.poly_mask([(10, 10), (100, 20), (50, 90)], wobble=3),
            cv.ribbon_mask([(10, 10), (80, 60), (150, 100)], [12, 6, 2]),
            cv.line_mask([(0, 0), (W, H)], 4),
            cv.ellipse_mask(80, 60, 30, 20, soft=10),
            cv.iso_mask(np.sin(cv.xx / 10), 0.0, 2.0),
        ):
            assert m.shape == (H, W) and m.dtype == np.float32
            assert m.min() >= 0.0 and m.max() <= 1.0 and m.max() > 0.5

    def test_scale_field_shrinks_marks(self) -> None:
        cv = _canvas()
        cv.stage("small")
        cv.paint_region(
            cv.rect_mask(0, 0, W, H), 20, "#333", length=(20, 20), width=(6, 6), scale=0.5
        )
        assert all(op[1] == 3.0 for op in _ops(cv))

    def test_bad_brush_rejected(self) -> None:
        cv = _canvas()
        with pytest.raises(ValueError, match="brush"):
            cv.paint_region(cv.rect_mask(0, 0, W, H), 5, "#333", brush="spray")


class TestAgentFriction:
    """Fixes for friction reported by agents painting through the product prompt."""

    def test_rough_edge_confined_to_edge_band(self) -> None:
        cv = Canvas(W, H, seed=5)
        m = cv.ellipse_mask(40, 60, 15, 10)
        out = cv.rough_edge(m, amount=20, scale=8)
        assert out[:, 100:].max() == 0.0, "no specks far from the mask"
        assert out[60, 40] == pytest.approx(1.0), "interior kept"
        assert not np.allclose(out, m), "edge still roughened"

    def test_shape_clip_and_return_mask(self) -> None:
        cv = _canvas()
        cv.stage("shape")
        before = cv.rgb.copy()
        clip = cv.rect_mask(0, 0, 50, H)
        m = cv.shape(parts=[("rect", 20, 20, 90, 60, "#112233")], clip=clip, return_mask=True)
        assert m is not None and m.shape == (H, W)
        assert m[40, 30] == pytest.approx(1.0) and m[40, 70] == 0.0
        assert np.allclose(before[:, 55:], cv.rgb[:, 55:])
        assert cv.shape(parts=[("rect", 20, 20, 90, 60, "#112233")]) is None

    @pytest.mark.parametrize("widths", [6.0, (8.0, 2.0), [8, 6, 4, 2, 1], [5.0] * 7])
    def test_widths_any_length(self, widths: object) -> None:
        cv = Canvas(W, H, seed=0)
        pts = cv.wobble([(10, 10), (80, 60), (150, 100)], 2.0)
        assert len(pts) not in (2, 3, 5, 7)
        m = cv.ribbon_mask(pts, widths)  # type: ignore[arg-type]
        assert m.max() > 0.5
        cv.stage("limb")
        cv.shape(limbs=[(pts, widths, "#333")])  # type: ignore[list-item]
        assert _ops(cv)

    def test_ribbon_pair_tapers(self) -> None:
        cv = Canvas(W, H, seed=0)
        m = cv.ribbon_mask([(10, 60), (150, 60)], (20, 2))
        assert m[:, 20].sum() > 3 * m[:, 140].sum()

    def test_cellular(self) -> None:
        f1, edge = cellular((H, W), 20, seed=3)
        assert f1.shape == edge.shape == (H, W)
        assert f1.min() >= 0 and edge.min() >= 0
        assert 0.02 < (edge < 1.5).mean() < 0.4, "a net of thin borders"
        _, _, ids = cellular((H, W), 20, seed=3, aniso=(3, 1), return_id=True)
        assert len(np.unique(ids)) > 5
        assert np.array_equal(cellular((H, W), 20, seed=3)[0], f1)

    def test_fbm_range_and_aniso(self) -> None:
        f = fbm((H, W), 30, 3, seed=1, aniso=(6, 1))
        assert f.min() >= 0 and f.max() <= 1
        gy, gx = np.gradient(f)
        assert np.abs(gy).mean() > 2 * np.abs(gx).mean(), "horizontal grain"

    def test_smoothstep_reversed(self) -> None:
        assert smoothstep(1.0, 0.0, 0.0) == pytest.approx(1.0)
        assert smoothstep(1.0, 0.0, 1.0) == pytest.approx(0.0)

    def test_vortex_rotation(self) -> None:
        cv = Canvas(W, H, seed=0)
        a0 = cv.vortex_angles(80, 60, squash=2.0)
        a1 = cv.vortex_angles(80, 60, squash=2.0, rotation=0.0)
        assert np.array_equal(a0, a1)
        a2 = cv.vortex_angles(80, 60, squash=2.0, rotation=0.6)
        assert not np.allclose(np.cos(a0), np.cos(a2))
        # a circular vortex is rotation-invariant
        c0 = cv.vortex_angles(80, 60, inward=0.0)
        c1 = cv.vortex_angles(80, 60, inward=0.0, rotation=0.9)
        away = np.hypot(cv.xx - 80, cv.yy - 60) > 1  # the eye itself has no direction
        assert np.allclose(np.cos(c0)[away], np.cos(c1)[away], atol=1e-4)

    def test_sample_points_follow_mask(self) -> None:
        cv = Canvas(W, H, seed=2)
        m = np.zeros((H, W), np.float32)
        m[:, :40] = 1.0
        m[:, 120:] = 0.25
        pts = cv.sample_points(m, 2000, seed=1)
        assert pts.shape == (2000, 2)
        x = pts[:, 0]
        assert ((x >= 40) & (x < 120)).sum() == 0
        left, right = (x < 40).sum(), (x >= 120).sum()
        assert 3 < left / right < 5.5
        assert np.array_equal(pts, cv.sample_points(m, 2000, seed=1))
        assert cv.sample_points(np.zeros((H, W)), 5).shape == (0, 2)

    def test_split_stage_summary_deduped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from code_monet.paintlib import canvas as canvas_mod

        monkeypatch.setattr(canvas_mod, "_OPS_PER_KEYFRAME", 10)
        cv = _canvas()
        cv.stage("many")
        cv.paint_region(cv.rect_mask(0, 0, W, H), 35, "#557799", length=(8, 12), width=(3, 5))
        cv.stage("after")
        cv.dab(40, 40, 0, 12, 4, "#123")
        info = cv.export(tmp_path)
        assert info["stages"] == ["ground", "many", "after"]
        reveal = json.loads((tmp_path / "reveal.json").read_text())
        assert [k["label"] for k in reveal["keyframes"]].count("many") == 4

    def test_contour_pressure_varies_width(self) -> None:
        def widths(pressure: float) -> float:
            cv = _canvas(seed=9)
            cv.stage("c")
            before = cv.rgb.copy()
            cv.contour(
                np.c_[np.arange(10, 150.0), np.full(140, 60.0)],
                6,
                "#223366",
                gap=0,
                pressure=pressure,
            )
            ink = (np.abs(cv.rgb - before).max(axis=2) > 0.05).sum(axis=0)[20:140]
            return float(ink.std())

        assert widths(1.0) > widths(0.0)
