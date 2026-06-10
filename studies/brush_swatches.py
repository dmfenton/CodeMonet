# Brush character chart: one row per brush, varied width and opacity.
import math

paths = []
w, h = canvas_width, canvas_height
paths.append(rect_shape(0, 0, w, h, "#ece5d8", fill_opacity=1.0))

brushes = [
    "oil_round", "oil_flat", "oil_filbert", "dry_brush", "palette_knife",
    "watercolor", "airbrush", "charcoal", "ink", "marker",
]
colors = ["#2d4a6b", "#8a3324", "#4f6b3a", "#b08030", "#5a4a78"]
row_h = h / (len(brushes) + 1)
for i, brush in enumerate(brushes):
    y = row_h * (i + 1)
    # long S-curve stroke
    pts = [(60 + t * (w - 320) / 30, y + 14 * math.sin(t * 0.45)) for t in range(31)]
    paths.append(polyline(*pts, brush=brush, color=colors[i % 5], stroke_width=12, opacity=0.9))
    # short dabs
    for k in range(4):
        paths.append(
            dab(w - 220 + k * 36, y, 22, 25 * k, brush=brush, color=colors[(i + 2) % 5],
                stroke_width=10, opacity=0.8)
        )
    # thin light stroke
    paths.append(
        line(60, y + 22, w - 260, y + 22, brush=brush, color=colors[(i + 1) % 5],
             stroke_width=4, opacity=0.55)
    )

output_paths(paths)
