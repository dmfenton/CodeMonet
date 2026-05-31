"""Tests for the drawing agent module."""

import base64
from importlib.metadata import version
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from code_monet.agent import DrawingAgent
from code_monet.types import AgentTurnComplete, DrawingStyleType, Path, PathType, Point


class TestDrawingAgentPauseResume:
    """Tests for agent pause/resume functionality."""

    def test_initial_state(self) -> None:
        agent = DrawingAgent()
        assert agent.paused is True  # Starts paused by default
        assert agent.container_id is None  # SDK manages sessions
        assert agent.pending_nudges == []

    @pytest.mark.asyncio
    async def test_pause(self) -> None:
        agent = DrawingAgent()
        await agent.pause()
        assert agent.paused is True

    @pytest.mark.asyncio
    async def test_resume(self) -> None:
        agent = DrawingAgent()
        await agent.pause()
        await agent.resume()
        assert agent.paused is False

    def test_add_nudge(self) -> None:
        agent = DrawingAgent()
        agent.add_nudge("Draw a circle")
        agent.add_nudge("Use blue color")
        assert len(agent.pending_nudges) == 2
        assert "Draw a circle" in agent.pending_nudges
        assert "Use blue color" in agent.pending_nudges

    def test_reset_container_sets_abort(self) -> None:
        """reset_container sets abort flag (SDK manages actual session)."""
        agent = DrawingAgent()
        agent.reset_container()
        assert agent._abort is True


class TestDrawingAgentImageConversion:
    """Tests for image conversion utilities."""

    def test_image_to_base64(self) -> None:
        agent = DrawingAgent()
        # Create a simple test image
        img = Image.new("RGB", (100, 100), color="white")

        result = agent._image_to_base64(img)

        # Should be a valid base64 string
        assert isinstance(result, str)
        assert len(result) > 0

        # Should be decodable
        decoded = base64.standard_b64decode(result)
        assert len(decoded) > 0

    def test_image_to_base64_with_colors(self) -> None:
        agent = DrawingAgent()
        # Create an image with specific content
        img = Image.new("RGB", (50, 50), color="red")

        result = agent._image_to_base64(img)

        # Verify it's a PNG by decoding and checking header
        decoded = base64.standard_b64decode(result)
        # PNG magic bytes
        assert decoded[:4] == b"\x89PNG"


class TestDrawingAgentRunTurn:
    """Tests for agent turn execution."""

    @pytest.mark.asyncio
    async def test_run_turn_when_paused(self) -> None:
        agent = DrawingAgent()
        await agent.pause()

        events = [event async for event in agent.run_turn()]

        # Should yield a single AgentTurnComplete with empty values
        assert len(events) == 1
        assert isinstance(events[0], AgentTurnComplete)
        assert events[0].thinking == ""
        assert events[0].done is False


class TestDrawingAgentBuildPrompt:
    """Tests for building the prompt string."""

    def _create_mock_state(
        self, strokes: list | None = None, notes: str = "", piece_number: int = 0
    ) -> Any:
        """Create a mock state object for testing."""
        from unittest.mock import MagicMock

        mock_state = MagicMock()
        mock_canvas = MagicMock()
        mock_canvas.strokes = strokes or []
        mock_state.canvas = mock_canvas
        mock_state.notes = notes
        mock_state.piece_number = piece_number
        return mock_state

    def test_build_prompt_basic(self) -> None:
        agent = DrawingAgent()
        agent._state = self._create_mock_state()

        prompt = agent._build_prompt()

        # Should be a string with canvas info
        assert isinstance(prompt, str)
        assert "Canvas size:" in prompt
        assert "Existing strokes: 0" in prompt
        assert "Piece number: 1" in prompt

    def test_build_prompt_with_notes(self) -> None:
        agent = DrawingAgent()
        agent._state = self._create_mock_state(
            notes="Previous work: drew a circle",
            piece_number=1,
        )

        prompt = agent._build_prompt()

        # Should include notes
        assert "Your notes:" in prompt
        assert "drew a circle" in prompt

    def test_build_prompt_with_nudges(self) -> None:
        agent = DrawingAgent()
        agent._state = self._create_mock_state()
        agent.add_nudge("Draw a tree")
        agent.add_nudge("Use green")

        prompt = agent._build_prompt()

        # Should include nudges
        assert "Human nudges:" in prompt
        assert "Draw a tree" in prompt
        assert "Use green" in prompt

        # Nudges should be cleared after building prompt
        assert agent.pending_nudges == []

    def test_build_prompt_clears_nudges(self) -> None:
        agent = DrawingAgent()
        agent._state = self._create_mock_state()
        agent.add_nudge("Test nudge")

        agent._build_prompt()

        # Nudges should be cleared
        assert agent.pending_nudges == []


class TestDrawingAgentContainerManagement:
    """Tests for container/session management."""

    def test_container_id_always_none(self) -> None:
        """container_id always returns None (SDK manages sessions)."""
        agent = DrawingAgent()
        assert agent.container_id is None

    def test_reset_container_disconnects_client(self) -> None:
        """reset_container sets abort flag and triggers disconnect."""
        agent = DrawingAgent()
        agent.reset_container()
        assert agent._abort is True
        # Client disconnect happens async - just verify abort is set


class TestPostToolUseHook:
    """Tests for _post_tool_use_hook behavior."""

    def _create_agent_with_paths(self, paths: list[Path] | None = None) -> DrawingAgent:
        """Create an agent with pre-populated collected paths."""
        agent = DrawingAgent()
        if paths:
            agent._collected_paths = paths.copy()
        return agent

    @pytest.mark.asyncio
    async def test_hook_calls_on_draw_for_draw_paths(self) -> None:
        """Hook calls _on_draw when draw_paths tool completes with collected paths."""
        agent = self._create_agent_with_paths(
            [Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])]
        )
        on_draw_mock = AsyncMock()
        agent.set_on_draw(on_draw_mock)

        # SDK passes a dict at runtime
        input_data = {"tool_name": "mcp__drawing__draw_paths", "tool_input": {}}
        await agent._post_tool_use_hook(input_data, None, MagicMock())

        on_draw_mock.assert_called_once()
        assert len(agent._collected_paths) == 0  # Cleared after draw

    @pytest.mark.asyncio
    async def test_hook_calls_on_draw_for_generate_svg(self) -> None:
        """Hook calls _on_draw when generate_svg tool completes."""
        agent = self._create_agent_with_paths(
            [
                Path(
                    type=PathType.CUBIC,
                    points=[
                        Point(x=0, y=0),
                        Point(x=50, y=50),
                        Point(x=100, y=0),
                        Point(x=100, y=100),
                    ],
                )
            ]
        )
        on_draw_mock = AsyncMock()
        agent.set_on_draw(on_draw_mock)

        input_data = {"tool_name": "mcp__drawing__generate_svg", "tool_input": {}}
        await agent._post_tool_use_hook(input_data, None, MagicMock())

        on_draw_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_hook_skips_on_draw_when_no_paths(self) -> None:
        """Hook does not call _on_draw when collected_paths is empty."""
        agent = DrawingAgent()
        on_draw_mock = AsyncMock()
        agent.set_on_draw(on_draw_mock)

        input_data = {"tool_name": "mcp__drawing__draw_paths", "tool_input": {}}
        await agent._post_tool_use_hook(input_data, None, MagicMock())

        on_draw_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_hook_skips_on_draw_when_callback_not_set(self) -> None:
        """Hook handles missing _on_draw callback gracefully."""
        agent = self._create_agent_with_paths(
            [Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])]
        )
        # Don't set on_draw callback

        input_data = {"tool_name": "mcp__drawing__draw_paths", "tool_input": {}}
        await agent._post_tool_use_hook(input_data, None, MagicMock())

        # Should not raise, paths should still be cleared
        assert len(agent._collected_paths) == 0

    @pytest.mark.asyncio
    async def test_hook_sets_piece_done_for_mark_piece_done(self) -> None:
        """Hook sets _piece_done flag when mark_piece_done tool completes."""
        agent = DrawingAgent()
        assert agent._piece_done is False

        input_data = {"tool_name": "mcp__drawing__mark_piece_done", "tool_input": {}}
        await agent._post_tool_use_hook(input_data, None, MagicMock())

        assert agent._piece_done is True

    @pytest.mark.asyncio
    async def test_hook_calls_on_draw_for_sign_canvas(self) -> None:
        """Hook calls _on_draw when sign_canvas tool completes with collected paths.

        Regression test: sign_canvas generates signature paths that must be animated
        just like draw_paths and generate_svg. Without this, signatures appear
        instantly instead of being animated.
        """
        agent = self._create_agent_with_paths(
            [Path(type=PathType.SVG, points=[], d="M 0 0 L 100 100")]
        )
        on_draw_mock = AsyncMock()
        agent.set_on_draw(on_draw_mock)

        input_data = {"tool_name": "mcp__drawing__sign_canvas", "tool_input": {}}
        await agent._post_tool_use_hook(input_data, None, MagicMock())

        on_draw_mock.assert_called_once()
        assert len(agent._collected_paths) == 0  # Cleared after draw

    @pytest.mark.asyncio
    async def test_hook_ignores_other_tools(self) -> None:
        """Hook does not trigger drawing for unrelated tools."""
        agent = self._create_agent_with_paths(
            [Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])]
        )
        on_draw_mock = AsyncMock()
        agent.set_on_draw(on_draw_mock)

        input_data = {"tool_name": "mcp__drawing__view_canvas", "tool_input": {}}
        await agent._post_tool_use_hook(input_data, None, MagicMock())

        on_draw_mock.assert_not_called()
        # Paths should NOT be cleared for other tools
        assert len(agent._collected_paths) == 1

    @pytest.mark.asyncio
    async def test_hook_handles_empty_tool_name(self) -> None:
        """Hook handles missing/empty tool_name gracefully."""
        agent = self._create_agent_with_paths(
            [Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])]
        )
        on_draw_mock = AsyncMock()
        agent.set_on_draw(on_draw_mock)

        input_data: dict[str, Any] = {"tool_input": {}}  # No tool_name
        await agent._post_tool_use_hook(input_data, None, MagicMock())

        on_draw_mock.assert_not_called()


class TestClaudeAgentSDKCompatibility:
    """Tests that validate compatibility with Claude Agent SDK.

    These tests catch breaking changes in the SDK (like parameter renames)
    before they hit production. They don't make API calls - they just verify
    that our option construction is valid.
    """

    def test_build_options_without_workspace(self) -> None:
        """Verify ClaudeAgentOptions accepts our base parameters."""
        agent = DrawingAgent()
        # This will raise TypeError if SDK parameters changed
        options = agent._build_options(DrawingStyleType.PLOTTER)
        assert options is not None

    def test_claude_agent_sdk_has_streaming_writer_fix(self) -> None:
        """Pin the SDK above the subprocess streaming writer regression."""
        sdk_version = tuple(int(part) for part in version("claude-agent-sdk").split("."))
        assert sdk_version >= (0, 2, 87)

    def test_build_options_with_workspace_directory(self) -> None:
        """Verify ClaudeAgentOptions accepts cwd parameter.

        Regression test: SDK renamed 'working_directory' to 'cwd' in v1.x.
        This test would have caught that breaking change immediately.
        """
        agent = DrawingAgent()
        # This will raise TypeError if 'cwd' parameter is renamed/removed
        options = agent._build_options(
            DrawingStyleType.PLOTTER, workspace_dir="/tmp/test-workspace"
        )
        assert options is not None

    def test_build_options_paint_style(self) -> None:
        """Verify options work with PAINT drawing style."""
        agent = DrawingAgent()
        options = agent._build_options(DrawingStyleType.PAINT)
        assert options is not None
