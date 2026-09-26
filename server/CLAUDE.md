# Server - Python Standards

Backend-specific guidance for the Code Monet server.

## Type Safety

### No `Any` - Use Specific Types

```python
# Bad
def process(data: Any) -> Any:
    ...

# Good
def process(data: PendingStrokeDict) -> list[Path]:
    ...
```

### Use TypedDict for Dictionary Structures

When passing dicts between functions, define the shape:

```python
# In types.py
class PendingStrokeDict(TypedDict):
    batch_id: int
    path: dict[str, Any]  # Serialized Pydantic model is ok
    points: list[PointDict]

# Usage
def queue_strokes(self) -> list[PendingStrokeDict]:
    ...
```

### Forward References

Use `from __future__ import annotations` to avoid string quotes:

```python
from __future__ import annotations

class Foo:
    def method(self) -> Foo:  # No quotes needed
        ...
```

## Async Patterns

### Use asyncio.Lock for Shared State

```python
class WorkspaceState:
    def __init__(self):
        self._lock = asyncio.Lock()

    async def modify(self):
        async with self._lock:
            # Safe to modify
            ...
```

### Event-Driven Wake-up (Not Polling)

Replace `asyncio.sleep()` polling with `asyncio.Event`:

```python
# Bad - wastes resources, adds latency
while True:
    if should_run():
        await do_work()
    await asyncio.sleep(10)  # 10 second delay!

# Good - immediate wake-up
self._wake_event = asyncio.Event()

async def run_loop(self):
    while True:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake_event.wait(), timeout=10)
        self._wake_event.clear()
        if should_run():
            await do_work()

def wake(self):
    self._wake_event.set()
```

### CPU-Bound Work to Thread Pool

```python
# Bad - blocks event loop
image_data = render_image(canvas)

# Good - runs in thread pool
image_data = await asyncio.to_thread(render_image, canvas)
```

## Rate Limiting

Use the `RateLimiter` class for any per-user limits:

```python
from drawing_agent.rate_limiter import RateLimiter, RateLimiterConfig

limiter = RateLimiter(RateLimiterConfig(
    max_requests=60,
    window_seconds=60.0,
))

if not limiter.is_allowed(user_id):
    raise RateLimitError()
```

## Data Models

### Pydantic for External Data

Use Pydantic models for:
- API request/response bodies
- WebSocket messages
- Persisted data (JSON files)

```python
class Path(BaseModel):
    type: PathType
    points: list[Point]
```

### Dataclass for Internal State

Use dataclass for internal orchestration:

```python
@dataclass
class AgentOrchestrator:
    agent: DrawingAgent
    broadcaster: Broadcaster
    _wake_event: asyncio.Event = field(default_factory=asyncio.Event)
```

## Testing

### New Features Need Tests

Every new class/function needs tests. Check existing patterns:
- `test_rate_limiter.py` - Unit tests for utility classes
- `test_orchestrator_wake.py` - Async tests with mocks
- `test_workspace_limits.py` - Integration tests with tmp_path

### Test Structure

```python
class TestFeatureName:
    """Group related tests."""

    @pytest.mark.asyncio
    async def test_specific_behavior(self) -> None:
        """Describe expected behavior."""
        # Arrange
        ...
        # Act
        ...
        # Assert
        ...
```

### Injectable Time for Rate Limiters

```python
# Make time injectable for testing
def is_allowed(self, key: int, now: float | None = None) -> bool:
    if now is None:
        now = time.time()
    ...

# In tests
assert limiter.is_allowed(user_id, now=0.0)
assert limiter.is_allowed(user_id, now=61.0)  # After window
```

## Error Handling

### Provide Context

```python
# Bad
raise ValueError("Invalid")

# Good
raise ValueError(f"Invalid user_id: {user_id}, must be positive integer")
```

### Log Before Raising

```python
logger.warning(f"User {user_id}: rate limited ({remaining} remaining)")
raise RateLimitError(...)
```

## Image Rendering

All canvas-to-image rendering uses the centralized `rendering.py` module.

### RenderOptions Dataclass

Configure rendering with `RenderOptions`:

```python
from code_monet.rendering import RenderOptions, render_strokes

options = RenderOptions(
    width=800,
    height=600,
    background_color="#FFFFFF",  # or tuple (r, g, b, a)
    drawing_style=DrawingStyleType.PLOTTER,
    highlight_human=False,
    expand_brushes=False,  # True for paint mode visibility
    scale_from=(800, 600),  # Source dims for scaling
    scale_padding=50,
    output_format="bytes",  # "image", "bytes", or "base64"
    optimize_png=False,
)
result = render_strokes(strokes, options)
```

### Preset Factories

Use preset factories for common scenarios:

```python
from code_monet.rendering import (
    options_for_agent_view,    # Agent sees canvas with human highlights
    options_for_og_image,      # 1200x630 social sharing
    options_for_thumbnail,     # 800x600 gallery thumbnail
    options_for_share_preview, # 800x600 optimized PNG
)

# Agent view (returns PIL Image)
options = options_for_agent_view(canvas)
img = render_strokes(canvas.strokes, options)

# OG image (dark bg, scaled, white strokes for plotter)
options = options_for_og_image(drawing_style)
png_bytes = await render_strokes_async(strokes, options)
```

### Async Rendering

Use `render_strokes_async` for non-blocking rendering:

```python
from code_monet.rendering import render_strokes_async

# Runs in thread pool, doesn't block event loop
result = await render_strokes_async(strokes, options)
```

### Adding New Rendering Scenarios

1. Add a preset factory in `rendering.py` if the scenario is reusable
2. Or construct `RenderOptions` directly for one-off cases
3. Never duplicate rendering logic - always use `render_strokes()`

## Module Architecture

The server is organized into focused packages:

```
code_monet/
├── agent/           # Claude Agent SDK integration
├── tools/           # MCP drawing tools
├── workspace/       # Per-user state management
├── types/           # Type definitions
├── routes/          # HTTP route handlers
├── auth/            # Authentication (JWT, magic links)
├── db/              # Database models and repository
├── share/           # Public sharing functionality
└── *.py             # Core modules (config, rendering, etc.)
```

### agent/ - Claude Agent SDK Integration

The drawing agent using Claude Agent SDK:

```python
from code_monet.agent import DrawingAgent, AgentCallbacks, SYSTEM_PROMPT

# Create agent with user workspace
agent = DrawingAgent(state=workspace_state)

# Run a turn with callbacks
async for event in agent.run_turn(callbacks):
    if isinstance(event, AgentTurnComplete):
        print(f"Done: {event.done}, Thinking: {event.thinking[:100]}")
```

**Key files:**
- `__init__.py` - DrawingAgent class, public API
- `prompts.py` - System prompt and style-specific instructions
- `processor.py` - Message stream processing
- `renderer.py` - Canvas image helpers

### tools/ - MCP Drawing Tools

All agent tools as an MCP server, one per agent. Each tool handler takes the calling
agent's `ToolContext`; there is no module-level tool state, because one process runs
many users' agents concurrently.

```python
from code_monet.tools import ToolContext, create_drawing_server

server = create_drawing_server(agent.tool_context)  # tools act only on this agent

# Tools available to agent:
# - draw_paths: Draw paths on canvas
# - generate_svg: Generate paths via Python code
# - view_canvas: View current canvas state
# - mark_piece_done: Signal piece completion
# - imagine: Generate AI reference image (Gemini)
# - sign_canvas: Add artist signature
# - name_piece: Title the artwork
# - critique_canvas: Visual finish gate
# - paint: Run the painting program (paint mode)
```

**Key files:**
- `__init__.py` - Server factory (`create_drawing_server(ctx)`), `DRAWING_TOOLS`, exports
- `context.py` - `ToolContext` (per-agent turn bindings + piece state) and `ToolSpec`
- `quality_gate.py` - `QualityGateState`, the per-agent critique finish gate
- `drawing.py` - draw_paths, mark_piece_done, view_canvas
- `svg_generation.py` - generate_svg tool handler
- `python_sandbox.py` - Python subprocess execution for generate_svg
- `image_generation.py` - imagine (Gemini integration)
- `signature.py` - sign_canvas
- `naming.py` - name_piece
- `critique.py` - critique_canvas
- `paint.py` - paint
- `path_parsing.py` - Parse path data from various formats

### workspace/ - Per-User State Management

Filesystem-backed workspace state:

```python
from code_monet.workspace import WorkspaceState

# Load workspace for a user
state = await WorkspaceState.load_for_user(user_id)

# Canvas operations
await state.add_stroke(path)
await state.clear_canvas()
saved_id = await state.new_canvas()  # Save to gallery and start fresh

# Stroke queue for client-side rendering
batch_id, point_count = await state.queue_strokes(paths)
pending = await state.pop_strokes()

# Gallery operations
entries = await state.list_gallery()
strokes, style = await state.load_from_gallery(piece_number)
```

**Key files:**
- `__init__.py` - WorkspaceState class
- `persistence.py` - Atomic file writes, directory helpers
- `gallery.py` - Gallery scanning and loading
- `strokes.py` - Stroke interpolation and limits

**Filesystem layout:**
```
agent_workspace/users/{user_id}/
├── workspace.json       # Current state
└── gallery/
    └── piece_000001.json  # Saved artwork
```

### types/ - Type Definitions

Organized into focused modules:

```python
from code_monet.types import (
    # Geometry
    Point, PathType, PendingStrokeDict,
    # Paths
    Path,
    # State
    CanvasState, AgentStatus, GalleryEntry,
    # Styles
    DrawingStyleType, DrawingStyleConfig, get_style_config,
    # Brushes
    BrushPreset, get_brush_preset,
    # Messages
    ServerMessage, ClientMessage, AgentTurnComplete,
)
```

**Modules:**
- `geometry.py` - Point, PathType, coordinate types
- `paths.py` - Path model for drawable strokes
- `state.py` - Canvas, agent, gallery state models
- `styles.py` - Drawing style configurations (PLOTTER, PAINT)
- `brushes.py` - Brush presets
- `messages.py` - WebSocket message types

### routes/ - HTTP Route Handlers

FastAPI routers extracted from main.py:

```python
from code_monet.routes import create_api_router

app = FastAPI()
app.include_router(create_api_router())
```

**Routes:**
- `health.py` - /health, /api/version
- `canvas.py` - Canvas state endpoints
- `gallery.py` - User gallery endpoints
- `public_gallery.py` - Public piece viewing
- `strokes.py` - Stroke data endpoints
- `seo.py` - OG image generation
- `apple.py` - Apple app-site-association
- `debug.py` - Debug endpoints (dev only)
- `auth_dev.py` - Dev auth token endpoint
- `tracing.py` - X-Ray trace ID endpoint

### Other Core Modules

| Module | Purpose |
|--------|---------|
| `config.py` | Settings from environment |
| `rendering.py` | Canvas-to-image rendering |
| `orchestrator.py` | Agent loop management |
| `connections.py` | WebSocket ConnectionManager |
| `user_handlers.py` | WebSocket message handlers |
| `interpolation.py` | Path interpolation functions |
| `brushes.py` | Brush expansion for paint mode |
| `svg_parser.py` | SVG path parsing |
| `rate_limiter.py` | Rate limiting utility |
| `tracing.py` | OpenTelemetry setup |
| `shutdown.py` | Graceful shutdown handling |
| `registry.py` | User orchestrator registry |
| `cli.py` | CLI commands (invite, user, workspace) |

## File Organization

| Type | Location |
|------|----------|
| Pydantic models, TypedDicts, Enums | `types/` package |
| Configuration | `config.py` |
| Image rendering | `rendering.py` |
| Reusable utilities | New file (e.g., `rate_limiter.py`) |
| WebSocket handlers | `user_handlers.py` |
| Routes | `routes/` package |
| Tests | `tests/test_<module>.py` |
