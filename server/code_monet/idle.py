"""Idle tracking for sleep-on-idle.

The server owns no work without a client: workspaces start on WebSocket connect
and pause on disconnect. So once no request or WebSocket has been open for the
configured time, the production entrypoint stops the server cleanly (exit 0)
and the host's waker starts the container again on the next request.

Health checks are not activity: the container healthcheck, deploy gates and
probes must never keep the server awake.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

logger = logging.getLogger(__name__)

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

HEALTH_PATHS = frozenset({"/health"})


class IdleTracker:
    """Counts open requests/WebSockets and when activity last changed."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._open = 0
        self._last_activity = clock()

    def begin(self) -> None:
        self._open += 1
        self._last_activity = self._clock()

    def end(self) -> None:
        self._open -= 1
        self._last_activity = self._clock()

    @property
    def open_count(self) -> int:
        return self._open

    def idle_seconds(self) -> float:
        """Seconds since the last activity, or 0 while anything is open."""
        if self._open > 0:
            return 0.0
        return self._clock() - self._last_activity


class ActivityMiddleware:
    """ASGI middleware: every HTTP request and WebSocket except health is activity.

    A WebSocket stays open for the whole application call, so it holds the
    server awake until it closes.
    """

    def __init__(self, app: ASGIApp, tracker: IdleTracker) -> None:
        self.app = app
        self.tracker = tracker

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or scope.get("path") in HEALTH_PATHS:
            await self.app(scope, receive, send)
            return
        self.tracker.begin()
        try:
            await self.app(scope, receive, send)
        finally:
            self.tracker.end()


async def exit_when_idle(
    tracker: IdleTracker,
    timeout_seconds: float,
    request_exit: Callable[[], None],
    *,
    poll_seconds: float | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Call request_exit once the tracker has been idle for timeout_seconds."""
    poll = poll_seconds if poll_seconds is not None else min(30.0, max(timeout_seconds / 4, 1.0))
    while True:
        await sleep(poll)
        idle = tracker.idle_seconds()
        if idle >= timeout_seconds:
            logger.info(f"No client activity for {idle:.0f}s; stopping until the next request")
            request_exit()
            return


idle_tracker = IdleTracker()
