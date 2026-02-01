"""WebSocket message handlers for multi-user workspaces.

Each handler receives the ActiveWorkspace context for the authenticated user.
"""

import logging
from typing import Any

from code_monet.config import settings
from code_monet.rate_limiter import RateLimiter, RateLimiterConfig
from code_monet.registry import ActiveWorkspace
from code_monet.types import (
    AgentStatus,
    ClearMessage,
    DrawingStyleType,
    LoadCanvasMessage,
    NewCanvasMessage,
    Path,
    PathType,
    PausedMessage,
    PauseReason,
    PieceStateMessage,
    get_style_config,
    Point,
)

logger = logging.getLogger(__name__)

# Rate limiter for user strokes
_stroke_limiter = RateLimiter(
    RateLimiterConfig(
        max_requests=settings.max_strokes_per_minute,
        window_seconds=60.0,
    )
)


async def handle_stroke(workspace: ActiveWorkspace, message: dict[str, Any]) -> None:
    """Handle a stroke from the user."""
    # Rate limit check
    if not _stroke_limiter.is_allowed(workspace.user_id):
        remaining_info = f"({_stroke_limiter.remaining(workspace.user_id)} remaining)"
        logger.warning(f"User {workspace.user_id}: stroke rate limited {remaining_info}")
        await workspace.connections.broadcast(
            {"type": "error", "message": "Drawing too fast. Please slow down."}
        )
        return

    points = [Point(x=p["x"], y=p["y"]) for p in message.get("points", [])]
    if points:
        path = Path(type=PathType.POLYLINE, points=points, author="human")
        await workspace.state.add_stroke(path)
        await workspace.connections.broadcast({"type": "human_stroke", "path": path.model_dump()})


async def handle_nudge(workspace: ActiveWorkspace, message: dict[str, Any]) -> None:
    """Handle a nudge suggestion from the user."""
    text = message.get("text", "")
    if text:
        workspace.agent.add_nudge(text)
        # Clear piece_completed flag and wake the orchestrator
        if workspace.orchestrator:
            workspace.orchestrator.clear_piece_completed()
            await workspace.start_agent_loop()
            workspace.orchestrator.wake()
        logger.info(f"User {workspace.user_id} nudge: {text}")


async def handle_clear(workspace: ActiveWorkspace) -> None:
    """Handle canvas clear request."""
    await workspace.state.clear_canvas()
    await workspace.connections.broadcast(ClearMessage())
    logger.info(f"User {workspace.user_id}: canvas cleared")


async def handle_new_canvas(
    workspace: ActiveWorkspace, message: dict[str, Any] | None = None
) -> None:
    """Handle new canvas request (save current and start fresh)."""
    saved_id = await workspace.state.new_canvas()
    workspace.agent.reset_container()

    # If direction provided, add it as an initial nudge for the new piece
    direction = message.get("direction") if message else None
    if direction:
        workspace.agent.add_nudge(direction)
        logger.info(f"User {workspace.user_id}: new canvas with direction: {direction}")

    # If drawing_style provided, persist it so the agent gets the right prompt
    style_str = message.get("drawing_style") if message else None
    if style_str:
        try:
            new_style = DrawingStyleType(style_str)
            workspace.state.canvas.drawing_style = new_style
            await workspace.state.save()
            logger.info(f"User {workspace.user_id}: new canvas with style: {new_style.value}")
        except ValueError:
            logger.warning(f"User {workspace.user_id}: invalid style in new_canvas: {style_str}")

    await workspace.connections.broadcast(NewCanvasMessage(saved_id=saved_id))

    # Send updated gallery
    gallery_entries = await workspace.state.list_gallery()
    await workspace.connections.broadcast(
        {"type": "gallery_update", "canvases": [e.model_dump() for e in gallery_entries]}
    )
    await workspace.connections.broadcast(
        PieceStateMessage(number=workspace.state.piece_number, completed=False)
    )

    # Auto-start the agent on new canvas
    await workspace.agent.resume()
    workspace.state.status = AgentStatus.IDLE
    workspace.state.pause_reason = PauseReason.NONE  # Clear pause reason on new canvas
    await workspace.state.save()
    await workspace.connections.broadcast(PausedMessage(paused=False))
    # Clear piece_completed flag and wake the orchestrator
    if workspace.orchestrator:
        workspace.orchestrator.clear_piece_completed()
        await workspace.start_agent_loop()
        workspace.orchestrator.wake()

    logger.info(
        f"User {workspace.user_id}: new canvas (piece #{workspace.state.piece_number}), saved: {saved_id}, auto-started"
    )


async def handle_load_canvas(workspace: ActiveWorkspace, message: dict[str, Any]) -> None:
    """Handle loading a canvas from gallery."""
    piece_num = message.get("piece_number")

    if piece_num is None or not isinstance(piece_num, int):
        logger.warning(f"User {workspace.user_id}: invalid piece_number: {piece_num}")
        return

    result = await workspace.state.load_from_gallery(piece_num)

    if result:
        strokes, drawing_style = result
        # Read-only: send strokes to client without mutating workspace state
        style_config = get_style_config(drawing_style)
        await workspace.connections.broadcast(
            LoadCanvasMessage(
                strokes=strokes,
                piece_number=piece_num,
                drawing_style=drawing_style,
                style_config=style_config,
            )
        )
        logger.info(
            f"User {workspace.user_id}: loaded canvas piece #{piece_num} (style: {drawing_style.value})"
        )
        return

    logger.warning(f"User {workspace.user_id}: canvas not found: piece #{piece_num}")


async def handle_pause(workspace: ActiveWorkspace) -> None:
    """Handle pause request."""
    await workspace.agent.pause()
    workspace.state.status = AgentStatus.PAUSED
    workspace.state.pause_reason = PauseReason.USER  # User explicitly paused
    await workspace.state.save()
    await workspace.connections.broadcast(PausedMessage(paused=True))
    logger.info(f"User {workspace.user_id}: agent paused")


async def handle_resume(workspace: ActiveWorkspace, message: dict[str, Any] | None = None) -> None:
    """Handle resume request with optional direction."""
    # If direction provided, add it as a nudge before resuming
    direction = message.get("direction") if message else None
    if direction:
        workspace.agent.add_nudge(direction)
        logger.info(f"User {workspace.user_id}: resume with direction: {direction}")

    await workspace.agent.resume()
    workspace.state.status = AgentStatus.IDLE
    workspace.state.pause_reason = PauseReason.NONE  # Clear pause reason on resume
    await workspace.state.save()
    await workspace.connections.broadcast(PausedMessage(paused=False))
    # Wake the orchestrator immediately to start working
    if workspace.orchestrator:
        await workspace.start_agent_loop()
        workspace.orchestrator.wake()
    logger.info(f"User {workspace.user_id}: agent resumed")


async def handle_animation_done(
    workspace: ActiveWorkspace, message: dict[str, Any] | None = None
) -> None:
    """Handle client signaling animation complete."""
    batch_id = message.get("batch_id") if message else None
    if workspace.orchestrator:
        workspace.orchestrator.signal_animation_done(batch_id)
    logger.info(f"User {workspace.user_id}: animation_done received (batch_id={batch_id})")


# Dispatch table
HANDLERS: dict[str, Any] = {
    "stroke": handle_stroke,
    "nudge": handle_nudge,
    "clear": handle_clear,
    "new_canvas": handle_new_canvas,
    "load_canvas": handle_load_canvas,
    "pause": handle_pause,
    "resume": handle_resume,
    "animation_done": handle_animation_done,
}


async def handle_user_message(workspace: ActiveWorkspace, message: dict[str, Any]) -> bool:
    """Route message to handler. Returns True if handled."""
    msg_type = message.get("type")
    handler = HANDLERS.get(msg_type) if msg_type else None

    logger.info(f"[MSG] User {workspace.user_id}: received type={msg_type}")

    if handler:
        # Handlers that need the message get it, others don't
        if msg_type in (
            "stroke",
            "nudge",
            "load_canvas",
            "new_canvas",
            "resume",
            "animation_done",
        ):
            await handler(workspace, message)
        else:
            await handler(workspace)
        logger.info(f"[MSG] User {workspace.user_id}: {msg_type} handled OK")
        return True

    if msg_type:
        logger.warning(f"User {workspace.user_id}: unknown message type: {msg_type}")
    return False
