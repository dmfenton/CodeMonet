# The Great Wave off Kanagawa — built ONLY from general primitives:
# filled masses, counter-shape cuts, edge fingers, contour stacks, bands.
# No subject-specific helpers. Painterly interpretation of the woodblock.
import math
import random

random.seed(29)
paths = []
w, h = canvas_width, canvas_height

# Woodblock-inspired palette
cream = "#ece1c8"
sky_warm = "#e3d3b4"
pale = "#c8d3da"
foam = "#f4efe2"
blue_deep = "#1b3a5c"
blue_mid = "#2d5a82"
blue_pale = "#7d9cb8"
navy = "#10243c"

def sx(x):
    return x * w / 800

def sy(y):
    return y * h / 600

def P(x, y):
    return (sx(x), sy(y))

# 1. Cream sky ground with quiet horizontal wash.
paths.append(rect_shape(0, 0, w, h, cream, fill_opacity=1.0))
paths.extend(background_wash(
    count=160,
    stops=[(0.0, [sky_warm, cream]), (0.5, [cream, "#e9dcc0"]), (1.0, [pale, "#b9c6cf"])],
    wash_rows=8,
    texture_ratio=0.08,
    opacity_range=(0.10, 0.25),
    width_range=(12, 22),
))

# 2. Mount Fuji, small and far, seen through the wave's trough.
fuji = f"M {sx(560)} {sy(335)} L {sx(622)} {sy(268)} L {sx(638)} {sy(277)} L {sx(692)} {sy(335)} Z"
paths.append(filled_svg_path(fuji, "#5d7491", fill_opacity=0.85))
snow = f"M {sx(611)} {sy(280)} L {sx(622)} {sy(268)} L {sx(638)} {sy(277)} L {sx(643)} {sy(285)} L {sx(631)} {sy(281)} L {sx(622)} {sy(288)} Z"
paths.append(filled_svg_path(snow, foam, fill_opacity=0.9))

# 3. Distant swell band behind the trough.
swell = f"M 0 {sy(345)} C {sx(200)} {sy(330)} {sx(420)} {sy(352)} {sx(620)} {sy(340)} C {sx(700)} {sy(336)} {sx(760)} {sy(342)} {sx(800)} {sy(338)} L {sx(800)} {sy(420)} L 0 {sy(420)} Z"
paths.append(filled_svg_path(swell, blue_pale, fill_opacity=0.65))

# 4. The wave BODY: low sweeping wall rising from the right trough up to
#    the left, leaning forward. One curved mass, hand-authored.
body = " ".join([
    f"M 0 {sy(420)}",
    f"C {sx(40)} {sy(285)} {sx(95)} {sy(160)} {sx(225)} {sy(132)}",
    f"C {sx(305)} {sy(104)} {sx(390)} {sy(120)} {sx(442)} {sy(128)}",
    f"C {sx(420)} {sy(196)} {sx(412)} {sy(264)} {sx(470)} {sy(330)}",
    f"C {sx(540)} {sy(404)} {sx(640)} {sy(428)} {sx(800)} {sy(440)}",
    f"L {sx(800)} {sy(600)} L 0 {sy(600)} Z",
])
paths.append(filled_svg_path(body, blue_mid, fill_opacity=0.96))

# 5. The LIP: a separate hooked mass curling forward and DOWN over the
#    pale tunnel. Drawn as its own ribbon, not the top of the body.
lip = " ".join([
    f"M {sx(225)} {sy(132)}",
    f"C {sx(320)} {sy(88)} {sx(430)} {sy(96)} {sx(505)} {sy(122)}",
    f"C {sx(560)} {sy(160)} {sx(580)} {sy(208)} {sx(566)} {sy(248)}",
    f"C {sx(540)} {sy(212)} {sx(508)} {sy(186)} {sx(470)} {sy(178)}",
    f"C {sx(405)} {sy(162)} {sx(330)} {sy(152)} {sx(282)} {sy(170)}",
    f"C {sx(250)} {sy(146)} {sx(230)} {sy(126)} {sx(225)} {sy(132)} Z",
])
paths.append(filled_svg_path(lip, blue_deep, fill_opacity=0.97))

# 6. The TUNNEL: pale counter-shape under the lip — the hollow that makes
#    the wave read as a hook instead of a hill.
tunnel = " ".join([
    f"M {sx(282)} {sy(170)}",
    f"C {sx(345)} {sy(154)} {sx(430)} {sy(168)} {sx(486)} {sy(196)}",
    f"C {sx(520)} {sy(218)} {sx(540)} {sy(248)} {sx(540)} {sy(276)}",
    f"C {sx(480)} {sy(330)} {sx(430)} {sy(330)} {sx(410)} {sy(300)}",
    f"C {sx(380)} {sy(254)} {sx(330)} {sy(206)} {sx(282)} {sy(170)} Z",
])
paths.append(filled_svg_path(tunnel, pale, fill_opacity=0.92))
# Dark underside of the lip shading the tunnel roof.
underside = " ".join([
    f"M {sx(300)} {sy(176)}",
    f"C {sx(370)} {sy(166)} {sx(450)} {sy(182)} {sx(505)} {sy(214)}",
    f"C {sx(528)} {sy(232)} {sx(540)} {sy(252)} {sx(542)} {sy(266)}",
    f"C {sx(500)} {sy(232)} {sx(420)} {sy(196)} {sx(300)} {sy(176)} Z",
])
paths.append(filled_svg_path(underside, navy, fill_opacity=0.7))

# 7. FOAM CLAWS along the lip edge: tapered fingers reaching down.
lip_edge = [P(250, 120), P(330, 90), P(420, 92), P(500, 128), P(556, 188), P(566, 244)]
paths.extend(edge_fingers(
    lip_edge, count=34, side=1,
    colors=[foam, "#e8e2d2", foam],
    length_range=(sx(14), sx(46)),
    width_range=(3, 9),
    opacity_range=(0.75, 0.95),
))
# Claws hanging from the lip underside into the tunnel.
underside_edge = [P(330, 178), P(420, 192), P(490, 218), P(536, 254)]
paths.extend(edge_fingers(
    underside_edge, count=16, side=1,
    colors=[foam, "#e8e2d2"],
    length_range=(sx(10), sx(30)),
    width_range=(2.5, 7),
    opacity_range=(0.7, 0.92),
))

# Crest foam mass on top of the lip.
paths.extend(mass_field(
    [P(225, 108), P(330, 62), P(470, 80), P(540, 140), P(470, 120), P(330, 96), P(250, 122)],
    count=90, colors=[foam, "#ffffff", "#e8e2d2"],
    brushes=["oil_filbert", "dry_brush"],
    length_range=(6, 18), width_range=(4, 10), opacity_range=(0.5, 0.9),
))

# 8. Spray: flecks blown off the crest (the print's snow-like dots).
for _ in range(90):
    x = sx(random.uniform(230, 620))
    y = sy(random.uniform(36, 150))
    paths.append(dab(
        x, y, random.uniform(2, 6), random.uniform(0, math.pi),
        brush="splatter", color=foam,
        stroke_width=random.uniform(1.5, 3.5), opacity=random.uniform(0.5, 0.9),
    ))

# 9. Wave-wall contours: pale parallel lines following the climb of the
#    body — the woodblock's signature striations.
wall_curve = [P(40, 360), P(95, 240), P(190, 150), P(300, 116)]
paths.extend(contour_stack(
    wall_curve, offsets=[0, sx(18), sx(38), sx(60), sx(84)],
    colors=[blue_pale, pale, blue_deep, blue_pale],
    brushes=["oil_flat"],
    count_per_offset=16,
    width_range=(2, 5), length_range=(sx(16), sx(44)),
    opacity_range=(0.3, 0.6), jitter=4,
))
# Tunnel interior contours sweeping with the curl.
curl_curve = [P(310, 196), P(390, 232), P(450, 282), P(470, 318)]
paths.extend(contour_stack(
    curl_curve, offsets=[0, -sx(14), -sx(28)],
    colors=[blue_mid, blue_pale, foam],
    brushes=["oil_filbert"],
    count_per_offset=12,
    width_range=(2, 5), length_range=(sx(12), sx(32)),
    opacity_range=(0.3, 0.55), jitter=4,
))

# 10. Secondary foreground wave (the small "Fuji echo") with its own claws.
echo = f"M {sx(520)} {sy(600)} C {sx(560)} {sy(470)} {sx(640)} {sy(420)} {sx(740)} {sy(442)} C {sx(700)} {sy(470)} {sx(690)} {sy(520)} {sx(800)} {sy(560)} L {sx(800)} {sy(600)} Z"
paths.append(filled_svg_path(echo, blue_deep, fill_opacity=0.95))
echo_edge = [P(560, 470), P(640, 424), P(736, 442)]
paths.extend(edge_fingers(
    echo_edge, count=14, side=-1,
    colors=[foam, "#e8e2d2"],
    length_range=(sx(8), sx(24)), width_range=(2.5, 6),
    opacity_range=(0.7, 0.95),
))

# 11. Foreground water: layered directional bands and chop.
paths.extend(tapered_band(
    [P(0, 480), P(220, 505), P(470, 475), P(800, 500)],
    [sy(30), sy(48), sy(60), sy(52)],
    count=110, colors=[navy, blue_deep, blue_mid],
    brushes=["oil_flat", "oil_filbert"],
    flow="path", wash_rows=4, texture_ratio=0.3,
    opacity_range=(0.35, 0.7),
))
for _ in range(70):
    x = sx(random.uniform(0, 800))
    y = sy(random.uniform(440, 590))
    paths.append(line(
        x, y, x + sx(random.uniform(20, 70)), y + random.uniform(-4, 4),
        brush=random.choice(["oil_flat", "dry_brush"]),
        color=random.choice([blue_pale, pale, foam, blue_mid]),
        stroke_width=random.uniform(2.5, 6), opacity=random.uniform(0.3, 0.65),
    ))

# 12. A boat with crew, prow into the trough — the human scale anchor.
boat = f"M {sx(560)} {sy(384)} C {sx(610)} {sy(370)} {sx(680)} {sy(368)} {sx(724)} {sy(352)} C {sx(712)} {sy(380)} {sx(660)} {sy(396)} {sx(596)} {sy(398)} Z"
paths.append(filled_svg_path(boat, "#8a6a44", fill_opacity=0.95))
paths.append(filled_svg_path(
    f"M {sx(566)} {sy(384)} C {sx(615)} {sy(372)} {sx(676)} {sy(370)} {sx(716)} {sy(356)} C {sx(700)} {sy(370)} {sx(640)} {sy(384)} {sx(580)} {sy(388)} Z",
    "#6a4e30", fill_opacity=0.9,
))
for bx in (600, 628, 656, 684):
    paths.extend(small_figure_silhouette(sx(bx), sy(372), scale=sx(0.5), pose="crouch", color=navy))

output_paths(paths)
