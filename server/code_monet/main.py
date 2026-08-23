"""FastAPI application with WebSocket support."""

import asyncio
import json
import logging
import traceback
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from code_monet.anthropic_wif import anthropic_wif_configuration
from code_monet.auth import auth_router
from code_monet.auth.jwt import TokenError, get_user_id_from_token
from code_monet.config import settings
from code_monet.db import get_session, repository
from code_monet.logging_config import setup_dev_logging, setup_production_logging
from code_monet.registry import workspace_registry
from code_monet.routes import create_api_router
from code_monet.share import share_router
from code_monet.shutdown import shutdown_manager
from code_monet.tracing import get_current_trace_id, setup_tracing
from code_monet.types import AgentStatus, PausedMessage, PauseReason
from code_monet.user_handlers import handle_user_message

# Configure logging based on environment
if settings.dev_mode:
    setup_dev_logging()
else:
    setup_production_logging()

logger = logging.getLogger(__name__)


async def shutdown_all_workspaces() -> None:
    """Callback to shutdown all active workspaces during shutdown."""
    try:
        await workspace_registry.shutdown_all()
        logger.info("All workspaces shutdown successfully")
    except Exception as e:
        logger.error(f"Failed to shutdown workspaces: {e}")


async def run_migrations() -> None:
    """Run database migrations on startup."""
    from alembic.config import Config

    from alembic import command

    # Run alembic upgrade head
    alembic_cfg = Config("alembic.ini")
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    logger.info("Database migrations completed")


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    """Application lifespan handler with graceful shutdown."""
    logger.info("=== Server startup initiated ===")

    # Validate required settings
    if settings.dev_mode and not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET environment variable must be set")
    if settings.dev_mode and len(settings.jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters")
    if not settings.dev_mode:
        anthropic_wif = anthropic_wif_configuration()
        if anthropic_wif is None or not anthropic_wif.identity_token_available():
            raise RuntimeError("Anthropic workload identity token is unavailable")

    # Run database migrations
    await run_migrations()

    # Register cleanup callback with shutdown manager
    shutdown_manager.add_cleanup_callback(shutdown_all_workspaces)

    # Install signal handlers only in production mode
    # In dev mode, uvicorn's reloader handles signals for hot reload
    if not settings.dev_mode:
        shutdown_manager.install_signal_handlers()
    else:
        logger.info("Dev mode: skipping custom signal handlers (uvicorn handles reload)")

    logger.info("=== Server startup completed (multi-user mode) ===")

    yield

    # Shutdown - delegate to shutdown manager
    logger.info("Lifespan shutdown triggered")
    await shutdown_manager.shutdown()


app = FastAPI(
    title="Code Monet",
    description="Autonomous AI artist",
    version="0.1.0",
    lifespan=lifespan,
)

# Initialize OpenTelemetry tracing
setup_tracing(app)

# CORS configuration
# Since we use JWT tokens (not cookies), we don't need allow_credentials=True
# This allows native apps and any web origin to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add auth routes
app.include_router(auth_router)

# Add share routes (public + authenticated)
app.include_router(share_router)

# Add all API routes from the routes package
app.include_router(create_api_router())


# Global exception handler to log all unhandled errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch all unhandled exceptions and log them with full traceback."""
    trace_id = get_current_trace_id()
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}\n"
        f"trace_id={trace_id}\n"
        f"{''.join(tb)}"
    )
    content: dict[str, Any] = {"detail": "Internal Server Error"}
    if trace_id:
        content["trace_id"] = trace_id
    return JSONResponse(status_code=500, content=content)


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
) -> None:
    """WebSocket endpoint with JWT authentication and per-user routing.

    Connect with: ws://host/ws?token=<jwt_access_token>&trace_id=<client_trace_id>

    Each authenticated user gets their own workspace with:
    - Isolated canvas state
    - Personal agent instance
    - Private gallery

    The optional trace_id parameter allows distributed tracing correlation
    with mobile client spans.
    """
    logger.info(f"[WS] New connection attempt, token={'present' if token else 'missing'}")
    # Must accept before any operations per ASGI spec
    await websocket.accept()
    logger.info("[WS] Connection accepted")

    # Reject during shutdown
    if shutdown_manager.is_shutting_down:
        await websocket.close(code=1001, reason="Server shutting down")
        return

    # Validate token
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    try:
        user_id = get_user_id_from_token(token, expected_type="access")
    except TokenError as e:
        await websocket.close(code=4001, reason=str(e))
        return
    except Exception as e:
        logger.warning(f"WebSocket auth failed with unexpected error: {e}")
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Verify user exists and is active
    async with get_session() as session:
        user = await repository.get_user_by_id(session, user_id)

    if user is None or not user.is_active:
        await websocket.close(code=4001, reason="User not found or inactive")
        return

    logger.info(f"WebSocket authenticated: user {user.email} (id={user_id})")

    # Record client trace ID for distributed tracing correlation
    if trace_id:
        from opentelemetry import trace as otel_trace

        current_span = otel_trace.get_current_span()
        if current_span.is_recording():
            current_span.set_attribute("client.trace_id", trace_id)
            current_span.set_attribute("client.source", "mobile")
        logger.debug(f"Client trace_id: {trace_id}")

    # Get or create user's workspace
    workspace = await workspace_registry.get_or_activate(user_id)
    if not workspace.connections.add(websocket):
        await websocket.close(code=4003, reason="Too many connections")
        return
    await shutdown_manager.register_connection(websocket)

    try:
        # Send current state to new client
        gallery_entries = await workspace.state.list_gallery()
        gallery_data = [entry.model_dump() for entry in gallery_entries]

        # Get the current drawing style config
        from code_monet.types import get_style_config

        drawing_style = workspace.state.canvas.drawing_style
        style_config = get_style_config(drawing_style)

        await workspace.connections.send_to(
            websocket,
            {
                "type": "init",
                "strokes": [s.model_dump() for s in workspace.state.canvas.strokes],
                "gallery": gallery_data,
                "status": workspace.state.status.value,
                "paused": workspace.agent.paused,
                "piece_number": workspace.state.piece_number,
                "canvas_width": workspace.state.canvas.width,
                "canvas_height": workspace.state.canvas.height,
                "monologue": workspace.state.monologue or "",
                "drawing_style": drawing_style.value,
                "style_config": style_config.model_dump(),
            },
        )
        logger.info(
            f"User {user_id}: sent init with {len(workspace.state.canvas.strokes)} strokes, "
            f"{len(gallery_data)} gallery, piece #{workspace.state.piece_number}"
        )

        # Auto-resume if agent was paused due to disconnect (not user action)
        if workspace.agent.paused and workspace.state.pause_reason == PauseReason.DISCONNECT:
            await workspace.agent.resume()
            workspace.state.status = AgentStatus.IDLE
            workspace.state.pause_reason = PauseReason.NONE
            await workspace.state.save()
            await workspace.connections.broadcast(PausedMessage(paused=False))
            # Wake the orchestrator to continue working
            if workspace.orchestrator:
                await workspace.start_agent_loop()
                workspace.orchestrator.wake()
            logger.info(f"User {user_id}: agent auto-resumed (client reconnected)")

        # Notify if there are pending strokes to fetch (reconnection scenario)
        # Only send if not paused - paused canvases shouldn't trigger animation
        if workspace.state.has_pending_strokes and not workspace.agent.paused:
            await workspace.connections.send_to(
                websocket,
                {
                    "type": "agent_strokes_ready",
                    "count": workspace.state.pending_stroke_count,
                    "batch_id": workspace.state.stroke_batch_id,
                    "piece_number": workspace.state.piece_number,
                },
            )
            logger.info(
                f"User {user_id}: notified of {workspace.state.pending_stroke_count} pending strokes"
            )

        while True:
            # Check shutdown between receives
            if shutdown_manager.is_shutting_down:
                break

            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON from user {user_id}: {e}")
                await workspace.connections.send_to(
                    websocket,
                    {"type": "error", "message": "Invalid JSON format"},
                )
                continue

            try:
                await handle_user_message(workspace, message)
            except Exception as e:
                logger.exception(f"Handler error for user {user_id}")
                await workspace.connections.send_to(
                    websocket,
                    {"type": "error", "message": f"Error processing message: {e}"},
                )

    except WebSocketDisconnect:
        await workspace_registry.on_disconnect(user_id, websocket)
        await shutdown_manager.unregister_connection(websocket)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        await workspace_registry.on_disconnect(user_id, websocket)
        await shutdown_manager.unregister_connection(websocket)


if __name__ == "__main__":
    uvicorn.run(
        "code_monet.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        reload_excludes=["logs/*"],
    )
