"""Sleep-on-idle: only real client activity keeps the server awake."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from code_monet.idle import ActivityMiddleware, IdleTracker, exit_when_idle


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TestIdleTracker:
    def test_idle_time_counts_from_last_activity(self) -> None:
        clock = FakeClock()
        tracker = IdleTracker(clock)
        clock.now += 30
        assert tracker.idle_seconds() == 30

        tracker.begin()
        clock.now += 600
        assert tracker.idle_seconds() == 0, "an open request or socket is never idle"

        tracker.end()
        assert tracker.idle_seconds() == 0
        clock.now += 45
        assert tracker.idle_seconds() == 45

    def test_overlapping_activity_stays_busy_until_the_last_ends(self) -> None:
        clock = FakeClock()
        tracker = IdleTracker(clock)
        tracker.begin()
        tracker.begin()
        tracker.end()
        clock.now += 100
        assert tracker.open_count == 1
        assert tracker.idle_seconds() == 0
        tracker.end()
        clock.now += 5
        assert tracker.idle_seconds() == 5


def _app(tracker: IdleTracker) -> tuple[FastAPI, list[int]]:
    app = FastAPI()
    seen: list[int] = []

    @app.get("/health")
    async def health() -> dict[str, str]:
        seen.append(tracker.open_count)
        return {"status": "ok"}

    @app.get("/version")
    async def version() -> dict[str, str]:
        seen.append(tracker.open_count)
        return {"version": "test"}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        seen.append(tracker.open_count)
        await websocket.receive_text()
        seen.append(tracker.open_count)
        await websocket.close()

    app.add_middleware(ActivityMiddleware, tracker=tracker)
    return app, seen


class TestActivityMiddleware:
    def test_health_checks_are_not_activity(self) -> None:
        clock = FakeClock()
        tracker = IdleTracker(clock)
        app, seen = _app(tracker)
        clock.now += 300
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
        assert seen == [0]
        assert tracker.idle_seconds() == 300, "/health must not reset the idle clock"

    def test_requests_are_activity(self) -> None:
        clock = FakeClock()
        tracker = IdleTracker(clock)
        app, seen = _app(tracker)
        clock.now += 300
        with TestClient(app) as client:
            assert client.get("/version").status_code == 200
        assert seen == [1]
        assert tracker.idle_seconds() == 0

    def test_websocket_holds_the_server_awake_until_it_closes(self) -> None:
        tracker = IdleTracker(FakeClock())
        app, seen = _app(tracker)
        with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
            websocket.send_text("hello")
        assert seen == [1, 1]
        assert tracker.open_count == 0

    @pytest.mark.asyncio
    async def test_lifespan_scope_passes_through(self) -> None:
        tracker = IdleTracker(FakeClock())
        calls: list[str] = []

        async def inner(scope: Any, _receive: Any, _send: Any) -> None:
            calls.append(scope["type"])

        async def receive() -> dict[str, Any]:
            return {}

        async def send(_message: Any) -> None:
            return None

        await ActivityMiddleware(inner, tracker)({"type": "lifespan"}, receive, send)
        assert calls == ["lifespan"]
        assert tracker.open_count == 0


class TestExitWhenIdle:
    @pytest.mark.asyncio
    async def test_requests_exit_once_idle_long_enough(self) -> None:
        clock = FakeClock()
        tracker = IdleTracker(clock)
        exits: list[float] = []

        async def advance(seconds: float) -> None:
            clock.now += seconds

        await exit_when_idle(
            tracker, 900, lambda: exits.append(clock.now), poll_seconds=60, sleep=advance
        )
        assert exits == [1900.0]

    @pytest.mark.asyncio
    async def test_activity_postpones_exit(self) -> None:
        clock = FakeClock()
        tracker = IdleTracker(clock)
        exits: list[float] = []
        polls = 0

        async def advance(seconds: float) -> None:
            nonlocal polls
            polls += 1
            clock.now += seconds
            if polls == 10:  # a client arrives and leaves at t=1600
                tracker.begin()
                tracker.end()

        await exit_when_idle(
            tracker, 900, lambda: exits.append(clock.now), poll_seconds=60, sleep=advance
        )
        assert exits == [1600.0 + 900]

    @pytest.mark.asyncio
    async def test_default_poll_is_bounded(self) -> None:
        tracker = IdleTracker(FakeClock())
        sleeps: list[float] = []

        async def record(seconds: float) -> None:
            sleeps.append(seconds)
            tracker._last_activity -= 10_000  # noqa: SLF001 - force idleness

        await exit_when_idle(tracker, 3600, lambda: None, sleep=record)
        await exit_when_idle(tracker, 2, lambda: None, sleep=record)
        assert sleeps == [30.0, 1.0]

    @pytest.mark.asyncio
    async def test_cancellation_stops_the_watcher(self) -> None:
        tracker = IdleTracker()
        task = asyncio.create_task(exit_when_idle(tracker, 900, lambda: None, poll_seconds=10))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
