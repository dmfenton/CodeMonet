"""Tests for the agent callbacks module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_monet.agent.callbacks import setup_tool_callbacks
from code_monet.types import Path, PathType, Point


class TestSetupToolCallbacks:
    """Tests for setup_tool_callbacks function."""

    def _create_mock_state(self) -> MagicMock:
        """Create a mock workspace state."""
        state = MagicMock()
        state.workspace_dir = "/tmp/test-workspace"
        state.add_stroke = AsyncMock()
        state.save = AsyncMock()
        state.current_piece_title = None
        return state

    @patch("code_monet.agent.callbacks.set_draw_callback")
    @patch("code_monet.agent.callbacks.set_get_canvas_callback")
    @patch("code_monet.agent.callbacks.set_add_strokes_callback")
    @patch("code_monet.agent.callbacks.set_workspace_dir_callback")
    @patch("code_monet.agent.callbacks.set_piece_title_callback")
    @patch("code_monet.agent.callbacks.set_canvas_dimensions")
    def test_sets_canvas_dimensions(
        self,
        mock_set_dimensions: MagicMock,
        _mock_set_title: MagicMock,
        _mock_set_workspace: MagicMock,
        _mock_set_add_strokes: MagicMock,
        _mock_set_canvas: MagicMock,
        _mock_set_draw: MagicMock,
    ) -> None:
        """Canvas dimensions are set correctly."""
        state = self._create_mock_state()
        get_canvas_png = MagicMock(return_value=b"png data")
        on_paths_collected = AsyncMock()

        setup_tool_callbacks(
            state=state,
            get_canvas_png=get_canvas_png,
            canvas_width=800,
            canvas_height=600,
            on_paths_collected=on_paths_collected,
        )

        mock_set_dimensions.assert_called_once_with(800, 600)

    @patch("code_monet.agent.callbacks.set_draw_callback")
    @patch("code_monet.agent.callbacks.set_get_canvas_callback")
    @patch("code_monet.agent.callbacks.set_add_strokes_callback")
    @patch("code_monet.agent.callbacks.set_workspace_dir_callback")
    @patch("code_monet.agent.callbacks.set_piece_title_callback")
    @patch("code_monet.agent.callbacks.set_canvas_dimensions")
    def test_registers_all_callbacks(
        self,
        _mock_set_dimensions: MagicMock,
        mock_set_title: MagicMock,
        mock_set_workspace: MagicMock,
        mock_set_add_strokes: MagicMock,
        mock_set_canvas: MagicMock,
        mock_set_draw: MagicMock,
    ) -> None:
        """All tool callbacks are registered."""
        state = self._create_mock_state()
        get_canvas_png = MagicMock(return_value=b"png data")
        on_paths_collected = AsyncMock()

        setup_tool_callbacks(
            state=state,
            get_canvas_png=get_canvas_png,
            canvas_width=800,
            canvas_height=600,
            on_paths_collected=on_paths_collected,
        )

        # Verify all callbacks were registered
        mock_set_draw.assert_called_once()
        mock_set_canvas.assert_called_once_with(get_canvas_png)
        mock_set_add_strokes.assert_called_once()
        mock_set_workspace.assert_called_once()
        mock_set_title.assert_called_once()

    @patch("code_monet.agent.callbacks.set_draw_callback")
    @patch("code_monet.agent.callbacks.set_get_canvas_callback")
    @patch("code_monet.agent.callbacks.set_add_strokes_callback")
    @patch("code_monet.agent.callbacks.set_workspace_dir_callback")
    @patch("code_monet.agent.callbacks.set_piece_title_callback")
    @patch("code_monet.agent.callbacks.set_canvas_dimensions")
    def test_draw_callback_receives_on_paths_collected(
        self,
        _mock_set_dimensions: MagicMock,
        _mock_set_title: MagicMock,
        _mock_set_workspace: MagicMock,
        _mock_set_add_strokes: MagicMock,
        _mock_set_canvas: MagicMock,
        mock_set_draw: MagicMock,
    ) -> None:
        """Draw callback is set with the provided callback."""
        state = self._create_mock_state()
        get_canvas_png = MagicMock(return_value=b"png data")
        on_paths_collected = AsyncMock()

        setup_tool_callbacks(
            state=state,
            get_canvas_png=get_canvas_png,
            canvas_width=800,
            canvas_height=600,
            on_paths_collected=on_paths_collected,
        )

        # Verify the draw callback was registered with our function
        mock_set_draw.assert_called_once_with(on_paths_collected)

    @patch("code_monet.agent.callbacks.set_draw_callback")
    @patch("code_monet.agent.callbacks.set_get_canvas_callback")
    @patch("code_monet.agent.callbacks.set_add_strokes_callback")
    @patch("code_monet.agent.callbacks.set_workspace_dir_callback")
    @patch("code_monet.agent.callbacks.set_piece_title_callback")
    @patch("code_monet.agent.callbacks.set_canvas_dimensions")
    @pytest.mark.asyncio
    async def test_workspace_dir_callback_returns_correct_path(
        self,
        _mock_set_dimensions: MagicMock,
        _mock_set_title: MagicMock,
        mock_set_workspace: MagicMock,
        _mock_set_add_strokes: MagicMock,
        _mock_set_canvas: MagicMock,
        _mock_set_draw: MagicMock,
    ) -> None:
        """Workspace directory callback returns state's workspace_dir."""
        state = self._create_mock_state()
        state.workspace_dir = "/custom/workspace/path"
        get_canvas_png = MagicMock(return_value=b"png data")
        on_paths_collected = AsyncMock()

        setup_tool_callbacks(
            state=state,
            get_canvas_png=get_canvas_png,
            canvas_width=800,
            canvas_height=600,
            on_paths_collected=on_paths_collected,
        )

        # Get the registered callback and verify it returns correct path
        registered_callback = mock_set_workspace.call_args[0][0]
        assert registered_callback() == "/custom/workspace/path"

    @patch("code_monet.agent.callbacks.set_draw_callback")
    @patch("code_monet.agent.callbacks.set_get_canvas_callback")
    @patch("code_monet.agent.callbacks.set_add_strokes_callback")
    @patch("code_monet.agent.callbacks.set_workspace_dir_callback")
    @patch("code_monet.agent.callbacks.set_piece_title_callback")
    @patch("code_monet.agent.callbacks.set_canvas_dimensions")
    @pytest.mark.asyncio
    async def test_add_strokes_callback_adds_to_state(
        self,
        _mock_set_dimensions: MagicMock,
        _mock_set_title: MagicMock,
        _mock_set_workspace: MagicMock,
        mock_set_add_strokes: MagicMock,
        _mock_set_canvas: MagicMock,
        _mock_set_draw: MagicMock,
    ) -> None:
        """Add strokes callback calls state.add_stroke for each path."""
        state = self._create_mock_state()
        get_canvas_png = MagicMock(return_value=b"png data")
        on_paths_collected = AsyncMock()

        setup_tool_callbacks(
            state=state,
            get_canvas_png=get_canvas_png,
            canvas_width=800,
            canvas_height=600,
            on_paths_collected=on_paths_collected,
        )

        # Get the registered callback
        registered_callback = mock_set_add_strokes.call_args[0][0]

        # Create test paths
        paths = [
            Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)]),
            Path(type=PathType.LINE, points=[Point(x=200, y=200), Point(x=300, y=300)]),
        ]

        # Call the callback
        await registered_callback(paths)

        # Verify add_stroke was called for each path
        assert state.add_stroke.call_count == 2

    @patch("code_monet.agent.callbacks.set_draw_callback")
    @patch("code_monet.agent.callbacks.set_get_canvas_callback")
    @patch("code_monet.agent.callbacks.set_add_strokes_callback")
    @patch("code_monet.agent.callbacks.set_workspace_dir_callback")
    @patch("code_monet.agent.callbacks.set_piece_title_callback")
    @patch("code_monet.agent.callbacks.set_canvas_dimensions")
    @pytest.mark.asyncio
    async def test_piece_title_callback_sets_title_and_saves(
        self,
        _mock_set_dimensions: MagicMock,
        mock_set_title: MagicMock,
        _mock_set_workspace: MagicMock,
        _mock_set_add_strokes: MagicMock,
        _mock_set_canvas: MagicMock,
        _mock_set_draw: MagicMock,
    ) -> None:
        """Piece title callback sets title and saves state."""
        state = self._create_mock_state()
        get_canvas_png = MagicMock(return_value=b"png data")
        on_paths_collected = AsyncMock()

        setup_tool_callbacks(
            state=state,
            get_canvas_png=get_canvas_png,
            canvas_width=800,
            canvas_height=600,
            on_paths_collected=on_paths_collected,
        )

        # Get the registered callback
        registered_callback = mock_set_title.call_args[0][0]

        # Call the callback
        await registered_callback("Sunset Dreams")

        # Verify title was set and state was saved
        assert state.current_piece_title == "Sunset Dreams"
        state.save.assert_called_once()
