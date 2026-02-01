"""Tests for user message handlers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from code_monet.types import AgentStatus, DrawingStyleType, PauseReason, StyleChangeMessage
from code_monet.user_handlers import (
    handle_new_canvas,
    handle_pause,
    handle_resume,
    handle_user_message,
)


class TestHandleNewCanvas:
    """Test handle_new_canvas function."""

    @pytest.fixture
    def mock_workspace(self) -> MagicMock:
        """Create a mock workspace with all required attributes."""
        workspace = MagicMock()
        workspace.user_id = 1
        workspace.state = MagicMock()
        workspace.state.new_canvas = AsyncMock(return_value="piece_001")
        workspace.state.piece_number = 1
        workspace.state.list_gallery = AsyncMock(return_value=[])
        workspace.state.canvas = MagicMock()
        workspace.state.canvas.drawing_style = DrawingStyleType.PLOTTER
        workspace.state.save = AsyncMock()
        workspace.agent = MagicMock()
        workspace.agent.reset_container = MagicMock()
        workspace.agent.add_nudge = MagicMock()
        workspace.agent.resume = AsyncMock()
        workspace.connections = MagicMock()
        workspace.connections.broadcast = AsyncMock()
        workspace.orchestrator = MagicMock()
        workspace.orchestrator.clear_piece_completed = MagicMock()
        workspace.orchestrator.wake = MagicMock()
        workspace.start_agent_loop = AsyncMock()
        return workspace

    @pytest.mark.asyncio
    async def test_new_canvas_without_style(self, mock_workspace: MagicMock) -> None:
        """New canvas without style should not change drawing style."""
        await handle_new_canvas(mock_workspace, {"direction": "landscape"})

        # Style should not be changed
        assert mock_workspace.state.canvas.drawing_style == DrawingStyleType.PLOTTER
        # Direction should be added as nudge
        mock_workspace.agent.add_nudge.assert_called_once_with("landscape")

    @pytest.mark.asyncio
    async def test_new_canvas_with_style_plotter(self, mock_workspace: MagicMock) -> None:
        """New canvas with plotter style should set style atomically."""
        mock_workspace.state.canvas.drawing_style = DrawingStyleType.PAINT  # Start with paint

        await handle_new_canvas(
            mock_workspace, {"direction": "abstract", "drawing_style": "plotter"}
        )

        # Style should be changed to plotter
        assert mock_workspace.state.canvas.drawing_style == DrawingStyleType.PLOTTER
        # Should save the state
        mock_workspace.state.save.assert_called()
        # Should broadcast style change
        broadcast_calls = mock_workspace.connections.broadcast.call_args_list
        style_change_calls = [
            call for call in broadcast_calls if isinstance(call[0][0], StyleChangeMessage)
        ]
        assert len(style_change_calls) == 1
        assert style_change_calls[0][0][0].drawing_style == DrawingStyleType.PLOTTER

    @pytest.mark.asyncio
    async def test_new_canvas_with_style_paint(self, mock_workspace: MagicMock) -> None:
        """New canvas with paint style should set style atomically."""
        await handle_new_canvas(mock_workspace, {"direction": None, "drawing_style": "paint"})

        # Style should be changed to paint
        assert mock_workspace.state.canvas.drawing_style == DrawingStyleType.PAINT
        # Should broadcast style change
        broadcast_calls = mock_workspace.connections.broadcast.call_args_list
        style_change_calls = [
            call for call in broadcast_calls if isinstance(call[0][0], StyleChangeMessage)
        ]
        assert len(style_change_calls) == 1
        assert style_change_calls[0][0][0].drawing_style == DrawingStyleType.PAINT

    @pytest.mark.asyncio
    async def test_new_canvas_with_invalid_style(self, mock_workspace: MagicMock) -> None:
        """New canvas with invalid style should log warning and not change style."""
        original_style = mock_workspace.state.canvas.drawing_style

        await handle_new_canvas(
            mock_workspace, {"direction": "test", "drawing_style": "invalid_style"}
        )

        # Style should not be changed
        assert mock_workspace.state.canvas.drawing_style == original_style
        # Should still process direction
        mock_workspace.agent.add_nudge.assert_called_once_with("test")

    @pytest.mark.asyncio
    async def test_new_canvas_style_applied_before_agent_starts(
        self, mock_workspace: MagicMock
    ) -> None:
        """Style should be applied before agent resumes (atomic operation)."""
        call_order: list[str] = []

        async def track_broadcast(msg: object) -> None:
            if isinstance(msg, StyleChangeMessage):
                call_order.append("style_change")

        async def track_resume() -> None:
            call_order.append("resume")

        mock_workspace.connections.broadcast.side_effect = track_broadcast
        mock_workspace.agent.resume.side_effect = track_resume

        await handle_new_canvas(mock_workspace, {"drawing_style": "paint"})

        # Style change should be broadcast before agent resumes
        style_idx = call_order.index("style_change") if "style_change" in call_order else -1
        resume_idx = call_order.index("resume") if "resume" in call_order else len(call_order)
        assert style_idx < resume_idx, "Style change should happen before agent resume"

    @pytest.mark.asyncio
    async def test_new_canvas_starts_agent_loop(self, mock_workspace: MagicMock) -> None:
        """New canvas should ensure agent loop is running."""
        await handle_new_canvas(mock_workspace, {"direction": "test"})

        mock_workspace.start_agent_loop.assert_awaited_once()


class TestHandleResume:
    """Test handle_resume function."""

    @pytest.fixture
    def mock_workspace(self) -> MagicMock:
        """Create a mock workspace for resume tests."""
        workspace = MagicMock()
        workspace.user_id = 1
        workspace.state = MagicMock()
        workspace.state.save = AsyncMock()
        workspace.agent = MagicMock()
        workspace.agent.add_nudge = MagicMock()
        workspace.agent.resume = AsyncMock()
        workspace.connections = MagicMock()
        workspace.connections.broadcast = AsyncMock()
        workspace.orchestrator = MagicMock()
        workspace.orchestrator.wake = MagicMock()
        workspace.start_agent_loop = AsyncMock()
        return workspace

    @pytest.mark.asyncio
    async def test_resume_starts_agent_loop(self, mock_workspace: MagicMock) -> None:
        """Resume should restart agent loop before waking."""
        await handle_resume(mock_workspace, {"direction": "test"})

        mock_workspace.start_agent_loop.assert_awaited_once()


class TestHandlePause:
    """Test handle_pause function and PauseReason."""

    @pytest.fixture
    def mock_workspace(self) -> MagicMock:
        """Create a mock workspace for pause tests."""
        workspace = MagicMock()
        workspace.user_id = 1
        workspace.state = MagicMock()
        workspace.state.status = AgentStatus.IDLE
        workspace.state.pause_reason = PauseReason.NONE
        workspace.state.save = AsyncMock()
        workspace.agent = MagicMock()
        workspace.agent.pause = AsyncMock()
        workspace.connections = MagicMock()
        workspace.connections.broadcast = AsyncMock()
        return workspace

    @pytest.mark.asyncio
    async def test_pause_sets_user_reason(self, mock_workspace: MagicMock) -> None:
        """User-initiated pause should set pause_reason to USER."""
        await handle_pause(mock_workspace)

        assert mock_workspace.state.status == AgentStatus.PAUSED
        assert mock_workspace.state.pause_reason == PauseReason.USER
        mock_workspace.agent.pause.assert_awaited_once()
        mock_workspace.state.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pause_broadcasts_paused_true(self, mock_workspace: MagicMock) -> None:
        """Pause should broadcast paused=True to all clients."""
        await handle_pause(mock_workspace)

        broadcast_calls = mock_workspace.connections.broadcast.call_args_list
        assert len(broadcast_calls) == 1
        assert broadcast_calls[0][0][0].paused is True


class TestHandleResumeWithPauseReason:
    """Test handle_resume clears pause_reason."""

    @pytest.fixture
    def mock_workspace(self) -> MagicMock:
        """Create a mock workspace for resume tests."""
        workspace = MagicMock()
        workspace.user_id = 1
        workspace.state = MagicMock()
        workspace.state.status = AgentStatus.PAUSED
        workspace.state.pause_reason = PauseReason.USER
        workspace.state.save = AsyncMock()
        workspace.agent = MagicMock()
        workspace.agent.add_nudge = MagicMock()
        workspace.agent.resume = AsyncMock()
        workspace.connections = MagicMock()
        workspace.connections.broadcast = AsyncMock()
        workspace.orchestrator = MagicMock()
        workspace.orchestrator.wake = MagicMock()
        workspace.start_agent_loop = AsyncMock()
        return workspace

    @pytest.mark.asyncio
    async def test_resume_clears_pause_reason(self, mock_workspace: MagicMock) -> None:
        """Resume should set pause_reason to NONE."""
        await handle_resume(mock_workspace, {})

        assert mock_workspace.state.status == AgentStatus.IDLE
        assert mock_workspace.state.pause_reason == PauseReason.NONE
        mock_workspace.agent.resume.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resume_clears_disconnect_reason(self, mock_workspace: MagicMock) -> None:
        """Resume should clear DISCONNECT reason as well."""
        mock_workspace.state.pause_reason = PauseReason.DISCONNECT

        await handle_resume(mock_workspace, {})

        assert mock_workspace.state.pause_reason == PauseReason.NONE


class TestHandleNewCanvasWithPauseReason:
    """Test handle_new_canvas clears pause_reason."""

    @pytest.fixture
    def mock_workspace(self) -> MagicMock:
        """Create a mock workspace for new_canvas tests."""
        workspace = MagicMock()
        workspace.user_id = 1
        workspace.state = MagicMock()
        workspace.state.new_canvas = AsyncMock(return_value="piece_001")
        workspace.state.piece_number = 1
        workspace.state.list_gallery = AsyncMock(return_value=[])
        workspace.state.canvas = MagicMock()
        workspace.state.canvas.drawing_style = DrawingStyleType.PLOTTER
        workspace.state.status = AgentStatus.PAUSED
        workspace.state.pause_reason = PauseReason.USER
        workspace.state.save = AsyncMock()
        workspace.agent = MagicMock()
        workspace.agent.reset_container = MagicMock()
        workspace.agent.add_nudge = MagicMock()
        workspace.agent.resume = AsyncMock()
        workspace.connections = MagicMock()
        workspace.connections.broadcast = AsyncMock()
        workspace.orchestrator = MagicMock()
        workspace.orchestrator.clear_piece_completed = MagicMock()
        workspace.orchestrator.wake = MagicMock()
        workspace.start_agent_loop = AsyncMock()
        return workspace

    @pytest.mark.asyncio
    async def test_new_canvas_clears_pause_reason(self, mock_workspace: MagicMock) -> None:
        """New canvas should clear pause_reason."""
        await handle_new_canvas(mock_workspace, {})

        assert mock_workspace.state.status == AgentStatus.IDLE
        assert mock_workspace.state.pause_reason == PauseReason.NONE


class TestHandleAnimationDone:
    """Test animation_done routing."""

    @pytest.mark.asyncio
    async def test_animation_done_passes_batch_id(self) -> None:
        workspace = MagicMock()
        workspace.user_id = 1
        workspace.orchestrator = MagicMock()

        handled = await handle_user_message(
            workspace,
            {"type": "animation_done", "batch_id": 7},
        )

        assert handled is True
        workspace.orchestrator.signal_animation_done.assert_called_once_with(7)
