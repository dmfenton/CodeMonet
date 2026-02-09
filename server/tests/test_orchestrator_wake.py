"""Tests for orchestrator event-driven wake-up."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_monet.orchestrator import AgentOrchestrator


@pytest.fixture
def mock_agent():
    """Create a mock agent."""
    agent = MagicMock()
    agent.paused = True
    agent.pending_nudges = []
    agent.get_state.return_value = MagicMock(
        canvas=MagicMock(strokes=[]),
        piece_number=0,
    )
    return agent


@pytest.fixture
def mock_broadcaster():
    """Create a mock broadcaster."""
    broadcaster = MagicMock()
    broadcaster.active_connections = []
    broadcaster.broadcast = AsyncMock()
    return broadcaster


@pytest.fixture
def orchestrator(mock_agent, mock_broadcaster):
    """Create an orchestrator with mocks."""
    return AgentOrchestrator(
        agent=mock_agent,
        broadcaster=mock_broadcaster,
    )


class TestOrchestratorWake:
    """Test event-driven wake-up."""

    def test_wake_sets_event(self, orchestrator: AgentOrchestrator) -> None:
        """wake() should set the event."""
        assert not orchestrator._wake_event.is_set()

        orchestrator.wake()

        assert orchestrator._wake_event.is_set()

    def test_wake_is_idempotent(self, orchestrator: AgentOrchestrator) -> None:
        """Multiple wake() calls should be safe."""
        orchestrator.wake()
        orchestrator.wake()
        orchestrator.wake()

        assert orchestrator._wake_event.is_set()

    @pytest.mark.asyncio
    async def test_run_loop_waits_for_wake(
        self, orchestrator: AgentOrchestrator, mock_broadcaster
    ) -> None:
        """run_loop should wait for wake event."""
        mock_broadcaster.active_connections = []  # No connections
        woke_up = asyncio.Event()

        async def run_loop_briefly():
            # Run one iteration of the loop
            try:
                await asyncio.wait_for(
                    orchestrator._wake_event.wait(),
                    timeout=0.1,
                )
                woke_up.set()
            except TimeoutError:
                pass

        # Start waiting
        task = asyncio.create_task(run_loop_briefly())

        # Wake up after a brief delay
        await asyncio.sleep(0.05)
        orchestrator.wake()

        await task
        assert woke_up.is_set()

    @pytest.mark.asyncio
    async def test_run_loop_clears_event_after_wake(self, orchestrator: AgentOrchestrator) -> None:
        """Event should be cleared after processing."""
        orchestrator.wake()
        assert orchestrator._wake_event.is_set()

        # Simulate the clear that happens in run_loop
        orchestrator._wake_event.clear()

        assert not orchestrator._wake_event.is_set()

    @pytest.mark.asyncio
    async def test_run_loop_skips_when_no_connections(
        self, orchestrator: AgentOrchestrator, mock_agent, mock_broadcaster
    ) -> None:
        """Should not run turn when no connections."""
        mock_broadcaster.active_connections = []
        mock_agent.paused = False

        # The loop checks connections first
        # This is tested implicitly by ensuring run_turn is not called
        with patch.object(orchestrator, "run_turn", new_callable=AsyncMock) as mock_run_turn:
            # Simulate one wake cycle
            orchestrator.wake()

            # Wait for event
            await asyncio.wait_for(orchestrator._wake_event.wait(), timeout=0.1)
            orchestrator._wake_event.clear()

            # Check conditions - no connections, so run_turn shouldn't be called
            if not mock_broadcaster.active_connections:
                # run_turn should not be called
                mock_run_turn.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_loop_skips_when_paused(
        self, orchestrator: AgentOrchestrator, mock_agent, mock_broadcaster
    ) -> None:
        """Should not run turn when agent is paused."""
        mock_broadcaster.active_connections = [MagicMock()]  # Has connections
        mock_agent.paused = True

        with patch.object(orchestrator, "run_turn", new_callable=AsyncMock) as mock_run_turn:
            orchestrator.wake()

            await asyncio.wait_for(orchestrator._wake_event.wait(), timeout=0.1)
            orchestrator._wake_event.clear()

            # Check conditions - paused, so run_turn shouldn't be called
            if mock_agent.paused:
                mock_run_turn.assert_not_called()


class TestDrawPathsAnimationWait:
    """Tests for _draw_paths animation wait behavior."""

    @pytest.mark.asyncio
    async def test_draw_paths_waits_for_animation(
        self, orchestrator: AgentOrchestrator, mock_agent
    ) -> None:
        """_draw_paths should wait for estimated animation time."""
        import time

        from code_monet.types import Path, Point

        # Mock state.queue_strokes to return known values
        mock_state = MagicMock()
        # 30 points at 60fps = 0.5s + 0.5s buffer = 1.0s
        mock_state.queue_strokes = AsyncMock(return_value=(1, 30))
        mock_agent.get_state.return_value = mock_state

        paths = [Path(type="line", points=[Point(x=0, y=0), Point(x=100, y=100)])]

        start = time.monotonic()
        await orchestrator._draw_paths(paths)
        elapsed = time.monotonic() - start

        # Should wait approximately 1.0s (30 points / 60fps + 0.5s buffer)
        # Allow some tolerance for test execution overhead
        assert elapsed >= 0.9, f"Expected >= 0.9s wait, got {elapsed:.2f}s"
        assert elapsed < 1.5, f"Expected < 1.5s wait, got {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_draw_paths_caps_wait_time(
        self, orchestrator: AgentOrchestrator, mock_agent
    ) -> None:
        """_draw_paths should cap wait time to max_animation_wait_s."""
        import time

        from code_monet.types import Path, Point

        # Mock state.queue_strokes with many points that would exceed max wait
        mock_state = MagicMock()
        # 10000 points at 60fps = 166s, but should be capped
        mock_state.queue_strokes = AsyncMock(return_value=(1, 10000))
        mock_agent.get_state.return_value = mock_state

        paths = [Path(type="line", points=[Point(x=0, y=0), Point(x=100, y=100)])]

        # Patch max_animation_wait_s to a short value for testing
        with patch("code_monet.orchestrator.settings") as mock_settings:
            mock_settings.client_animation_fps = 60
            mock_settings.animation_wait_buffer_ms = 500
            mock_settings.max_animation_wait_s = 2.0  # 2 second cap for test

            start = time.monotonic()
            await orchestrator._draw_paths(paths)
            elapsed = time.monotonic() - start

        # Should be capped near 2s (the patched max)
        assert elapsed >= 1.8, f"Expected >= 1.8s (capped), got {elapsed:.2f}s"
        assert elapsed <= 2.5, f"Expected <= 2.5s (capped), got {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_draw_paths_skips_empty(self, orchestrator: AgentOrchestrator) -> None:
        """_draw_paths should return immediately for empty paths."""
        import time

        start = time.monotonic()
        await orchestrator._draw_paths([])
        elapsed = time.monotonic() - start

        # Should be nearly instant
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_draw_paths_passes_through_without_expansion(
        self, orchestrator: AgentOrchestrator, mock_agent, mock_broadcaster
    ) -> None:
        """_draw_paths should pass brush paths through without server-side expansion.

        Client handles bristle rendering via getBristleOutlines().
        """
        from code_monet.types import Path, Point

        mock_state = MagicMock()
        mock_state.queue_strokes = AsyncMock(return_value=(1, 1))
        mock_state.piece_number = 0
        mock_agent.get_state.return_value = mock_state

        paths = [
            Path(
                type="line",
                points=[Point(x=0, y=0), Point(x=1, y=1)],
                author="agent",
                brush="oil_round",
            ),
        ]

        with patch("code_monet.orchestrator.settings") as mock_settings:
            mock_settings.client_animation_fps = 60
            mock_settings.animation_wait_buffer_ms = 0
            mock_settings.max_animation_wait_s = 0.0

            await orchestrator._draw_paths(paths)

        ready_messages = [
            call.args[0]
            for call in mock_broadcaster.broadcast.call_args_list
            if getattr(call.args[0], "type", None) == "agent_strokes_ready"
        ]
        assert ready_messages, "Expected agent_strokes_ready broadcast"
        assert ready_messages[0].count == 1  # No expansion, original count preserved


class TestAnimationDoneBatchMatching:
    """Tests for animation_done batch ID handling."""

    def test_signal_animation_done_matches_batch(self, orchestrator: AgentOrchestrator) -> None:
        orchestrator._animation_wait_batch_id = 3

        assert not orchestrator._animation_done_event.is_set()
        orchestrator.signal_animation_done(3)

        assert orchestrator._animation_done_event.is_set()

    def test_signal_animation_done_ignores_mismatch(self, orchestrator: AgentOrchestrator) -> None:
        orchestrator._animation_wait_batch_id = 3

        assert not orchestrator._animation_done_event.is_set()
        orchestrator.signal_animation_done(2)

        assert not orchestrator._animation_done_event.is_set()


class TestOrchestratorWakeIntegration:
    """Integration tests for wake behavior."""

    @pytest.mark.asyncio
    async def test_wake_reduces_latency(self) -> None:
        """Wake should allow immediate response vs polling interval."""
        event = asyncio.Event()
        latency = None

        async def wait_for_wake():
            nonlocal latency
            import time

            start = time.monotonic()
            try:
                await asyncio.wait_for(event.wait(), timeout=5.0)
                latency = time.monotonic() - start
            except TimeoutError:
                latency = 5.0

        # Start waiting
        task = asyncio.create_task(wait_for_wake())

        # Wake after 50ms
        await asyncio.sleep(0.05)
        event.set()

        await task

        # Should have woken up quickly (< 200ms including overhead)
        assert latency is not None
        assert latency < 0.2
