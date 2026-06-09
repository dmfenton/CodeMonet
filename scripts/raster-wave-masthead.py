#!/usr/bin/env python3
"""Raster woodblock wave masthead painter.

This is a small drawing tool for hand-building a Hokusai-inspired masthead
with bitmap-native marks: masks, texture, thick ink curves, foam stamps, and
layered ribbons. It intentionally avoids SVG path export as the primary medium.
"""

from __future__ import annotations

import argparse
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

CANVAS_W = 1200
CANVAS_H = 420
SCALE = 3

PAPER = "#fdfbf5"
PAPER_100 = "#f8f3e7"
PAPER_200 = "#efe7d2"
PAPER_300 = "#e2d5b3"
INK = "#1a1d18"
FOREST_900 = "#0f2a1c"
FOREST_800 = "#163a28"
FOREST_700 = "#1f4d34"
FOREST_600 = "#2a6243"
FOREST_500 = "#3a7a53"
FOREST_400 = "#5e9a72"
FOREST_300 = "#94b89e"
FOREST_100 = "#dde7df"
GOLD = "#e8c98a"
SURFER_BOARD = PAPER_100
SURFER_JERSEY = INK
SKY_TAN = "#ead8a9"
SKY_GOLD = "#dec786"
HORIZON_MOSS = "#bfd3bd"

Color = tuple[int, int, int, int]
Point = tuple[float, float]


def rgba(hex_color: str, alpha: int = 255) -> Color:
    value = hex_color.lstrip("#")
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
        alpha,
    )


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def cubic(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 36) -> list[Point]:
    points: list[Point] = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = (
            u * u * u * p0[0]
            + 3 * u * u * t * p1[0]
            + 3 * u * t * t * p2[0]
            + t * t * t * p3[0]
        )
        y = (
            u * u * u * p0[1]
            + 3 * u * u * t * p1[1]
            + 3 * u * t * t * p2[1]
            + t * t * t * p3[1]
        )
        points.append((x, y))
    return points


def catmull(points: list[Point], samples: int = 16, closed: bool = False) -> list[Point]:
    if len(points) < 2:
        return points
    pts = points[:]
    if closed:
        pts = [points[-1], *points, points[0], points[1]]
    else:
        pts = [points[0], *points, points[-1]]
    out: list[Point] = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for j in range(samples):
            t = j / samples
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * (
                (2 * p1[0])
                + (-p0[0] + p2[0]) * t
                + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
            )
            y = 0.5 * (
                (2 * p1[1])
                + (-p0[1] + p2[1]) * t
                + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
            )
            out.append((x, y))
    out.append(points[0] if closed else points[-1])
    return out


def rotate(point: Point, angle: float) -> Point:
    x, y = point
    return (
        x * math.cos(angle) - y * math.sin(angle),
        x * math.sin(angle) + y * math.cos(angle),
    )


class RasterPainter:
    def __init__(self, width: int, height: int, seed: int) -> None:
        self.width = width
        self.height = height
        self.scale = SCALE
        random.seed(seed)
        self.image = Image.new("RGBA", (width * SCALE, height * SCALE), rgba(SKY_TAN))
        self.draw = ImageDraw.Draw(self.image)

    def sp(self, point: Point) -> tuple[int, int]:
        return (round(point[0] * self.scale), round(point[1] * self.scale))

    def sw(self, value: float) -> int:
        return max(1, round(value * self.scale))

    def points(self, points: list[Point]) -> list[tuple[int, int]]:
        return [self.sp(point) for point in points]

    def polygon(self, points: list[Point], fill: str, alpha: int = 255) -> None:
        self.draw.polygon(self.points(points), fill=rgba(fill, alpha))

    def polygon_outline(
        self,
        points: list[Point],
        fill: str,
        outline: str,
        outline_width: float,
        alpha: int = 255,
    ) -> None:
        self.draw.polygon(self.points(points), fill=rgba(fill, alpha))
        self.draw.line(
            self.points([*points, points[0]]),
            fill=rgba(outline, 255),
            width=self.sw(outline_width),
            joint="curve",
        )

    def smooth_polygon(
        self,
        points: list[Point],
        fill: str,
        outline: str | None = None,
        outline_width: float = 1,
        alpha: int = 255,
        closed: bool = True,
    ) -> None:
        sampled = catmull(points, samples=14, closed=closed)
        self.draw.polygon(self.points(sampled), fill=rgba(fill, alpha))
        if outline is not None:
            line = sampled + [sampled[0]]
            self.draw.line(
                self.points(line),
                fill=rgba(outline, 255),
                width=self.sw(outline_width),
                joint="curve",
            )

    def line(
        self,
        points: list[Point],
        color: str,
        width: float,
        alpha: int = 255,
        smooth: bool = True,
    ) -> None:
        sampled = catmull(points, samples=12, closed=False) if smooth else points
        self.draw.line(
            self.points(sampled),
            fill=rgba(color, alpha),
            width=self.sw(width),
            joint="curve",
        )

    def outlined_line(
        self,
        points: list[Point],
        fill: str,
        outline: str,
        width: float,
        outline_width: float,
        alpha: int = 255,
        smooth: bool = True,
    ) -> None:
        self.line(points, outline, width + outline_width * 2, alpha=255, smooth=smooth)
        self.line(points, fill, width, alpha=alpha, smooth=smooth)

    def bezier(
        self,
        p0: Point,
        p1: Point,
        p2: Point,
        p3: Point,
        color: str,
        width: float,
        alpha: int = 255,
    ) -> None:
        self.draw.line(
            self.points(cubic(p0, p1, p2, p3, steps=44)),
            fill=rgba(color, alpha),
            width=self.sw(width),
            joint="curve",
        )

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, fill: str, alpha: int = 255) -> None:
        self.draw.ellipse(
            [
                self.sp((cx - rx, cy - ry)),
                self.sp((cx + rx, cy + ry)),
            ],
            fill=rgba(fill, alpha),
        )

    def ellipse_outline(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        fill: str,
        outline: str,
        outline_width: float,
        alpha: int = 255,
    ) -> None:
        self.ellipse(cx, cy, rx + outline_width, ry + outline_width, outline, 255)
        self.ellipse(cx, cy, rx, ry, fill, alpha)

    def oriented_ellipse_outline(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        angle: float,
        fill: str,
        outline: str,
        outline_width: float,
        alpha: int = 255,
    ) -> None:
        points: list[Point] = []
        for index in range(36):
            t = math.tau * index / 36
            x, y = rotate((math.cos(t) * rx, math.sin(t) * ry), angle)
            points.append((cx + x, cy + y))
        self.smooth_polygon(points, fill, outline=outline, outline_width=outline_width, alpha=alpha)

    def ribbon(
        self,
        center: list[Point],
        widths: list[float],
        fill: str,
        alpha: int = 255,
        outline: str | None = None,
        outline_width: float = 1,
    ) -> None:
        sampled = catmull(center, samples=12, closed=False)
        if len(widths) < len(center):
            widths = [*widths, *([widths[-1]] * (len(center) - len(widths)))]
        expanded_widths: list[float] = []
        for i in range(len(sampled)):
            source = i / max(1, len(sampled) - 1) * (len(widths) - 1)
            low = math.floor(source)
            high = min(len(widths) - 1, low + 1)
            expanded_widths.append(lerp(widths[low], widths[high], source - low))

        left: list[Point] = []
        right: list[Point] = []
        for i, (x, y) in enumerate(sampled):
            prev_point = sampled[max(0, i - 1)]
            next_point = sampled[min(len(sampled) - 1, i + 1)]
            dx = next_point[0] - prev_point[0]
            dy = next_point[1] - prev_point[1]
            length = math.hypot(dx, dy) or 1
            nx = -dy / length
            ny = dx / length
            half = expanded_widths[i] / 2
            left.append((x + nx * half, y + ny * half))
            right.append((x - nx * half, y - ny * half))
        self.smooth_polygon(left + list(reversed(right)), fill, outline, outline_width, alpha)

    def paper_texture(self) -> None:
        arr = np.asarray(self.image).astype(np.int16)
        h, w = arr.shape[:2]
        noise = np.random.default_rng(21).normal(0, 7, (h, w, 1)).astype(np.int16)
        fibers = np.random.default_rng(22).normal(0, 3, (h, 1, 1)).astype(np.int16)
        arr[:, :, :3] = np.clip(arr[:, :, :3] + noise + fibers, 0, 255)
        self.image = Image.fromarray(arr.astype(np.uint8), mode="RGBA")
        self.draw = ImageDraw.Draw(self.image)
        for _ in range(260):
            x = random.uniform(0, self.width)
            y = random.uniform(0, self.height)
            length = random.uniform(12, 90)
            self.line(
                [(x, y), (x + length, y + random.uniform(-2, 2))],
                PAPER_200,
                random.uniform(0.25, 0.9),
                alpha=random.randint(18, 45),
                smooth=False,
            )

    def dry_marks(
        self,
        count: int,
        y_range: tuple[float, float],
        colors: list[str],
        width_range: tuple[float, float],
        length_range: tuple[float, float],
        alpha_range: tuple[int, int],
        angle: float = 0,
        jitter: float = 0.2,
    ) -> None:
        for _ in range(count):
            x = random.uniform(-40, self.width + 40)
            y = random.uniform(*y_range)
            length = random.uniform(*length_range)
            theta = angle + random.uniform(-jitter, jitter)
            color = random.choice(colors)
            width = random.uniform(*width_range)
            alpha = random.randint(*alpha_range)
            self.bezier(
                (x, y),
                (x + length * 0.30, y + random.uniform(-8, 8)),
                (x + length * 0.70, y + random.uniform(-8, 8)),
                (x + math.cos(theta) * length, y + math.sin(theta) * length),
                color,
                width,
                alpha,
            )

    def save(self, path: Path) -> None:
        out = self.image.resize((self.width, self.height), Image.Resampling.LANCZOS)
        out = out.filter(ImageFilter.UnsharpMask(radius=1.1, percent=90, threshold=4))
        path.parent.mkdir(parents=True, exist_ok=True)
        out.convert("RGB").save(path, "PNG", optimize=True)


def foam_curl(
    painter: RasterPainter,
    cx: float,
    cy: float,
    scale: float,
    angle: float,
    flip: bool = False,
    fill: str = PAPER,
    shade: str = FOREST_300,
    ink: str = INK,
) -> None:
    sign = -1 if flip else 1

    def tr(point: Point) -> Point:
        x, y = point
        x *= sign
        x, y = rotate((x * scale, y * scale), angle)
        return (cx + x, cy + y)

    body = [
        tr((-0.95, 0.26)),
        tr((-0.50, -0.64)),
        tr((0.28, -0.62)),
        tr((0.66, -0.06)),
        tr((0.28, 0.42)),
        tr((-0.18, 0.22)),
        tr((-0.05, -0.18)),
        tr((0.28, -0.14)),
        tr((0.18, 0.16)),
        tr((-0.36, 0.44)),
    ]
    shadow = [(x + scale * 0.13, y + scale * 0.20) for x, y in body]
    painter.smooth_polygon(shadow, shade, alpha=150, closed=True)
    painter.smooth_polygon(body, fill, outline=ink, outline_width=max(1.0, scale * 0.08), closed=True)
    painter.bezier(
        tr((-0.24, 0.12)),
        tr((0.15, -0.24)),
        tr((0.56, -0.18)),
        tr((0.50, 0.18)),
        ink,
        max(1.0, scale * 0.08),
        230,
    )


def foam_claw(
    painter: RasterPainter,
    cx: float,
    cy: float,
    scale: float,
    angle: float,
    flip: bool = False,
    fill: str = PAPER,
    shade: str = FOREST_300,
    ink: str = INK,
) -> None:
    sign = -1 if flip else 1

    def tr(point: Point) -> Point:
        x, y = point
        x *= sign
        x, y = rotate((x * scale, y * scale), angle)
        return (cx + x, cy + y)

    shadow = [tr((-0.86, 0.16)), tr((-0.18, -0.38)), tr((0.58, -0.28)), tr((0.78, 0.18))]
    shadow = [(x + scale * 0.12, y + scale * 0.18) for x, y in shadow]
    painter.line(shadow, shade, scale * 0.46, alpha=135)
    painter.outlined_line(
        [tr((-0.86, 0.16)), tr((-0.18, -0.38)), tr((0.58, -0.28)), tr((0.78, 0.18))],
        fill,
        ink,
        scale * 0.31,
        scale * 0.08,
        alpha=248,
    )
    painter.outlined_line(
        [tr((-0.56, 0.32)), tr((-0.02, 0.05)), tr((0.34, 0.10)), tr((0.18, 0.34))],
        fill,
        ink,
        scale * 0.21,
        scale * 0.07,
        alpha=248,
    )
    painter.bezier(
        tr((-0.12, -0.12)),
        tr((0.18, -0.28)),
        tr((0.56, -0.12)),
        tr((0.44, 0.18)),
        ink,
        max(1.0, scale * 0.05),
        220,
    )


def draw_surfer(
    painter: RasterPainter,
    cx: float,
    cy: float,
    scale: float,
    angle: float,
    ink: str,
) -> None:
    def tr(point: Point) -> Point:
        x, y = rotate((point[0] * scale, point[1] * scale), angle)
        return (cx + x, cy + y)

    painter.ribbon([tr((-80, 12)), tr((-20, 7)), tr((44, 8)), tr((82, 10))], [5, 7, 6, 4], FOREST_900, alpha=145)
    painter.ribbon(
        [tr((-78, 5)), tr((-24, -1)), tr((42, 0)), tr((82, 4))],
        [7.5 * scale, 9.2 * scale, 8.2 * scale, 4.8 * scale],
        SURFER_BOARD,
        alpha=252,
        outline=ink,
        outline_width=1.25 * scale,
    )
    painter.line([tr((-48, 3)), tr((-4, 1)), tr((48, 2))], FOREST_600, 0.9 * scale, alpha=155)

    wetsuit = INK
    jersey = SURFER_JERSEY
    skin = PAPER_300

    # Thumbnail-first surfer: dark connected silhouette with a thin cream edge.
    edge = PAPER_100
    painter.outlined_line([tr((-2, -31)), tr((-26, -18)), tr((-44, -4)), tr((-64, 5))], wetsuit, edge, 5.5 * scale, 1.05 * scale)
    painter.outlined_line([tr((14, -31)), tr((34, -18)), tr((52, -6)), tr((72, 1))], wetsuit, edge, 5.5 * scale, 1.05 * scale)
    painter.ellipse_outline(*tr((-65, 5)), 6.2 * scale, 2.0 * scale, wetsuit, edge, 0.9 * scale)
    painter.ellipse_outline(*tr((73, 1)), 6.0 * scale, 1.9 * scale, wetsuit, edge, 0.9 * scale)

    body = [
        (-7, -33), (-2, -49), (8, -61), (20, -67), (31, -62), (36, -49),
        (33, -36), (21, -27), (6, -25),
    ]
    painter.smooth_polygon([tr(point) for point in body], jersey, outline=edge, outline_width=1.6 * scale, alpha=252)
    painter.outlined_line([tr((4, -55)), tr((-24, -48)), tr((-50, -34))], jersey, edge, 4.4 * scale, 0.95 * scale)
    painter.outlined_line([tr((30, -53)), tr((54, -40)), tr((74, -27))], jersey, edge, 4.4 * scale, 0.95 * scale)

    neck = [(18, -61), (30, -60), (31, -68), (20, -70)]
    painter.smooth_polygon([tr(point) for point in neck], skin, outline=ink, outline_width=0.7 * scale, alpha=252)
    head_center = tr((28, -71))
    painter.ellipse_outline(head_center[0], head_center[1], 7.3 * scale, 8.0 * scale, skin, ink, 0.95 * scale)
    painter.bezier(tr((21, -79)), tr((27, -83)), tr((36, -82)), tr((43, -77)), ink, 1.6 * scale, alpha=235)


def draw_wave(painter: RasterPainter) -> None:
    ink = INK
    navy = FOREST_900
    deep = FOREST_800
    mid = FOREST_600
    pale = PAPER
    foam = PAPER
    shade = FOREST_300

    painter.paper_texture()

    # Distant atmospheric forms.
    painter.smooth_polygon(
        [(-10, 0), (1210, 0), (1210, 178), (1040, 164), (830, 154), (620, 164), (430, 150), (220, 162), (-10, 150)],
        SKY_TAN,
        alpha=255,
    )
    painter.smooth_polygon(
        [(0, 96), (180, 72), (340, 82), (520, 64), (690, 78), (900, 64), (1200, 86), (1200, 182), (0, 176)],
        SKY_GOLD,
        alpha=235,
    )
    painter.smooth_polygon(
        [(0, 182), (170, 164), (380, 180), (590, 166), (780, 184), (990, 170), (1200, 184), (1200, 252), (0, 252)],
        HORIZON_MOSS,
        alpha=188,
    )
    painter.smooth_polygon(
        [(836, 262), (886, 228), (928, 184), (980, 248), (1036, 262), (1200, 258), (1200, 286), (836, 286)],
        PAPER_100,
        outline=ink,
        outline_width=1.35,
        alpha=185,
    )
    painter.smooth_polygon([(906, 238), (928, 194), (966, 244)], FOREST_700, alpha=222)
    painter.ribbon(
        [(770, 276), (915, 260), (1050, 274), (1208, 262)],
        [8, 10, 8, 10],
        navy,
        alpha=220,
        outline=ink,
        outline_width=0.8,
    )

    # Foreground ocean ribbons.
    painter.ribbon(
        [(0, 374), (220, 350), (430, 374), (650, 350), (890, 370), (1210, 342)],
        [34, 58, 42, 62, 44, 68],
        deep,
        alpha=245,
    )
    painter.ribbon(
        [(0, 404), (220, 382), (472, 406), (720, 380), (980, 402), (1230, 374)],
        [50, 76, 52, 78, 60, 90],
        navy,
        alpha=250,
    )
    painter.ribbon(
        [(-20, 296), (178, 284), (360, 312), (560, 292), (785, 314), (1010, 292), (1220, 306)],
        [22, 36, 25, 34, 24, 34, 26],
        deep,
        alpha=240,
        outline=ink,
        outline_width=1.2,
    )
    painter.ribbon(
        [(30, 326), (250, 312), (440, 336), (650, 310), (890, 330), (1190, 312)],
        [12, 18, 16, 20, 14, 18],
        pale,
        alpha=235,
        outline=ink,
        outline_width=1.3,
    )
    painter.ribbon(
        [(24, 352), (240, 338), (470, 360), (720, 334), (980, 354), (1210, 338)],
        [10, 18, 13, 18, 13, 16],
        FOREST_300,
        alpha=215,
    )
    for y, offset, width in [(332, 0, 13), (368, 34, 16), (394, 12, 18)]:
        painter.ribbon(
            [
                (-40, y + 18),
                (160, y - 4),
                (360, y + 10),
                (585, y - 7),
                (810, y + 8),
                (1040, y - 6),
                (1240, y + offset),
            ],
            [width, width + 6, width, width + 5, width, width + 5, width],
            pale,
            alpha=226,
            outline=ink,
            outline_width=0.95,
        )
    painter.dry_marks(
        170,
        (315, 415),
        [ink, deep, mid, pale],
        (1.0, 4.0),
        (24, 96),
        (60, 145),
        angle=-0.03,
        jitter=0.16,
    )

    # Large pale back of the wave.
    painter.smooth_polygon(
        [
            (-34, 232), (56, 182), (118, 128), (196, 82), (302, 58), (416, 54),
            (500, 76), (548, 116), (572, 154), (526, 182), (412, 156),
            (292, 138), (178, 152), (70, 204), (-28, 286),
        ],
        pale,
        outline=ink,
        outline_width=3.0,
        alpha=248,
    )

    # Continuous rideable face: one steep surface before the carved rib marks.
    painter.smooth_polygon(
        [
            (-28, 404), (46, 340), (120, 268), (224, 204), (348, 160), (494, 142),
            (634, 156), (736, 198), (820, 258), (866, 310), (772, 340), (610, 346),
            (430, 360), (220, 392), (64, 424),
        ],
        deep,
        outline=ink,
        outline_width=2.2,
        alpha=246,
    )
    painter.smooth_polygon(
        [(260, 352), (386, 268), (536, 220), (682, 230), (792, 280), (690, 314), (488, 322)],
        FOREST_700,
        alpha=150,
    )
    painter.ribbon(
        [(140, 356), (282, 286), (444, 236), (604, 228), (772, 288)],
        [13, 17, 18, 15, 9],
        FOREST_300,
        alpha=142,
    )
    painter.ribbon(
        [(186, 378), (338, 318), (504, 284), (694, 302), (846, 334)],
        [10, 14, 12, 10, 8],
        pale,
        alpha=190,
        outline=ink,
        outline_width=0.8,
    )

    # Dark ribbed wave body, broken into separate rising bands.
    rib_centers = [
        [(-14, 390), (54, 316), (122, 238), (218, 176), (320, 150)],
        [(52, 398), (116, 315), (184, 226), (288, 166), (402, 145)],
        [(122, 398), (182, 318), (248, 226), (356, 166), (492, 148)],
        [(192, 398), (246, 320), (316, 234), (430, 174), (604, 160)],
        [(272, 392), (318, 328), (386, 246), (514, 190), (712, 190)],
        [(350, 382), (398, 326), (480, 264), (628, 218), (804, 246)],
    ]
    rib_widths = [
        [54, 66, 74, 62, 34],
        [48, 60, 68, 56, 32],
        [44, 58, 62, 48, 30],
        [38, 52, 56, 42, 25],
        [32, 44, 48, 34, 18],
        [28, 38, 38, 28, 14],
    ]
    for idx, center in enumerate(rib_centers):
        painter.ribbon(center, rib_widths[idx], navy if idx < 3 else deep, alpha=246)
        painter.ribbon(center, [w * 0.22 for w in rib_widths[idx]], mid, alpha=125)
        painter.line(center, ink, 2.2, alpha=175)

    painter.smooth_polygon(
        [
            (246, 370), (340, 308), (468, 252), (598, 230), (730, 252),
            (846, 312), (750, 342), (594, 336), (438, 350),
        ],
        FOREST_600,
        outline=ink,
        outline_width=1.4,
        alpha=232,
    )
    painter.ribbon(
        [(310, 346), (446, 286), (600, 260), (770, 304)],
        [9, 14, 12, 7],
        FOREST_300,
        alpha=170,
    )
    painter.ribbon(
        [(278, 374), (414, 330), (576, 314), (790, 342)],
        [8, 12, 10, 7],
        pale,
        alpha=195,
        outline=ink,
        outline_width=0.75,
    )
    painter.dry_marks(
        46,
        (250, 346),
        [FOREST_300, deep, pale],
        (0.8, 2.3),
        (18, 68),
        (45, 112),
        angle=-0.18,
        jitter=0.24,
    )

    # Curling lip and dark crest.
    painter.smooth_polygon(
        [
            (226, 170), (318, 124), (428, 106), (548, 118), (662, 148), (748, 194),
            (804, 236), (752, 262), (646, 230), (532, 196), (424, 170), (312, 182),
            (244, 212), (204, 200),
        ],
        navy,
        outline=ink,
        outline_width=3.0,
        alpha=252,
    )
    painter.ribbon(
        [(278, 154), (416, 124), (548, 134), (686, 174), (762, 230)],
        [14, 22, 24, 18, 9],
        FOREST_400,
        alpha=150,
    )

    # Foam clusters along crest.
    crest = cubic((190, 180), (312, 88), (570, 88), (812, 242), steps=42)
    for i, (x, y) in enumerate(crest[2:-2:2]):
        scale = random.uniform(17, 30) * (1.22 if i < 10 else 1.0)
        angle = random.uniform(-0.82, 0.34)
        if i % 3 == 0:
            foam_curl(
                painter,
                x + random.uniform(-18, 18),
                y + random.uniform(-22, 14),
                scale * 0.92,
                angle,
                flip=random.random() < 0.45,
                fill=foam,
                shade=shade,
                ink=ink,
            )
        foam_claw(
            painter,
            x + random.uniform(-16, 18),
            y + random.uniform(-18, 16),
            scale,
            angle,
            flip=random.random() < 0.42,
            fill=foam,
            shade=shade,
            ink=ink,
        )
    for _ in range(72):
        x = random.uniform(220, 812)
        y = random.uniform(98, 272)
        if random.random() < 0.78:
            foam_claw(
                painter,
                x,
                y,
                random.uniform(8, 18),
                random.uniform(-1.0, 0.75),
                flip=random.random() < 0.5,
                fill=foam,
                shade=shade,
                ink=ink,
            )
        else:
            foam_curl(
                painter,
                x,
                y,
                random.uniform(8, 15),
                random.uniform(-0.9, 0.7),
                flip=random.random() < 0.5,
                fill=foam,
                shade=shade,
                ink=ink,
            )

    # Foreground foam and lower breaking wave.
    lower_foam_path = cubic((-20, 306), (138, 236), (300, 280), (486, 334), steps=34)
    for x, y in lower_foam_path[::2]:
        if random.random() < 0.65:
            foam_claw(
                painter,
                x + random.uniform(-18, 20),
                y + random.uniform(-26, 12),
                random.uniform(13, 27),
                random.uniform(-0.95, 0.7),
                flip=random.random() < 0.55,
                fill=foam,
                shade=shade,
                ink=ink,
            )
        else:
            foam_curl(
                painter,
                x + random.uniform(-16, 18),
                y + random.uniform(-24, 12),
                random.uniform(12, 24),
                random.uniform(-0.8, 0.9),
                flip=random.random() < 0.55,
                fill=foam,
                shade=shade,
                ink=ink,
            )
    for _ in range(42):
        x = random.uniform(-10, 470)
        y = random.uniform(250, 360)
        foam_claw(
            painter,
            x,
            y,
            random.uniform(7, 16),
            random.uniform(-1.1, 1.0),
            flip=random.random() < 0.5,
            fill=foam,
            shade=shade,
            ink=ink,
        )
    painter.dry_marks(
        170,
        (235, 345),
        [foam, shade, ink, mid],
        (0.8, 3.2),
        (10, 44),
        (45, 130),
        angle=-0.35,
        jitter=0.45,
    )

    # White spray dots in the dark ribs.
    for _ in range(145):
        x = random.uniform(145, 620)
        y = random.uniform(150, 350)
        painter.ellipse(x, y, random.uniform(1.2, 3.2), random.uniform(1.2, 3.2), pale, random.randint(150, 235))

    # Filled surfer planted on the lower third of the rideable face.
    painter.ribbon(
        [(430, 330), (552, 304), (692, 316)],
        [9, 14, 7],
        INK,
        alpha=180,
    )
    draw_surfer(painter, 552, 297, 1.9, -0.08, ink)


def generate(output: Path, seed: int) -> None:
    painter = RasterPainter(CANVAS_W, CANVAS_H, seed)
    draw_wave(painter)
    painter.save(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("server/screenshots/raster-surfer-wave-masthead.png"),
    )
    parser.add_argument("--seed", type=int, default=14)
    args = parser.parse_args()
    generate(args.output, args.seed)
    print(args.output)


if __name__ == "__main__":
    main()
