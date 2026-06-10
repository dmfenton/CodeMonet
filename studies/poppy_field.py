# Poppy field at midsummer: red poppies sweeping down a green hillside,
# two strolling figures with a parasol, hazy poplars, big cloud sky.
import math
import random

random.seed(33)
paths = []
w, h = canvas_width, canvas_height
horizon = h * 0.42

sky_blue = "#bcd2e4"
cloud = "#f4f1e8"
cloud_shadow = "#cfd4dc"
field_light = "#a8b86a"
field_mid = "#7e9a4e"
field_dark = "#55763c"
ochre = "#c8b478"
poppy = "#c43a2a"
poppy_hot = "#e05538"
poppy_deep = "#8e2419"
tree_green = "#4a6647"

# 1. Sky ground and clouds.
paths.append(rect_shape(0, 0, w, h, sky_blue, fill_opacity=1.0))
paths.extend(background_wash(
    count=200,
    stops=[(0.0, ["#a9c4dd", sky_blue]), (0.6, [sky_blue, "#cdddE8"]), (1.0, ["#d8e2ea", "#c4d5e4"])],
    y_range=(0, horizon),
    wash_rows=8, texture_ratio=0.1, opacity_range=(0.12, 0.3),
))
for ccx, ccy, cr in [(0.3, 0.16, 0.2), (0.62, 0.1, 0.16), (0.84, 0.22, 0.13)]:
    cx_, cy_, r_ = w * ccx, h * ccy, w * cr
    paths.extend(radial_cluster(cx_, cy_, count=70, rx=r_, ry=r_ * 0.45,
        colors=[cloud, "#ffffff", cloud_shadow],
        brushes=["oil_filbert", "airbrush"],
        length_range=(14, 40), width_range=(8, 20), opacity_range=(0.25, 0.6)))

# 2. Field: layered green planes, warmer near.
paths.extend(curve_band(
    [(0, horizon), (w * 0.4, horizon - 6), (w, horizon + 4)], bottom_y=h,
    count=240,
    stops=[(0.0, [field_light, ochre]), (0.5, [field_mid, field_light]), (1.0, [field_dark, field_mid])],
    brushes=["oil_flat", "oil_filbert"],
    length_range=(18, 56), width_range=(7, 18),
    opacity_range=(0.35, 0.7), wash_rows=7, texture_ratio=0.25,
))

# 3. Distant tree line and one poplar pair.
treeline = [(0, horizon - 4), (w * 0.3, horizon - 16), (w * 0.62, horizon - 8), (w, horizon - 20)]
paths.extend(curve_band(treeline, bottom_y=horizon + 8, count=90,
    colors=[tree_green, "#5d7a52", "#3c5840"],
    brushes=["oil_filbert"], length_range=(8, 22), width_range=(5, 12),
    opacity_range=(0.4, 0.75), texture_ratio=0.5))
for tx, ts in [(w * 0.71, 1.0), (w * 0.76, 0.8)]:
    top = horizon - h * 0.16 * ts
    paths.extend(mass_field(
        [(tx - 12 * ts, horizon), (tx - 16 * ts, (top + horizon) / 2), (tx - 6 * ts, top),
         (tx + 6 * ts, top + 6), (tx + 15 * ts, (top + horizon) / 2 + 8), (tx + 10 * ts, horizon)],
        count=60, colors=[tree_green, "#618457", "#39523d"],
        brushes=["oil_filbert", "dry_brush"],
        length_range=(5, 14), width_range=(3, 8), opacity_range=(0.4, 0.8),
    ))

# 4. Poppies: massed drifts down the diagonal — clusters of overlapping
# dabs, sparse and small far, dense and heavy near.
# Light scatter across the whole meadow first.
for _ in range(160):
    t = random.random() ** 1.4
    y = horizon + 12 + t * (h - horizon - 26)
    x = random.uniform(0, w)
    size = (2.5 + 9 * t) * random.uniform(0.7, 1.2)
    paths.append(dab(
        x, y, size, random.uniform(0, math.pi),
        brush="oil_round", color=random.choice([poppy, poppy_hot]),
        stroke_width=max(2, size * 0.55), opacity=random.uniform(0.6, 0.9),
    ))

n_clusters = 30
for c in range(n_clusters):
    t = c / (n_clusters - 1)
    y = horizon + 14 + t * (h - horizon - 30)
    drift = c % 2
    base = 0.7 - 0.55 * t if drift == 0 else 0.3 + 0.25 * t
    center = w * base + random.uniform(-w * 0.07, w * 0.07)
    cluster_r = w * (0.025 + 0.075 * t)
    n = int(6 + 22 * t)
    for _ in range(n):
        x = random.gauss(center, cluster_r)
        yy = y + random.gauss(0, cluster_r * 0.35)
        if x < -10 or x > w + 10:
            continue
        size = (3.0 + 12 * t) * random.uniform(0.75, 1.3)
        color = random.choice([poppy, poppy_hot, poppy_hot, poppy])
        paths.append(dab(
            x, yy, size, random.uniform(0, math.pi),
            brush="oil_round" if t < 0.5 else "palette_knife",
            color=color, stroke_width=max(2.5, size * 0.6),
            opacity=random.uniform(0.75, 0.95),
        ))
        if t > 0.45 and random.random() < 0.4:
            paths.append(dab(
                x + size * 0.15, yy + size * 0.12, size * 0.45, random.uniform(0, math.pi),
                brush="oil_round", color=poppy_deep,
                stroke_width=max(2, size * 0.3), opacity=0.8,
            ))
# A few grass blades between near poppies.
for _ in range(50):
    x = random.uniform(0, w * 0.7)
    y = random.uniform(h * 0.72, h * 0.97)
    paths.append(line(x, y, x + random.uniform(-6, 6), y - random.uniform(10, 26),
        brush="dry_brush", color=random.choice([field_dark, field_mid, "#46663a"]),
        stroke_width=random.uniform(2, 4), opacity=random.uniform(0.3, 0.6)))

# 5. Strolling figures: woman with rose parasol and child beside her.
fx, fy = w * 0.55, h * 0.62
paths.extend(small_figure_silhouette(fx, fy, scale=2.3, pose="walk", color="#2e3a4c", ground=True,
                                     ground_color="#46603a"))
parasol = f"M {fx - 26} {fy - 52} Q {fx} {fy - 74} {fx + 26} {fy - 52} Q {fx} {fy - 60} {fx - 26} {fy - 52} Z"
paths.append(filled_svg_path(parasol, "#d8a0a8", fill_opacity=0.96))
paths.append(line(fx, fy - 56, fx + 2, fy - 22, brush="ink", color="#3a4452", stroke_width=2.5))
paths.extend(small_figure_silhouette(fx + w * 0.05, fy + h * 0.03, scale=1.3, pose="walk",
                                     color="#46414e", ground=True, ground_color="#46603a"))

output_paths(paths)
