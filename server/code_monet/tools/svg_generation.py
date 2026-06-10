"""SVG generation tool using Python code execution."""

from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import tool

from .callbacks import (
    get_add_strokes_callback,
    get_canvas_dimensions,
    get_draw_callback,
    inject_canvas_image,
)
from .python_sandbox import run_python_code
from .quality_gate import (
    finish_block_message,
    note_drawing,
)

logger = logging.getLogger(__name__)

AUTO_CANVAS_IMAGE_PATH_LIMIT = 160


async def handle_generate_svg(args: dict[str, Any]) -> dict[str, Any]:
    """Handle generate_svg tool call (testable without decorator).

    Args:
        args: Dictionary with 'code' (Python code string) and optional 'done' (bool)

    Returns:
        Tool result with execution output and drawn paths
    """
    code = args.get("code", "")
    done = args.get("done", False)
    block_done_message = finish_block_message() if done else None
    effective_done = done and block_done_message is None

    if not code or not isinstance(code, str):
        return {
            "content": [{"type": "text", "text": "Error: code must be a non-empty string"}],
            "is_error": True,
        }

    # Run the Python code
    canvas_width, canvas_height = get_canvas_dimensions()
    result = await run_python_code(code, canvas_width, canvas_height)

    stdout = result["stdout"]
    stderr = result["stderr"]
    return_code = result["return_code"]
    paths = result["paths"]

    # Build response message
    response_parts = []

    if return_code != 0:
        response_parts.append(f"Code execution failed (exit code {return_code})")
        if stderr:
            response_parts.append(f"Errors:\n{stderr[:1000]}")
        return {
            "content": [{"type": "text", "text": "\n".join(response_parts)}],
            "is_error": True,
        }

    # Add strokes to state immediately (so canvas image includes them)
    _add_strokes_callback = get_add_strokes_callback()
    _draw_callback = get_draw_callback()

    logger.info(
        f"generate_svg: {len(paths)} paths, add_strokes={'set' if _add_strokes_callback else 'None'}"
    )
    if paths and _add_strokes_callback is not None:
        await _add_strokes_callback(paths)
        note_drawing(len(paths))
        response_parts.append(f"Successfully generated and drew {len(paths)} paths.")
    elif paths:
        note_drawing(len(paths))
        response_parts.append(f"Code executed and generated {len(paths)} paths.")
    elif not paths:
        response_parts.append(
            "Code executed but no paths were generated. "
            "Make sure to call output_paths() or output_svg_paths() at the end."
        )
    # Call the draw callback for animation (strokes already in state)
    logger.info(
        f"generate_svg: triggering animation, callback={'set' if _draw_callback else 'None'}"
    )
    if paths and _draw_callback is not None:
        await _draw_callback(paths, effective_done)

    if effective_done:
        response_parts.append("Piece marked as complete.")
    elif block_done_message is not None:
        response_parts.append(block_done_message)

    # Include stdout if there's additional output
    if stdout and not stdout.strip().startswith("{"):
        response_parts.append(f"Output:\n{stdout[:500]}")

    # Build response content
    content: list[dict[str, Any]] = [{"type": "text", "text": "\n".join(response_parts)}]

    # Inject canvas image for small batches. Large generated batches can exceed SDK
    # transport limits; the agent can call view_canvas explicitly when it needs inspection.
    if 0 < len(paths) <= AUTO_CANVAS_IMAGE_PATH_LIMIT:
        inject_canvas_image(content)
    elif paths:
        content[0]["text"] += " Canvas image omitted for dense batch; call view_canvas to inspect."

    return {"content": content}


@tool(
    "generate_svg",
    """Run Python code to generate SVG paths programmatically. Use this for algorithmic, mathematical, or complex generative drawings.

IMPORTANT: Use canvas_width and canvas_height from the runtime. All coordinates must be within those bounds.

The code has access to:
- canvas_width, canvas_height: Use for positioning within bounds
- math, random, json: Standard library modules
- BRUSHES: list of available brush names for Paint mode
- Helper functions (line/curve helpers accept optional brush, color, stroke_width, opacity kwargs for Paint mode; filled helpers accept fill/fill_opacity):
  - line(x1, y1, x2, y2, brush=None, color=None, stroke_width=None, opacity=None) -> path dict
  - dab(x, y, length, angle, brush="oil_filbert", color=None, stroke_width=None, opacity=None) -> centered short brush mark
  - rect_shape(x, y, width, height, fill, fill_opacity=1.0, stroke=None, stroke_width=0, opacity=None) -> filled rectangle
  - ellipse_shape(cx, cy, rx, ry, fill, fill_opacity=1.0, stroke=None, stroke_width=0, opacity=None) -> filled ellipse
  - filled_polygon_path(vertices, fill, fill_opacity=1.0, stroke=None, stroke_width=0, opacity=None) -> filled polygon
  - filled_svg_path(d_string, fill, fill_opacity=1.0, stroke=None, stroke_width=0, opacity=None) -> filled closed SVG path; keep stroke_width=0 unless the closing edge should be visible
  - background_wash(count=420, stops=None, y_range=None, angle=0, angle_jitter=0.08, length_range=None, width_range=None, brushes=None, opacity_range=None, exclude_polygons=None, wash_rows=14, texture_ratio=0.18) -> full-canvas colored ground before subject marks
  - stroke_field(count, x_range=None, y_range=None, angle=0, angle_jitter=0.2, length_range=None, width_range=None, colors=None, brushes=None, opacity_range=None, exclude_polygons=None) -> list of atmospheric or textural marks; use exclude_polygons to reserve silhouettes
  - ramp_field(count, x_range=None, y_range=None, axis="y", stops=None, angle=0, angle_jitter=0.16, length_range=None, width_range=None, brushes=None, opacity_range=None, exclude_polygons=None, wash_rows=None, texture_ratio=1.0) -> list of directional color-ramp marks
  - curve_marks(points, count=48, length_range=None, width_range=None, colors=None, brushes=None, opacity_range=None, jitter=5) -> list of marks along a skeleton
  - mass_field(vertices, count=180, colors=None, stops=None, axis="y", angle=0, angle_jitter=0.28, length_range=None, width_range=None, brushes=None, opacity_range=None, wash_rows=None, edge=False, texture_ratio=1.0) -> list of marks filling a closed value mass
  - curve_band(top_points, bottom_points=None, bottom_y=None, count=180, colors=None, stops=None, axis="depth", brushes=None, length_range=None, width_range=None, opacity_range=None, angle_jitter=0.28, edge=True, wash_rows=None, texture_ratio=1.0) -> list of marks filling a curved band
  - tapered_band(center_points, widths, count=150, colors=None, stops=None, axis="y", flow="horizontal", brushes=None, length_range=None, width_range=None, opacity_range=None, angle_jitter=0.18, wash_rows=None, edge=False, texture_ratio=1.0) -> list of marks filling a tapered ribbon around a centerline
  - broken_edge(points, count=64, colors=None, brushes=None, length_range=None, width_range=None, opacity_range=None, spread=6, side=0, angle_jitter=0.32) -> list of feathered edge marks
  - fill_polygon(vertices, count=120, angle=0, angle_jitter=0.35, length_range=None, width_range=None, colors=None, brushes=None, opacity_range=None, edge=True) -> list of marks filling a polygon
  - glow_field(cx, cy, radius, count=140, colors=None, brushes=None, length_range=None, width_range=None, opacity_range=None, elliptical_y=0.72, exclude_polygons=None, core_marks=None) -> list of soft radial light or atmosphere marks
  - reflection_field(cx, y, width, height, count=72, angle=0, colors=None, brushes=None, opacity_range=None) -> list of tapering reflected marks
  - radial_cluster(cx, cy, count=160, rx=80, ry=60, colors=None, brushes=None, length_range=None, width_range=None, opacity_range=None) -> list of organic clustered marks
  - sector_bounds(column, row, columns=3, rows=3, padding=0) -> (left, top, right, bottom) for compositional planning and audits
  - sector_vertices(column, row, columns=3, rows=3, padding=0) -> rectangle vertices for reserving, filling, or checking a sector
  - contour_stack(points, offsets=None, colors=None, brushes=None, count_per_offset=16, width_range=None, length_range=None, opacity_range=None, jitter=5) -> repeated offset contours and short marks around any flowing edge, fold, current, ridge, fabric, smoke, or body plane
  - edge_fingers(points, count=18, side=-1, colors=None, brushes=None, length_range=None, width_range=None, opacity_range=None) -> tapered organic projections from an edge such as foam, flame, leaves, hair, spray, torn cloth, or bright accents
  - curved_ribbon_mass(center_points, widths, fill, fill_opacity=0.92, stroke=None, stroke_width=0, contour_color=None, contour_count=0) -> filled variable-width ribbon around a centerline for separate folded lips, overhangs, loops, smoke curls, fabric edges, limbs, branches, or bold graphic strokes
  - crescent_mass(cx, cy, rx, ry, fill, cutout_fill, curl="right", fill_opacity=0.92, cutout_opacity=0.96, stroke=None, stroke_width=0, cutout_stroke=None, cutout_stroke_width=0) -> generic curved mass with an explicit negative-space bite for curls, moons, arches, smoke loops, cloud scrolls, or hollow forms
  - small_figure_silhouette(cx, cy, scale=1, pose="crouch", color="#0b263e", ground=False, ground_color="#734534") -> readable human-scale anchor with head, torso, limbs, and optional ground/contact mark
  - small_figure_with_prop(cx, cy, scale=1, pose="crouch", color="#0b263e", prop_color="#39405a", prop_length=78, prop_width=10, prop_angle=0, ground=False, ground_color="#734534") -> small readable figure attached to a broad prop such as a board, vehicle, instrument, tool, handle, or beam
  - polyline(*points, brush=None, color=None, stroke_width=None, opacity=None) -> path dict (points are (x,y) tuples)
  - quadratic(x1, y1, cx, cy, x2, y2, brush=None, color=None, stroke_width=None, opacity=None) -> path dict
  - cubic(x1, y1, cx1, cy1, cx2, cy2, x2, y2, brush=None, color=None, stroke_width=None, opacity=None) -> path dict
  - svg_path(d_string, brush=None, color=None, stroke_width=None, opacity=None, fill=None, fill_opacity=None) -> path dict
  - output_paths(paths_list) -> prints JSON to stdout
  - output_svg_paths(d_strings_list) -> prints JSON to stdout

Available brushes (BRUSHES list):
- oil_round: Classic round brush, visible bristle texture
- oil_flat: Flat brush, parallel marks
- oil_filbert: Rounded flat, organic shapes
- watercolor: Translucent, soft edges
- dry_brush: Scratchy, broken strokes
- palette_knife: Sharp edges, thick paint
- ink: Pressure-sensitive, elegant taper
- pencil: Thin, consistent lines
- charcoal: Smudgy edges, texture
- marker: Solid color, slight bleed
- airbrush: Very soft edges
- splatter: Random dots around stroke

Example - draw a spiral centered on canvas:
```python
paths = []
cx, cy = canvas_width / 2, canvas_height / 2  # (400, 300)
for i in range(100):
    t = i * 0.1
    r = 10 + t * 5
    x1, y1 = cx + r * math.cos(t), cy + r * math.sin(t)
    x2, y2 = cx + (r+5) * math.cos(t+0.1), cy + (r+5) * math.sin(t+0.1)
    paths.append(line(x1, y1, x2, y2))
output_paths(paths)
```

Example - oil painting with brush strokes (Paint mode):
```python
colors = ["#e94560", "#7b68ee", "#4ecdc4", "#ffd93d"]
paths = []
cx, cy = canvas_width / 2, canvas_height / 2
for i in range(50):
    t = i * 0.15
    r = 20 + t * 8
    x1, y1 = cx + r * math.cos(t), cy + r * math.sin(t)
    x2, y2 = cx + (r+20) * math.cos(t+0.15), cy + (r+20) * math.sin(t+0.15)
    paths.append(line(x1, y1, x2, y2, brush="oil_round", color=colors[i % len(colors)]))
output_paths(paths)
```

Example - watercolor wash:
```python
paths = []
for y in range(50, 550, 30):
    pts = [(x, y + random.uniform(-5, 5)) for x in range(50, 750, 20)]
    paths.append(polyline(*pts, brush="watercolor", color="#4ecdc4", opacity=0.3))
output_paths(paths)
```

Example - color-filled background:
```python
paths = []
paths.append(rect_shape(0, 0, canvas_width, canvas_height, "#dbe7f4"))
paths.extend(background_wash(
    count=420,
    stops=[(0.0, ["#dbe7f4", "#c9d9ee"]), (0.65, ["#f7ead0", "#e9d9b5"]), (1.0, ["#8faec0", "#5d7f9c"])],
    wash_rows=14,
    texture_ratio=0.16,
))
output_paths(paths)
```

Example - layered value masses with a clear negative space:
```python
paths = []
ground = "#eadfc7"
body = "#2f7897"
dark = "#0d2f4c"
light = "#eef4ef"
paths.append(rect_shape(0, 0, canvas_width, canvas_height, ground))
mass = f"M 0 {canvas_height*0.55} C {canvas_width*0.3} {canvas_height*0.38} {canvas_width*0.7} {canvas_height*0.46} {canvas_width} {canvas_height*0.4} L {canvas_width} {canvas_height} L 0 {canvas_height} Z"
paths.append(filled_svg_path(mass, body, fill_opacity=0.9))
cut = f"M {canvas_width*0.55} {canvas_height*0.46} C {canvas_width*0.7} {canvas_height*0.4} {canvas_width*0.85} {canvas_height*0.44} {canvas_width*0.95} {canvas_height*0.52} C {canvas_width*0.8} {canvas_height*0.56} {canvas_width*0.62} {canvas_height*0.54} {canvas_width*0.55} {canvas_height*0.46} Z"
paths.append(filled_svg_path(cut, light, fill_opacity=0.85))
paths.extend(tapered_band(
    [(0, canvas_height*0.82), (canvas_width*0.35, canvas_height*0.86), (canvas_width, canvas_height*0.82)],
    [26, 46, 34],
    colors=[dark, "#1f5d82", body],
    count=90,
    texture_ratio=0.45,
))
output_paths(paths)
```""",
    {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute. Must call output_paths() or output_svg_paths() at the end.",
            },
            "done": {
                "type": "boolean",
                "description": "Set to true when the piece is complete",
                "default": False,
            },
        },
        "required": ["code"],
    },
)
async def generate_svg(args: dict[str, Any]) -> dict[str, Any]:
    """Generate SVG paths using Python code."""
    return await handle_generate_svg(args)
