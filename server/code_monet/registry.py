"""Workspace registry for multi-user isolation."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from code_monet.config import settings
from code_monet.types import AgentStatus, PauseReason
from code_monet.workspace import WorkspaceState

logger = logging.getLogger(__name__)

# Grace period before deactivating idle workspace (seconds)
IDLE_GRACE_PERIOD = 300  # 5 minutes

# Maximum WebSocket connections per user (0 = unlimited)
MAX_CONNECTIONS_PER_USER = settings.max_connections_per_user


class UserConnectionManager:
    """WebSocket connection manager scoped to a single user.

    Each user has their own connection manager that only broadcasts
    to that user's connections.
    """

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.connections: list[WebSocket] = []

    def add(self, websocket: WebSocket) -> bool:
        """Add a WebSocket connection.

        Returns True if connection was added, False if limit reached.
        """
        if MAX_CONNECTIONS_PER_USER > 0 and len(self.connections) >= MAX_CONNECTIONS_PER_USER:
            client = getattr(websocket, "client", None)
            client_info = f"{client.host}:{client.port}" if client else "unknown"
            logger.error(
                f"User {self.user_id}: connection limit reached "
                f"({MAX_CONNECTIONS_PER_USER}), rejecting connection from {client_info}"
            )
            return False
        self.connections.append(websocket)
        logger.info(f"User {self.user_id}: connection added. Total: {len(self.connections)}")
        return True

    def remove(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.connections:
            self.connections.remove(websocket)
        logger.info(f"User {self.user_id}: connection removed. Total: {len(self.connections)}")

    @property
    def connection_count(self) -> int:
        return len(self.connections)

    @property
    def is_empty(self) -> bool:
        return len(self.connections) == 0

    @property
    def active_connections(self) -> list[WebSocket]:
        """Alias for connections - required by Broadcaster protocol."""
        return self.connections

    async def broadcast(self, message: Any) -> None:
        """Broadcast message to all user's connections."""
        if not self.connections:
            return

        # Log important message types
        msg_type = message.type if hasattr(message, "type") else "unknown"
        if msg_type == "human_stroke":
            logger.info(f"User {self.user_id}: >>> human_stroke")
        elif msg_type == "agent_strokes_ready":
            count = message.count if hasattr(message, "count") else "?"
            batch_id = message.batch_id if hasattr(message, "batch_id") else "?"
            logger.info(
                f"User {self.user_id}: >>> agent_strokes_ready count={count} batch={batch_id}"
            )
        elif msg_type == "status":
            status = message.status if hasattr(message, "status") else "?"
            logger.info(f"User {self.user_id}: >>> status={status}")

        if hasattr(message, "model_dump_json"):
            data = message.model_dump_json()
        else:
            data = json.dumps(message)

        failed: list[WebSocket] = []
        for conn in self.connections:
            try:
                await conn.send_text(data)
            except Exception as e:
                logger.error(f"User {self.user_id} broadcast error: {e}")
                failed.append(conn)

        for conn in failed:
            self.remove(conn)

    async def send_to(self, websocket: WebSocket, message: Any) -> None:
        """Send message to a specific connection."""
        if hasattr(message, "model_dump_json"):
            data = message.model_dump_json()
        else:
            data = json.dumps(message)
        await websocket.send_text(data)


@dataclass
class ActiveWorkspace:
    """Bundle of components for an active user workspace.

    Created when a user connects, destroyed after idle timeout.
    """

    user_id: str
    state: WorkspaceState
    connections: UserConnectionManager
    agent: Any = None  # DrawingAgent - set after creation to avoid circular import
    orchestrator: Any = None  # AgentOrchestrator - set after creation
    loop_task: asyncio.Task[None] | None = None
    _idle_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _loop_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def start_agent_loop(self) -> None:
        """Start (or restart) the agent orchestrator loop.

        Thread-safe: uses internal lock to prevent race conditions when
        multiple clients connect simultaneously.
        """
        if not self.orchestrator:
            return

        async with self._loop_lock:
            if self.loop_task and not self.loop_task.done():
                return

            if self.loop_task and self.loop_task.done():
                if self.loop_task.cancelled():
                    logger.info(f"User {self.user_id}: agent loop cancelled, restarting")
                else:
                    exc = self.loop_task.exception()
                    if exc:
                        logger.warning(
                            f"User {self.user_id}: agent loop exited with error, restarting: {exc}"
                        )
                self.loop_task = None

            self.loop_task = asyncio.create_task(self.orchestrator.run_loop())
            logger.info(f"User {self.user_id}: agent loop started")

    async def stop_agent_loop(self) -> None:
        """Stop the agent orchestrator loop."""
        import contextlib

        if self.loop_task and not self.loop_task.done():
            self.loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.loop_task
            self.loop_task = None
            logger.info(f"User {self.user_id}: agent loop stopped")


class WorkspaceRegistry:
    """Manages active workspaces for all users.

    Handles:
    - Lazy activation when user connects
    - Deactivation after idle timeout
    - Workspace lookup by user ID
    """

    def __init__(self) -> None:
        self._workspaces: dict[str, ActiveWorkspace] = {}
        self._lock = asyncio.Lock()
        self._loading: set[str] = set()  # Users currently being loaded

    async def get_or_activate(self, user_id: str) -> ActiveWorkspace:
        """Get existing workspace or activate a new one.

        Uses double-check pattern to avoid holding lock during I/O.
        """
        # Fast path: check if already exists (no lock needed for read)
        if user_id in self._workspaces:
            ws: ActiveWorkspace | None = None
            # Cancel any pending deactivation
            async with self._lock:
                ws = self._workspaces.get(user_id)
                if ws and ws._idle_task and not ws._idle_task.done():
                    ws._idle_task.cancel()
                    ws._idle_task = None
            if ws:
                await ws.start_agent_loop()
                return ws

        # Slow path: need to activate
        ws = None
        should_activate = False
        async with self._lock:
            # Double-check after acquiring lock
            if user_id in self._workspaces:
                ws = self._workspaces[user_id]
                if ws._idle_task and not ws._idle_task.done():
                    ws._idle_task.cancel()
                    ws._idle_task = None

            # Check if another task is already loading this workspace
            elif user_id not in self._loading:
                # Mark as loading and release lock during I/O
                self._loading.add(user_id)
                should_activate = True

        if ws:
            await ws.start_agent_loop()
            return ws

        # If we marked it as loading, do the activation outside the lock
        if should_activate:
            try:
                workspace = await self._activate_workspace(user_id)
                async with self._lock:
                    self._workspaces[user_id] = workspace
                    self._loading.discard(user_id)
                return workspace
            except Exception:
                async with self._lock:
                    self._loading.discard(user_id)
                raise

        # Another task was loading - wait and retry
        while user_id in self._loading:
            await asyncio.sleep(0.05)

        # Should now be available
        async with self._lock:
            ws = self._workspaces.get(user_id)
        if ws:
            await ws.start_agent_loop()
            return ws

        # Fallback: load ourselves (shouldn't normally reach here)
        return await self.get_or_activate(user_id)

    async def _activate_workspace(self, user_id: str) -> ActiveWorkspace:
        """Create and initialize a new active workspace."""
        # Lazy imports to avoid circular dependencies
        from code_monet.agent import DrawingAgent
        from code_monet.agent.openai_agent import OpenAIDrawingAgent
        from code_monet.agent_logger import AgentFileLogger
        from code_monet.config import settings
        from code_monet.orchestrator import AgentOrchestrator

        logger.info(f"Activating workspace for user {user_id}")

        # Load state from database
        state = await WorkspaceState.load_for_user(user_id)

        # Create per-user file logger for agent activity
        file_logger: AgentFileLogger | None = None
        if settings.agent_logs_enabled:
            file_logger = AgentFileLogger(
                user_dir=state._user_dir,
                max_log_files=settings.agent_logs_max_files,
            )
            logger.info(f"User {user_id}: agent file logging enabled")

        # Create per-user components
        connections = UserConnectionManager(user_id)
        provider = settings.agent_provider.lower()
        agent: Any
        if provider == "openai":
            agent = OpenAIDrawingAgent(state)
        elif provider == "anthropic":
            agent = DrawingAgent(state)
        else:
            raise ValueError(f"Unsupported AGENT_PROVIDER: {settings.agent_provider}")
        logger.info(f"User {user_id}: agent provider={provider}")
        orchestrator = AgentOrchestrator(
            agent=agent,
            broadcaster=connections,
            file_logger=file_logger,
        )

        workspace = ActiveWorkspace(
            user_id=user_id,
            state=state,
            connections=connections,
            agent=agent,
            orchestrator=orchestrator,
        )

        # Start agent loop
        await workspace.start_agent_loop()

        return workspace

    async def on_disconnect(self, user_id: str, websocket: WebSocket) -> None:
        """Handle user disconnect - pause agent and schedule deactivation if no connections remain."""
        async with self._lock:
            if user_id not in self._workspaces:
                return

            ws = self._workspaces[user_id]
            ws.connections.remove(websocket)

            if ws.connections.is_empty:
                # Pause the agent if not already paused by user
                # This prevents wasted API calls while no one is watching
                if ws.agent and not ws.agent.paused:
                    await ws.agent.pause()
                    ws.state.status = AgentStatus.PAUSED
                    ws.state.pause_reason = PauseReason.DISCONNECT
                    await ws.state.save()
                    logger.info(f"User {user_id}: agent paused (no clients connected)")

                # Schedule deactivation after grace period
                ws._idle_task = asyncio.create_task(
                    self._deactivate_after_delay(user_id, IDLE_GRACE_PERIOD)
                )

    async def _deactivate_after_delay(self, user_id: str, delay: float) -> None:
        """Deactivate workspace after delay if still idle."""
        await asyncio.sleep(delay)

        async with self._lock:
            if user_id not in self._workspaces:
                return

            ws = self._workspaces[user_id]

            # Only deactivate if still no connections
            if ws.connections.is_empty:
                await self._deactivate_workspace(user_id)

    async def _deactivate_workspace(self, user_id: str) -> None:
        """Deactivate and remove a workspace."""
        if user_id not in self._workspaces:
            return

        ws = self._workspaces[user_id]
        logger.info(f"Deactivating workspace for user {user_id}")

        # Stop agent loop
        await ws.stop_agent_loop()

        # Save state one final time
        await ws.state.save()

        # Remove from registry
        del self._workspaces[user_id]

    async def shutdown_all(self) -> None:
        """Shutdown all active workspaces (for server shutdown)."""
        async with self._lock:
            user_ids = list(self._workspaces.keys())

        for user_id in user_ids:
            await self._deactivate_workspace(user_id)

        logger.info("All workspaces deactivated")

    def get(self, user_id: str) -> ActiveWorkspace | None:
        """Get workspace by user ID without activating."""
        return self._workspaces.get(user_id)

    @property
    def active_count(self) -> int:
        """Number of active workspaces."""
        return len(self._workspaces)


# Global registry instance
workspace_registry = WorkspaceRegistry()
