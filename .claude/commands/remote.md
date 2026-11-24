# Remote

Remote control for Code Monet. Sends real commands to the running app and displays all WebSocket events.

## Usage

```bash
uv run python scripts/ws-client.py [command] [args]
```

## Commands

| Command | Description |
|---------|-------------|
| `watch` | Connect and display all WebSocket events |
| `start [prompt]` | Start drawing (triggers real UI, agent runs) |
| `pause` | Pause the agent |
| `resume` | Resume the agent |
| `nudge [message]` | Send nudge to agent |
| `clear` | Clear the canvas |
| `status` | Get agent status from debug endpoint |
| `view [path]` | Save canvas image to file (default: canvas.png) |
| `test "prompt" --strokes N` | Run E2E test with stroke verification |

## Event Display

- **thinking** (cyan) - Agent reasoning chunks
- **tool_use** (yellow→green) - Tool started→completed
- **paths** (magenta) - Canvas drawing data
- **status** (green) - Agent state changes
- **error** (red) - Errors

## Full Flow Test

### 1. Start drawing and watch events
```bash
uv run python scripts/ws-client.py start "draw a red circle"
```
**Verify:** Thinking (cyan) appears BEFORE tool completions (green)

### 2. Verify canvas updates
**Verify:** `paths` events (magenta) arrive with drawing data

### 3. Test pause mid-drawing
```bash
# While agent is running, in another terminal:
uv run python scripts/ws-client.py pause
```
**Verify:** Status changes to paused. Canvas retains current strokes.

### 4. Test resume
```bash
uv run python scripts/ws-client.py resume
```
**Verify:** Agent continues, more events flow.

## Quick Check

```bash
uv run python scripts/ws-client.py status
```

## Server Logs

Use Platform's `box` CLI for production server access:

```bash
box logs drawing-agent                     # Container logs
box run --command 'docker restart drawing-agent'
box run --command 'docker exec drawing-agent <command>'
box run --command '<host command>'
```

For local dev, use the debug endpoint:
```bash
curl -s "localhost:8000/debug/logs?lines=50"
```

See also: `/logs` and `/diagnose` commands for detailed log queries.
