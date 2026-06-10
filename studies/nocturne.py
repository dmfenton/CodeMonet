# Nocturne: swirling night sky over a sleeping village, crescent moon,
# cypress flame. Post-impressionist mark grammar — long curved strokes.
import math
import random

random.seed(19)
paths = []
w, h = canvas_width, canvas_height
horizon = h * 0.68

night_deep = "#16213e"
night_mid = "#1f3a6e"
night_glow = "#3a5f9e"
star_gold = "#f3cf6d"
star_warm = "#e8b84a"
moon_pale = "#f7e9b8"
hill_dark = "#1b2a35"
village = "#22303c"
window = "#f0c060"
cypress = "#0e1f18"

# 1. Deep blue ground.
paths.append(rect_shape(0, 0, w, h, night_deep, fill_opacity=1.0))
paths.extend(background_wash(
    count=240,
    stops=[(0.0, [night_mid, night_deep]), (0.5, [night_glow, night_mid]), (1.0, [night_deep, "#101a30"])],
    y_range=(0, horizon),
    wash_rows=10,
    texture_ratio=0.1,
    opacity_range=(0.15, 0.4),
))

# 2. The great swirl: two interlocking spiral currents of long curved marks.
def spiral_skeleton(cx, cy, r0, r1, turns, n, phase=0.0, squash=0.55):
    pts = []
    for i in range(n):
        t = i / (n - 1)
        ang = phase + turns * 2 * math.pi * t
        r = r0 + (r1 - r0) * t
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang) * squash))
    return pts

swirl_colors = ["#7d9cd8", "#4a6fb0", "#b8c9e8", "#2d4a8a", "#9bb4dd"]
for cx, cy, r1, turns, phase in [
    (w * 0.38, h * 0.26, w * 0.17, 1.6, 0.8),
    (w * 0.66, h * 0.2, w * 0.11, 1.4, 3.6),
]:
    skel = spiral_skeleton(cx, cy, 6, r1, turns, 60, phase)
    paths.extend(curve_marks(
        skel, count=130, colors=swirl_colors,
        brushes=["oil_filbert", "oil_round"],
        width_range=(4, 9), length_range=(14, 34),
        opacity_range=(0.3, 0.6), jitter=5,
    ))

# 3. Wind currents flowing between the swirls.
current = [(0, h * 0.3), (w * 0.25, h * 0.22), (w * 0.52, h * 0.3), (w * 0.8, h * 0.18), (w, h * 0.26)]
paths.extend(contour_stack(
    current, offsets=[-18, 0, 20, 44],
    colors=swirl_colors, brushes=["oil_filbert"],
    count_per_offset=26, width_range=(3.5, 8),
    length_range=(18, 44), opacity_range=(0.22, 0.5), jitter=8,
))

# 4. Crescent moon, radiant.
mx, my = w * 0.86, h * 0.13
paths.extend(glow_field(mx, my, 72, count=90, colors=[moon_pale, star_gold, "#fff6d8"],
                        opacity_range=(0.1, 0.35)))
paths.append(ellipse_shape(mx, my, 24, 24, moon_pale, fill_opacity=0.96))
paths.append(ellipse_shape(mx - 6, my - 3, 14, 14, "#fff6d8", fill_opacity=0.85))

# 5. Stars with whirling halos.
for sx_, sy_ in [(0.1, 0.12), (0.22, 0.32), (0.48, 0.1), (0.6, 0.36), (0.75, 0.32), (0.32, 0.05)]:
    x, y = w * sx_, h * sy_
    paths.extend(glow_field(x, y, 26, count=30, colors=[star_gold, star_warm, "#fff0c0"],
                            opacity_range=(0.12, 0.4)))
    for k in range(8):
        ang = k / 8 * 2 * math.pi
        paths.append(dab(x + 10 * math.cos(ang), y + 8 * math.sin(ang), 9, ang + math.pi / 2,
                         brush="oil_round", color=star_gold,
                         stroke_width=3, opacity=0.55))
    paths.append(dab(x, y, 6, 0, brush="palette_knife", color="#fff6d8", stroke_width=4, opacity=0.95))

# 6. Rolling dark hills.
hills = [(0, horizon - 14), (w * 0.2, horizon - 44), (w * 0.45, horizon - 16), (w * 0.7, horizon - 38), (w, horizon - 8)]
paths.extend(curve_band(hills, bottom_y=h, count=170,
    colors=[hill_dark, "#243a48", "#16242e"],
    brushes=["oil_flat", "oil_filbert"],
    length_range=(16, 50), width_range=(6, 16),
    opacity_range=(0.4, 0.8), wash_rows=5, texture_ratio=0.3))

# 7. Village: small gabled houses with lit windows, a steeple.
hx = [0.14, 0.24, 0.34, 0.46, 0.58, 0.68]
for i, fx in enumerate(hx):
    x = w * fx
    y = horizon + h * 0.04 + (i % 3) * h * 0.035
    hw = w * random.uniform(0.045, 0.07)
    hh = h * random.uniform(0.045, 0.065)
    paths.append(rect_shape(x, y, hw, hh, village, fill_opacity=0.95))
    roof = f"M {x - 3} {y} L {x + hw / 2} {y - hh * 0.7} L {x + hw + 3} {y} Z"
    paths.append(filled_svg_path(roof, "#1a2630", fill_opacity=0.95))
    if random.random() < 0.8:
        paths.append(rect_shape(x + hw * 0.25, y + hh * 0.3, hw * 0.16, hh * 0.3, window, fill_opacity=0.9))
    if random.random() < 0.5:
        paths.append(rect_shape(x + hw * 0.62, y + hh * 0.35, hw * 0.14, hh * 0.28, "#d9a440", fill_opacity=0.85))
# Steeple
stx, sty = w * 0.41, horizon - h * 0.015
paths.append(rect_shape(stx, sty - h * 0.09, w * 0.022, h * 0.105, village, fill_opacity=0.97))
spire = f"M {stx - 4} {sty - h * 0.09} L {stx + w * 0.011} {sty - h * 0.16} L {stx + w * 0.022 + 4} {sty - h * 0.09} Z"
paths.append(filled_svg_path(spire, "#1a2630", fill_opacity=0.97))

# 8. Cypress: a dark flame in the left foreground.
cyx = w * 0.09
flame = " ".join([
    f"M {cyx - w * 0.025} {h}",
    f"C {cyx - w * 0.045} {h * 0.7} {cyx - w * 0.02} {h * 0.5} {cyx - w * 0.008} {h * 0.34}",
    f"C {cyx} {h * 0.26} {cyx + w * 0.012} {h * 0.3} {cyx + w * 0.01} {h * 0.4}",
    f"C {cyx + w * 0.03} {h * 0.34} {cyx + w * 0.026} {h * 0.5} {cyx + w * 0.04} {h * 0.62}",
    f"C {cyx + w * 0.05} {h * 0.78} {cyx + w * 0.03} {h * 0.9} {cyx + w * 0.035} {h} Z",
])
paths.append(filled_svg_path(flame, cypress, fill_opacity=0.97))
paths.extend(curve_marks(
    [(cyx - 8, h * 0.85), (cyx - 4, h * 0.6), (cyx + 2, h * 0.4), (cyx + 6, h * 0.32)],
    count=40, colors=["#173026", "#0a1812", "#24443a"],
    brushes=["dry_brush", "oil_filbert"],
    width_range=(2.5, 6), length_range=(10, 30), opacity_range=(0.4, 0.75), jitter=6,
))

# 9. Moonlight rim on the hills, sparse.
paths.extend(broken_edge(hills, count=22, colors=[moon_pale, "#9bb4dd"],
    length_range=(8, 26), width_range=(2, 4), opacity_range=(0.2, 0.45)))

output_paths(paths)
