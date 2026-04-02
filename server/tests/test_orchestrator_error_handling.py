"""Tests for orchestrator error handling in run_loop."""

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_monet.orchestrator import AgentOrchestrator
from code_monet.types import AgentStatus, PauseReason


@pytest.fixture
def mock_agent():
    """Create a mock agent."""
    agent = MagicMock()
    agent.paused = False
    agent.pending_nudges = []
    agent.pause = AsyncMock()
    mock_state = MagicMock()
    mock_state.save = AsyncMock()
    agent.get_state.return_value = mock_state
    return agent


@pytest.fixture
def mock_broadcaster():
    """Create a mock broadcaster with an active connection."""
    broadcaster = MagicMock()
    broadcaster.active_connections = [MagicMock()]
    broadcaster.broadcast = AsyncMock()
    return broadcaster


@pytest.fixture
def orchestrator(mock_agent, mock_broadcaster):
    """Create an orchestrator with mocks."""
    return AgentOrchestrator(
        agent=mock_agent,
        broadcaster=mock_broadcaster,
    )


async def _run_one_loop_iteration(orchestrator: AgentOrchestrator) -> None:
    """Wake the orchestrator, run one iteration, then cancel."""
    orchestrator.wake()
    task = asyncio.create_task(orchestrator.run_loop())
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


class TestUnrecoverableErrorPause:
    """Test that unrecoverable errors auto-pause the agent."""

    @pytest.mark.asyncio
    async def test_credit_balance_error_pauses_agent(
        self, orchestrator: AgentOrchestrator, mock_agent
    ) -> None:
        """Credit balance errors should auto-pause the agent."""
        with patch.object(
            orchestrator,
            "run_turn",
            new_callable=AsyncMock,
            side_effect=Exception("Credit balance is too low"),
        ):
            await _run_one_loop_iteration(orchestrator)

        mock_agent.pause.assert_awaited_once()
        state = mock_agent.get_state()
        assert state.status == AgentStatus.PAUSED
        assert state.pause_reason == PauseReason.ERROR
        state.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_authentication_error_pauses_agent(
        self, orchestrator: AgentOrchestrator, mock_agent
    ) -> None:
        """Authentication errors should auto-pause the agent."""
        with patch.object(
            orchestrator,
            "run_turn",
            new_callable=AsyncMock,
            side_effect=Exception("Authentication failed"),
        ):
            await _run_one_loop_iteration(orchestrator)

        mock_agent.pause.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_api_key_pauses_agent(
        self, orchestrator: AgentOrchestrator, mock_agent
    ) -> None:
        """Invalid API key errors should auto-pause the agent."""
        with patch.object(
            orchestrator,
            "run_turn",
            new_callable=AsyncMock,
            side_effect=Exception("Invalid API key provided"),
        ):
            await _run_one_loop_iteration(orchestrator)

        mock_agent.pause.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_quota_error_pauses_agent(
        self, orchestrator: AgentOrchestrator, mock_agent
    ) -> None:
        """Quota errors should auto-pause the agent."""
        with patch.object(
            orchestrator,
            "run_turn",
            new_callable=AsyncMock,
            side_effect=Exception("insufficient_quota"),
        ):
            await _run_one_loop_iteration(orchestrator)

        mock_agent.pause.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unrecoverable_error_broadcasts_paused(
        self, orchestrator: AgentOrchestrator, mock_broadcaster
    ) -> None:
        """Unrecoverable errors should broadcast paused=True to clients."""
        with patch.object(
            orchestrator,
            "run_turn",
            new_callable=AsyncMock,
            side_effect=Exception("Credit balance is too low"),
        ):
            await _run_one_loop_iteration(orchestrator)

        broadcast_calls = mock_broadcaster.broadcast.call_args_list
        messages = [call.args[0] for call in broadcast_calls]
        paused_messages = [m for m in messages if getattr(m, "type", None) == "paused"]
        assert len(paused_messages) == 1
        assert paused_messages[0].paused is True

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(
        self, orchestrator: AgentOrchestrator, mock_agent
    ) -> None:
        """Error matching should be case-insensitive."""
        with patch.object(
            orchestrator,
            "run_turn",
            new_callable=AsyncMock,
            side_effect=Exception("CREDIT BALANCE IS TOO LOW"),
        ):
            await _run_one_loop_iteration(orchestrator)

        mock_agent.pause.assert_awaited_once()


class TestTransientErrorHandling:
    """Test that transient errors clear the wake event without pausing."""

    @pytest.mark.asyncio
    async def test_transient_error_clears_wake_event(
        self, orchestrator: AgentOrchestrator, mock_agent
    ) -> None:
        """Transient errors should clear the wake event to prevent immediate retry."""
        with patch.object(
            orchestrator,
            "run_turn",
            new_callable=AsyncMock,
            side_effect=Exception("Connection timeout"),
        ):
            await _run_one_loop_iteration(orchestrator)

        mock_agent.pause.assert_not_awaited()
        assert not orchestrator._wake_event.is_set()

    @pytest.mark.asyncio
    async def test_transient_error_does_not_change_state(
        self, orchestrator: AgentOrchestrator, mock_agent
    ) -> None:
        """Transient errors should not modify agent state or pause reason."""
        state = mock_agent.get_state()
        original_status = state.status
        original_reason = state.pause_reason

        with patch.object(
            orchestrator,
            "run_turn",
            new_callable=AsyncMock,
            side_effect=Exception("Temporary network error"),
        ):
            await _run_one_loop_iteration(orchestrator)

        assert state.status == original_status
        assert state.pause_reason == original_reason
        state.save.assert_not_awaited()
