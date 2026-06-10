"""Debug endpoints for development and troubleshooting."""

from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import APIRouter, Body, HTTPException, Query, Request

from code_monet.auth.dependencies import CurrentUser
from code_monet.config import settings
from code_monet.registry import workspace_registry
from code_monet.routes.canvas import get_user_state
from code_monet.tools.quality_gate import get_quality_gate_snapshot
from code_monet.types import AgentStatus, PausedMessage
from code_monet.user_handlers import handle_new_canvas

router = APIRouter()

# Browser console log forwarding
BROWSER_LOG_FILE = Path("/tmp/code-monet-browser.log")


@router.get("/debug/agent")
async def get_agent_debug(user: CurrentUser) -> dict[str, Any]:
    """Get agent debug info for user's workspace."""
    workspace = workspace_registry.get(user.id)
    if not workspace:
        # Return state from file if no active workspace
        state = await get_user_state(user)
        return {
            "paused": True,
            "status": state.status.value,
            "piece_number": state.piece_number,
            "notes": state.notes[:500] if state.notes else None,
            "monologue": state.monologue[:500] if state.monologue else None,
            "stroke_count": len(state.canvas.strokes),
            "connected_clients": 0,
            "quality_gate": get_quality_gate_snapshot(),
        }

    state = workspace.state
    return {
        "paused": workspace.agent.paused,
        "status": state.status.value,
        "piece_number": state.piece_number,
        "notes": state.notes[:500] if state.notes else None,
        "monologue": state.monologue[:500] if state.monologue else None,
        "stroke_count": len(state.canvas.strokes),
        "connected_clients": workspace.connections.connection_count,
        "quality_gate": get_quality_gate_snapshot(),
    }


@router.get("/debug/workspace")
async def get_workspace_debug(user: CurrentUser) -> dict[str, Any]:
    """Get workspace files and state for debugging."""
    workspace_dir = Path("agent_workspace") / "users" / str(user.id)

    files = []
    if workspace_dir.exists():
        for file_path in workspace_dir.rglob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                files.append(
                    {
                        "name": file_path.name,
                        "path": str(file_path.relative_to(workspace_dir)),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    }
                )

    return {"files": files}


@router.post("/debug/reset")
async def reset_workspace_debug(user: CurrentUser) -> dict[str, Any]:
    """Reset workspace state for testing. Only available in DEV_MODE."""
    if not settings.dev_mode:
        raise HTTPException(status_code=403, detail="Only available in dev mode")

    workspace = await workspace_registry.get_or_activate(user.id)
    state = workspace.state
    agent = workspace.agent

    # Clear canvas, notes, and agent state
    state.canvas.strokes.clear()
    state.notes = ""
    state.monologue = ""
    state.piece_number = 0
    state.status = AgentStatus.PAUSED
    if agent:
        agent.pending_nudges.clear()
        await agent.pause()
        agent.reset_container()

    # Persist the cleared state
    await state.save()

    # Broadcast updates to all connected clients
    await workspace.connections.broadcast({"type": "clear"})
    await workspace.connections.broadcast(PausedMessage(paused=True))

    return {"status": "reset", "piece_number": 0, "paused": True}


@router.post("/debug/new-canvas")
async def debug_new_canvas(
    user: CurrentUser,
    direction: str | None = Body(default=None, embed=True),
    drawing_style: str | None = Body(default=None, embed=True),
) -> dict[str, Any]:
    """Trigger new canvas from server side (dev mode only)."""
    if not settings.dev_mode:
        raise HTTPException(status_code=403, detail="Only available in dev mode")

    workspace = await workspace_registry.get_or_activate(user.id)

    # Build message matching client format
    message: dict[str, Any] = {}
    if direction:
        message["direction"] = direction
    if drawing_style:
        message["drawing_style"] = drawing_style

    # Reuse existing handler
    await handle_new_canvas(workspace, message if message else None)

    return {
        "status": "new_canvas_triggered",
        "direction": direction,
        "drawing_style": drawing_style,
        "piece_number": workspace.state.piece_number,
    }


@router.get("/debug/logs")
async def get_debug_logs(_user: CurrentUser, lines: int = 100) -> dict[str, Any]:
    """Get recent server logs."""
    log_path = Path(__file__).parent.parent / "logs" / "server.log"
    if not log_path.exists():
        return {"error": "Log file not found. Use 'make server-bg' to start with logging."}

    try:
        with open(log_path) as f:
            all_lines = f.readlines()
            recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return {
                "total_lines": len(all_lines),
                "returned_lines": len(recent),
                "logs": "".join(recent),
            }
    except Exception as e:
        return {"error": str(e)}


@router.get("/debug/agent-logs")
async def get_agent_logs(
    user: CurrentUser,
    filename: str | None = Query(default=None),
    count: int = Query(default=5, ge=1, le=50),
) -> dict[str, Any]:
    """Get agent activity logs for the authenticated user.

    Each agent turn creates a separate timestamped log file containing:
    - Turn start/end timestamps
    - Agent thinking/monologue text
    - Code execution results
    - Drawing commands
    - Errors

    Args:
        filename: Specific log file to read (e.g., "turn_20240115_143022.log")
        count: Number of recent log files to return (default 5, max 50)

    Returns:
        If filename provided: Dict with single log file content
        Otherwise: Dict with list of recent log files and their content
    """
    from code_monet.agent_logger import AgentFileLogger

    state = await get_user_state(user)
    file_logger = AgentFileLogger(user_dir=state._user_dir)

    if filename:
        # Read specific file - TypedDict is compatible with dict[str, Any]
        result = await file_logger.read_log_file(filename)
        return dict(result)

    # Return list of recent log files with content
    files = await file_logger.list_log_files()
    logs = await file_logger.read_latest_logs(count=count)

    return {
        "total_files": len(files),
        "returned_files": len(logs),
        "logs": [dict(log) for log in logs],
    }


@router.post("/debug/log")
async def debug_log(request: Request) -> dict[str, bool]:
    """Receive forwarded browser/app console logs to dedicated file (dev mode only)."""
    if not settings.dev_mode:
        raise HTTPException(status_code=404, detail="Not found")
    data = await request.json()
    timestamp = datetime.now().isoformat()
    session_id = data.get("session_id", "unknown")
    level = data.get("level", "log")
    message = data.get("message", "")

    line = f"[{timestamp}][{session_id}][{level}] {message}\n"
    async with aiofiles.open(BROWSER_LOG_FILE, "a") as f:
        await f.write(line)
    return {"ok": True}


@router.post("/debug/log/session")
async def debug_log_session(request: Request) -> dict[str, Any]:
    """Start a new logging session with clear marker (dev mode only)."""
    if not settings.dev_mode:
        raise HTTPException(status_code=404, detail="Not found")
    data = await request.json()
    session_id = data.get("session_id", "unknown")
    timestamp = datetime.now().isoformat()

    marker = f"\n{'=' * 60}\n[SESSION START] {session_id} at {timestamp}\n{'=' * 60}\n"
    async with aiofiles.open(BROWSER_LOG_FILE, "a") as f:
        await f.write(marker)
    return {"ok": True, "session_id": session_id}
