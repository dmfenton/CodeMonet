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

logger = logging.getLogger(__name__)


async def handle_generate_svg(args: dict[str, Any]) -> dict[str, Any]:
    """Handle generate_svg tool call (testable without decorator).

    Args:
        args: Dictionary with 'code' (Python code string) and optional 'done' (bool)

    Returns:
        Tool result with execution output and drawn paths
    """
    code = args.get("code", "")
    done = args.get("done", False)

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
        response_parts.append(f"Successfully generated and drew {len(paths)} paths.")
    elif paths:
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
        await _draw_callback(paths, done)

    if done:
        response_parts.append("Piece marked as complete.")

    # Include stdout if there's additional output
    if stdout and not stdout.strip().startswith("{"):
        response_parts.append(f"Output:\n{stdout[:500]}")

    # Build response content
    content: list[dict[str, Any]] = [{"type": "text", "text": "\n".join(response_parts)}]

    # Inject canvas image if we drew paths
    if paths:
        inject_canvas_image(content)

    return {"content": content}


@tool(
    "generate_svg",
    """Run Python code to generate SVG paths programmatically. Use this for algorithmic, mathematical, or complex generative drawings.

IMPORTANT: Canvas is 800x600. All coordinates must be within X: 0-800, Y: 0-600. Center is (400, 300).

The code has access to:
- canvas_width (800), canvas_height (600): Use for positioning within bounds
- math, random, json: Standard library modules
- BRUSHES: list of available brush names for Paint mode
- Helper functions (all accept optional brush, color, stroke_width, opacity kwargs for Paint mode):
  - line(x1, y1, x2, y2, brush=None, color=None, stroke_width=None, opacity=None) -> path dict
  - dab(x, y, length, angle, brush="oil_filbert", color=None, stroke_width=None, opacity=None) -> centered short brush mark
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
  - polyline(*points, brush=None, color=None, stroke_width=None, opacity=None) -> path dict (points are (x,y) tuples)
  - quadratic(x1, y1, cx, cy, x2, y2, brush=None, color=None, stroke_width=None, opacity=None) -> path dict
  - cubic(x1, y1, cx1, cy1, cx2, cy2, x2, y2, brush=None, color=None, stroke_width=None, opacity=None) -> path dict
  - svg_path(d_string, brush=None, color=None, stroke_width=None, opacity=None) -> path dict
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
