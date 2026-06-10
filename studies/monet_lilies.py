# Monet-style study: water lilies. Fewer, wider, confident marks.
import math
import random

random.seed(11)
paths = []
w, h = canvas_width, canvas_height

# 1. Ground: the whole canvas is water — cool ground with warm sky reflections.
paths.append(rect_shape(0, 0, w, h, "#7c93a6", fill_opacity=1.0))
paths.extend(
    background_wash(
        count=320,
        stops=[
            (0.0, ["#5c7d7a", "#6f8d86"]),
            (0.35, ["#8aa3b5", "#9db0c4"]),
            (0.62, ["#b9c3cf", "#cdbfae"]),
            (1.0, ["#4f6c88", "#3f5a74"]),
        ],
        wash_rows=12,
        texture_ratio=0.1,
        width_range=(14, 26),
    )
)

# 2. Reflections of unseen trees: long vertical pulls, broken.
for _ in range(70):
    x = random.uniform(0, w)
    y0 = random.uniform(0, h * 0.55)
    ln = random.uniform(30, 120)
    green = random.choice(["#3f5a4a", "#52715a", "#2f4a44", "#5d7a55"])
    paths.append(
        line(x, y0, x + random.uniform(-6, 6), y0 + ln,
             brush="oil_filbert", color=green,
             stroke_width=random.uniform(5, 12), opacity=random.uniform(0.25, 0.55))
    )

# 3. Sky reflection lane, warm.
for _ in range(46):
    x = random.uniform(w * 0.3, w * 0.85)
    y = random.uniform(h * 0.3, h * 0.62)
    paths.append(
        line(x, y, x + random.uniform(24, 90), y + random.uniform(-2, 2),
             brush="oil_flat", color=random.choice(["#e8d7bb", "#dfc8a8", "#f0e3cb"]),
             stroke_width=random.uniform(6, 13), opacity=random.uniform(0.3, 0.6))
    )

# 4. Lily pad clusters: elliptical dabs in drifting groups, perspective-scaled.
clusters = [
    (w * 0.22, h * 0.78, 1.25), (w * 0.62, h * 0.86, 1.4), (w * 0.78, h * 0.55, 0.9),
    (w * 0.38, h * 0.5, 0.75), (w * 0.16, h * 0.36, 0.55), (w * 0.55, h * 0.3, 0.5),
]
pad_greens = ["#4a6b3f", "#5f8049", "#74925b", "#39563b", "#86a063", "#2f4a35"]
for cx, cy, s in clusters:
    n = int(14 * s + 6)
    for _ in range(n):
        px = cx + random.gauss(0, w * 0.07 * s)
        py = cy + random.gauss(0, h * 0.035 * s)
        ln = random.uniform(14, 34) * s
        paths.append(
            dab(px, py, ln, 0, brush="oil_filbert",
                color=random.choice(pad_greens),
                stroke_width=random.uniform(6, 12) * s,
                opacity=random.uniform(0.55, 0.9))
        )
    # cool shadow under each cluster
    for _ in range(int(n * 0.4)):
        px = cx + random.gauss(0, w * 0.07 * s)
        py = cy + h * 0.02 * s + random.gauss(0, h * 0.02 * s)
        paths.append(
            dab(px, py, random.uniform(12, 26) * s, 0, brush="oil_round",
                color=random.choice(["#2b3f4a", "#34503f", "#1f3640"]),
                stroke_width=random.uniform(4, 8) * s,
                opacity=random.uniform(0.3, 0.55))
        )

# 5. Blossoms: few, bright, thick paint.
blooms = [(w * 0.24, h * 0.76, 1.2), (w * 0.64, h * 0.84, 1.3), (w * 0.4, h * 0.49, 0.7), (w * 0.79, h * 0.54, 0.8)]
for bx, by, s in blooms:
    for _ in range(int(6 * s + 3)):
        ang = random.uniform(0, math.pi)
        paths.append(
            dab(bx + random.gauss(0, 7 * s), by + random.gauss(0, 3.5 * s),
                random.uniform(7, 15) * s, ang, brush="palette_knife",
                color=random.choice(["#e7b7c4", "#f2d3da", "#d98ca2", "#fdf3ef"]),
                stroke_width=random.uniform(4, 8) * s,
                opacity=random.uniform(0.75, 0.95))
        )
    paths.append(
        dab(bx, by, 7 * s, 0.4, brush="palette_knife", color="#e9c46a",
            stroke_width=5 * s, opacity=0.9)
    )

# 6. Sparkle: dry brush skips between pads.
for _ in range(36):
    x = random.uniform(0, w)
    y = random.uniform(h * 0.2, h * 0.95)
    paths.append(
        line(x, y, x + random.uniform(18, 50), y + random.uniform(-2, 2),
             brush="dry_brush", color=random.choice(["#dfe8ee", "#cfdde8", "#f0e9d8"]),
             stroke_width=random.uniform(3, 6), opacity=random.uniform(0.35, 0.65))
    )

output_paths(paths)
