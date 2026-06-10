# Monet-style study: poplars on a river at dusk, broken color, reflections.
# Written the way the system prompt teaches the agent to paint.
import math
import random

random.seed(7)
paths = []
w, h = canvas_width, canvas_height
horizon = h * 0.52

# 1. Colored ground — warm dusk sky into cool water.
paths.append(rect_shape(0, 0, w, h, "#e8d9c0", fill_opacity=1.0))
paths.extend(
    background_wash(
        count=420,
        stops=[
            (0.0, ["#cfd9e8", "#dccfb9"]),
            (0.30, ["#e8cfa8", "#e0b98e"]),
            (0.52, ["#d9a87c", "#c9956e"]),
            (0.62, ["#9fb3c4", "#8aa0b5"]),
            (1.0, ["#5d7591", "#4a607c"]),
        ],
        wash_rows=16,
        texture_ratio=0.15,
    )
)

# 2. Sun glow low in the sky.
paths.extend(
    glow_field(
        w * 0.62,
        horizon - h * 0.13,
        110,
        count=120,
        colors=["#f2c98a", "#eebd72", "#f7e3b2"],
        brushes=["oil_filbert", "airbrush"],
        opacity_range=(0.10, 0.30),
    )
)

# 3. Far bank value mass.
bank = [
    (0, horizon),
    (w * 0.42, horizon - 14),
    (w * 0.72, horizon - 8),
    (w, horizon - 18),
    (w, horizon + 10),
    (0, horizon + 10),
]
paths.extend(
    mass_field(
        bank,
        count=140,
        colors=["#6d6a52", "#7c7456", "#5c5d49"],
        brushes=["oil_flat", "oil_filbert"],
        opacity_range=(0.3, 0.6),
    )
)

# 4. Poplar trees: tall broken-color masses with trunks.
tree_xs = [w * 0.18, w * 0.27, w * 0.36, w * 0.46]
tree_palette = ["#4f5a3a", "#6a7344", "#86703f", "#3f4a33", "#9b8a52"]
for i, tx in enumerate(tree_xs):
    top = horizon - h * (0.30 + 0.06 * math.sin(i * 1.7))
    crown = [
        (tx - 16, horizon - 6),
        (tx - 22, (top + horizon) / 2),
        (tx - 10, top),
        (tx + 10, top + 8),
        (tx + 20, (top + horizon) / 2 + 10),
        (tx + 14, horizon - 4),
    ]
    paths.extend(
        mass_field(
            crown,
            count=120,
            colors=tree_palette,
            brushes=["oil_filbert", "dry_brush"],
            length_range=(6, 16),
            width_range=(3, 8),
            opacity_range=(0.35, 0.75),
        )
    )
    paths.append(
        line(tx, horizon, tx, top + 14, brush="dry_brush", color="#41382b", stroke_width=4)
    )

# 5. Water: horizontal broken strokes, warm light lane under the sun.
for band in range(26):
    t = band / 25
    y = horizon + 12 + t * (h - horizon - 24)
    n = int(14 + 10 * t)
    for _ in range(n):
        x = random.uniform(0, w)
        ln = random.uniform(14, 60) * (0.5 + t)
        warm_lane = abs(x - w * 0.62) < w * 0.09 and random.random() < 0.7
        if warm_lane:
            color = random.choice(["#e9bd83", "#dca36b", "#f3d6a0"])
        else:
            color = random.choice(["#5d7591", "#49617e", "#7589a1", "#3e5470"])
        paths.append(
            line(
                x,
                y + random.uniform(-3, 3),
                x + ln,
                y + random.uniform(-3, 3),
                brush=random.choice(["oil_flat", "oil_filbert"]),
                color=color,
                stroke_width=random.uniform(3, 8),
                opacity=random.uniform(0.35, 0.8),
            )
        )

# 6. Tree reflections, broken and elongated.
for tx in tree_xs:
    paths.extend(
        reflection_field(
            tx,
            horizon + 8,
            34,
            h * 0.34,
            count=46,
            colors=["#46523a", "#5a6342", "#3c4a3a"],
            brushes=["oil_filbert"],
            opacity_range=(0.2, 0.5),
        )
    )

# 7. Sparse highlights: sun sparkle on water.
for _ in range(60):
    x = w * 0.62 + random.gauss(0, w * 0.05)
    y = horizon + random.uniform(8, h * 0.42)
    paths.append(
        dab(
            x,
            y,
            random.uniform(4, 14),
            0,
            brush="palette_knife",
            color=random.choice(["#f7e3b2", "#f2cd8d", "#ffeec6"]),
            stroke_width=random.uniform(2, 5),
            opacity=random.uniform(0.5, 0.9),
        )
    )

output_paths(paths)
