# Agent Tools Reference

Documentation for all tools available to the Code Monet drawing agent.

## Overview

The agent has access to 5 tools for creating artwork:

| Tool              | Purpose                              | Event Display    |
| ----------------- | ------------------------------------ | ---------------- |
| `draw_paths`      | Draw predefined paths on canvas      | "drawing paths"  |
| `generate_svg`    | Generate paths via Python code       | "generating SVG" |
| `view_canvas`     | View current canvas state            | "viewing canvas" |
| `mark_piece_done` | Signal piece completion              | "marking done"   |
| `imagine`         | Generate AI reference image (Gemini) | "imagining"      |

## Tool Events

All tools emit `code_execution` events via WebSocket:

```typescript
interface CodeExecutionMessage {
  type: 'code_execution';
  status: 'started' | 'completed';
  tool_name?: ToolName | null;
  tool_input?: Record<string, unknown> | null;
  stdout?: string | null;
  stderr?: string | null;
  return_code?: number | null;
  iteration: number;
}
```

**Event Flow:**

1. Tool invoked → `code_execution(status="started")` broadcast
2. Tool completes → `code_execution(status="completed")` broadcast

The UI uses these events to show "Running Code" status and display the tool name (e.g., "imagining" for `imagine`).

---

## Drawing Tools

### `draw_paths`

Draw predefined paths on the canvas. Best for specific, manually-defined shapes.

**Parameters:**

- `paths` (required): Array of path objects to draw
- `done` (optional): Set `true` when piece is complete

**Path Object Properties:**

- `type`: `"line"` | `"polyline"` | `"quadratic"` | `"cubic"` | `"svg"`
- `points`: Array of `{x, y}` coordinates (for non-svg types)
- `d`: SVG path d-string (for type="svg")
- `color`: Hex color (Paint mode only, e.g., `"#e94560"`)
- `stroke_width`: Width 0.5-10 (Paint mode only)
- `opacity`: Opacity 0-1 (Paint mode only)

**Point Counts by Type:**
| Type | Points Required |
| ---------- | --------------- |
| `line` | 2 |
| `polyline` | 2+ |
| `quadratic`| 3 |
| `cubic` | 4 |
| `svg` | 0 (uses `d`) |

**Example:**

```json
{
  "paths": [
    {
      "type": "line",
      "points": [
        { "x": 100, "y": 100 },
        { "x": 200, "y": 200 }
      ]
    },
    { "type": "svg", "d": "M 300 300 C 350 250 450 350 500 300", "color": "#7b68ee" }
  ],
  "done": false
}
```

**Returns:** Success message + canvas image showing the new paths.

---

### `generate_svg`

Run Python code to generate paths programmatically. Best for algorithmic, mathematical, or generative drawings.

**Parameters:**

- `code` (required): Python code that outputs paths
- `done` (optional): Set `true` when piece is complete

**Available in Code:**

- `canvas_width` (800), `canvas_height` (600): Canvas dimensions
- `math`, `random`, `json`: Standard library modules

**Helper Functions (all support optional style kwargs):**

```python
line(x1, y1, x2, y2, color=None, stroke_width=None, opacity=None) -> path dict
polyline(*points, color=None, stroke_width=None, opacity=None) -> path dict
quadratic(x1, y1, cx, cy, x2, y2, color=None, stroke_width=None, opacity=None) -> path dict
cubic(x1, y1, cx1, cy1, cx2, cy2, x2, y2, color=None, stroke_width=None, opacity=None) -> path dict
svg_path(d_string, color=None, stroke_width=None, opacity=None) -> path dict
output_paths(paths_list) -> prints JSON to stdout
output_svg_paths(d_strings_list) -> prints JSON to stdout
```

**Example - Spiral:**

```python
paths = []
cx, cy = canvas_width / 2, canvas_height / 2
for i in range(100):
    t = i * 0.1
    r = 10 + t * 5
    x1, y1 = cx + r * math.cos(t), cy + r * math.sin(t)
    x2, y2 = cx + (r+5) * math.cos(t+0.1), cy + (r+5) * math.sin(t+0.1)
    paths.append(line(x1, y1, x2, y2))
output_paths(paths)
```

**Example - Colorful Spiral (Paint mode):**

```python
colors = ["#e94560", "#7b68ee", "#4ecdc4", "#ffd93d"]
paths = []
cx, cy = canvas_width / 2, canvas_height / 2
for i in range(100):
    t = i * 0.1
    r = 10 + t * 5
    x1, y1 = cx + r * math.cos(t), cy + r * math.sin(t)
    x2, y2 = cx + (r+5) * math.cos(t+0.1), cy + (r+5) * math.sin(t+0.1)
    paths.append(line(x1, y1, x2, y2, color=colors[i % len(colors)], stroke_width=2))
output_paths(paths)
```

**Returns:** Execution output + canvas image. Includes stdout/stderr if code prints or errors.

**Timeout:** 30 seconds.

---

### `mark_piece_done`

Signal that the current artwork is complete. Triggers piece save and gallery update.

**Parameters:** None

**Example:**

```json
{}
```

**Returns:** Confirmation message.

---

## Canvas Tools

### `view_canvas`

View the current canvas state as an image. Useful for planning next steps.

**Parameters:** None

**Returns:** Current canvas as PNG image.

**Visual Indicators:**

- Agent strokes: Styled per drawing mode (black in Plotter, colorful in Paint)
- Human strokes: Blue (Plotter) or rose/crimson (Paint)

---

## Image Generation Tools

### `imagine`

Generate a reference image using AI (Google Gemini). Use for visual inspiration, style references, or to visualize concepts before drawing.

**Parameters:**

- `prompt` (required): Detailed description of image to generate
- `name` (optional): Filename for saved image (without extension)

**Example:**

```json
{
  "prompt": "A serene Japanese garden with cherry blossoms at sunset, soft lighting",
  "name": "japanese_garden"
}
```

**Returns:**

- Generated image displayed inline
- Saved to `references/{name}.png` in workspace
- Can be viewed later using the Read tool on `references/` directory

**Tips for Good Prompts:**

- Be specific about subject, style, composition, and mood
- Use photographic terms: "wide angle", "close-up", "soft lighting"
- Specify art styles: "watercolor style", "line art", "minimalist"

**Example Prompts:**

- `"Simple line drawing of a cat sitting, minimal black lines on white"`
- `"Abstract geometric pattern with overlapping circles in blue and orange"`
- `"Misty mountain landscape at dawn, impressionist painting style"`

**Timeout:** 60 seconds.

**Requirements:** `GOOGLE_API_KEY` environment variable must be set.

---

## Drawing Modes

Tools behave differently based on the active drawing style:

### Plotter Mode

- Monochrome pen plotter aesthetic
- All strokes rendered in dark color
- Style properties (`color`, `stroke_width`, `opacity`) ignored
- Best for: Line art, technical drawings, minimalist pieces

### Paint Mode

- Full color painting style
- Style properties honored on paths
- Color palette available: dark, rose, violet, teal, gold, coral, green, blue, orange, purple, white
- Best for: Expressive, colorful artwork

---

## Canvas Coordinates

- **Width:** 800 pixels
- **Height:** 600 pixels
- **Origin:** Top-left (0, 0)
- **Center:** (400, 300)
- **All coordinates must be within bounds** (0-800 for X, 0-600 for Y)

---

## Tool Implementation

Tools live in `server/code_monet/tools/`. Each is a `ToolSpec` (name, description,
input schema, handler) whose handler takes the calling agent's `ToolContext`. One
server process runs many users' agents at once, so there is no module-level tool
state: every agent owns a `ToolContext` and its own MCP server, bound to it:

```python
from code_monet.tools import DRAWING_TOOLS, ToolContext

def create_drawing_server(ctx: ToolContext):
    return create_sdk_mcp_server(
        name="drawing",
        version="1.0.0",
        tools=[spec.bind(ctx) for spec in DRAWING_TOOLS],
    )
```

The OpenAI backend calls the same handlers directly with its own context.

### Tool context

`ToolContext` (`tools/context.py`) holds everything a tool call may touch:

- Turn bindings, set by the agent at the start of each turn with `bind_turn(...)`:
  `draw` (queue paths for animation), `get_canvas` (current canvas image),
  `add_strokes` (add strokes to state), `paint` (run the painting program),
  `workspace_dir`, and the canvas size.
- Piece state, kept across turns until `reset_piece()`: the finish gate
  (`gate`, a `QualityGateState`) and the latest `imagine` reference image.

---

## Adding New Tools

1. **Define the handler** in a `tools/` module:

   ```python
   async def handle_my_tool(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
       # Act only through ctx; never through module-level state
       return {"content": [{"type": "text", "text": "Success"}]}
   ```

2. **Declare the tool**:

   ```python
   my_tool = ToolSpec("my_tool", "Tool description", {schema}, handle_my_tool)
   ```

3. **Add it to `DRAWING_TOOLS`** in `tools/__init__.py` (and to the agent's allowed tools)

4. **Update TypeScript types** in `shared/src/types.ts`:
   - Add to `ToolName` union type
   - Add to `TOOL_DISPLAY_NAMES` record

5. **Rebuild shared library**: `cd shared && npm run build`
