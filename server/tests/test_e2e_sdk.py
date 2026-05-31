"""End-to-end tests for Claude Agent SDK integration.

These tests make real API calls to verify SDK compatibility.
They catch breaking changes like parameter renames before production.

Run:
    make test-e2e-sdk

API key is loaded from SSM (production) or .env (local).
Cost: Uses claude-3-5-haiku (fastest/cheapest) with minimal prompts.
"""

from __future__ import annotations

from pathlib import Path as FilePath

import pytest

from code_monet.agent import DrawingAgent
from code_monet.types import AgentTurnComplete, DrawingStyleType
from code_monet.workspace import WorkspaceState

# Mark all tests as e2e (excluded from default pytest run, use -m e2e to include)
pytestmark = pytest.mark.e2e


@pytest.fixture
async def workspace(tmp_path: FilePath) -> WorkspaceState:
    """Create a minimal workspace for testing."""
    user_dir = tmp_path / "1"
    user_dir.mkdir(parents=True)
    (user_dir / "gallery").mkdir()

    state = WorkspaceState(user_id="1", user_dir=user_dir)
    state._loaded = True
    return state


@pytest.fixture
def use_haiku(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use haiku for faster/cheaper E2E tests."""
    monkeypatch.setattr(
        "code_monet.config.settings.agent_model",
        "claude-3-5-haiku-latest",
    )


class TestSDKIntegrationE2E:
    """End-to-end tests that exercise the full SDK integration path.

    These tests validate:
    1. ClaudeAgentOptions construction is accepted by SDK
    2. ClaudeSDKClient.connect() succeeds
    3. query() and receive_response() work correctly
    4. Streaming events are properly typed and handled

    The tests use haiku and minimal prompts to reduce cost and execution time.
    """

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    @pytest.mark.usefixtures("use_haiku")
    async def test_agent_turn_executes_without_sdk_errors(self, workspace: WorkspaceState) -> None:
        """Verify agent can complete a turn without SDK errors.

        This is the primary integration test. It exercises:
        - ClaudeAgentOptions with all our parameters including cwd
        - ClaudeSDKClient connection
        - MCP server registration (drawing tools)
        - Streaming response handling

        If the SDK changes parameter names (like working_directory -> cwd),
        this test will fail immediately with a clear TypeError.
        """
        agent = DrawingAgent(state=workspace)
        await agent.resume()

        async def noop_draw(paths: list, done: bool = False) -> None:
            pass

        agent.set_on_draw(noop_draw)

        # Run the turn - this exercises the full SDK path
        events = [event async for event in agent.run_turn()]

        # Turn should complete with at least one event
        assert len(events) >= 1, "Expected at least one event from run_turn"

        last_event = events[-1]
        assert isinstance(last_event, AgentTurnComplete), (
            f"Expected AgentTurnComplete, got {type(last_event)}"
        )

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    @pytest.mark.usefixtures("use_haiku")
    async def test_agent_turn_with_workspace_cwd(self, workspace: WorkspaceState) -> None:
        """Verify workspace_dir is correctly passed as cwd to SDK.

        Regression test: SDK renamed 'working_directory' to 'cwd'.
        This test explicitly uses a workspace with a directory set.
        """
        # Ensure workspace has a directory (workspace_dir is the public property)
        assert workspace.workspace_dir is not None

        agent = DrawingAgent(state=workspace)
        await agent.resume()

        async def noop_draw(paths: list, done: bool = False) -> None:
            pass

        agent.set_on_draw(noop_draw)

        # The workspace_dir gets passed to _build_options as cwd
        # If the parameter name is wrong, SDK will reject it
        events = [event async for event in agent.run_turn()]

        assert len(events) >= 1
        assert isinstance(events[-1], AgentTurnComplete)

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_paused_agent_no_api_call(self, workspace: WorkspaceState) -> None:
        """Verify paused agent doesn't make API calls.

        Fast test - no API call, no haiku needed.
        """
        agent = DrawingAgent(state=workspace)
        # Agent starts paused by default
        assert agent.paused is True

        events = [event async for event in agent.run_turn()]

        assert len(events) == 1
        assert isinstance(events[0], AgentTurnComplete)
        assert events[0].thinking == ""
        assert events[0].done is False

        # No client should be created
        assert agent._client is None


class TestSDKOptionsWithRealValidation:
    """Test SDK options with styles that exercise different code paths."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    @pytest.mark.usefixtures("use_haiku")
    async def test_plotter_style_turn(self, workspace: WorkspaceState) -> None:
        """Verify PLOTTER style works end-to-end."""
        workspace.canvas.drawing_style = DrawingStyleType.PLOTTER

        agent = DrawingAgent(state=workspace)
        await agent.resume()

        async def noop_draw(paths: list, done: bool = False) -> None:
            pass

        agent.set_on_draw(noop_draw)

        events = [event async for event in agent.run_turn()]
        assert len(events) >= 1
        assert isinstance(events[-1], AgentTurnComplete)

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    @pytest.mark.usefixtures("use_haiku")
    async def test_paint_style_turn(self, workspace: WorkspaceState) -> None:
        """Verify PAINT style works end-to-end."""
        workspace.canvas.drawing_style = DrawingStyleType.PAINT

        agent = DrawingAgent(state=workspace)
        await agent.resume()

        async def noop_draw(paths: list, done: bool = False) -> None:
            pass

        agent.set_on_draw(noop_draw)

        events = [event async for event in agent.run_turn()]
        assert len(events) >= 1
        assert isinstance(events[-1], AgentTurnComplete)
