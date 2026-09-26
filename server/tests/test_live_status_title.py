"""Server-authoritative turn state and piece title, broadcast live to clients."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_monet.agent.callbacks import setup_tool_callbacks
from code_monet.main import _init_message
from code_monet.orchestrator import AgentOrchestrator
from code_monet.types import AgentTurnComplete, PieceTitleMessage, TurnStateMessage
from code_monet.workspace import WorkspaceState


def _orchestrator(agent: MagicMock) -> tuple[AgentOrchestrator, AsyncMock]:
    broadcaster = MagicMock()
    broadcaster.broadcast = AsyncMock()
    return AgentOrchestrator(agent=agent, broadcaster=broadcaster), broadcaster.broadcast


def _agent(turn: Any) -> MagicMock:
    agent = MagicMock()
    agent.pending_nudges = []
    state = MagicMock()
    state.piece_number = 7
    agent.get_state.return_value = state
    agent.run_turn = turn
    return agent


def _broadcast_types(broadcast: AsyncMock) -> list[Any]:
    return [call.args[0] for call in broadcast.await_args_list]


class TestTurnState:
    @pytest.mark.asyncio
    async def test_turn_is_active_while_running_and_broadcast_around_it(self) -> None:
        seen: list[bool] = []

        async def turn(**_: Any) -> AsyncIterator[AgentTurnComplete]:
            seen.append(orchestrator.turn_active)
            yield AgentTurnComplete(thinking="", done=False)

        orchestrator, broadcast = _orchestrator(_agent(turn))

        await orchestrator.run_turn()

        assert seen == [True]
        assert orchestrator.turn_active is False
        states = [m for m in _broadcast_types(broadcast) if isinstance(m, TurnStateMessage)]
        assert [m.active for m in states] == [True, False]

    @pytest.mark.asyncio
    async def test_failed_turn_still_reports_inactive(self) -> None:
        async def turn(**_: Any) -> AsyncIterator[AgentTurnComplete]:
            raise RuntimeError("boom")
            yield AgentTurnComplete(thinking="", done=False)  # pragma: no cover

        orchestrator, broadcast = _orchestrator(_agent(turn))

        with pytest.raises(RuntimeError):
            await orchestrator.run_turn()

        assert orchestrator.turn_active is False
        states = [m for m in _broadcast_types(broadcast) if isinstance(m, TurnStateMessage)]
        assert [m.active for m in states] == [True, False]


class TestPieceTitle:
    @pytest.mark.asyncio
    async def test_naming_the_piece_broadcasts_its_title(self) -> None:
        orchestrator, broadcast = _orchestrator(_agent(MagicMock()))

        callback = orchestrator.create_callbacks().on_piece_titled
        assert callback is not None
        await callback("Harbor Fog")

        [message] = _broadcast_types(broadcast)
        assert message == PieceTitleMessage(piece_number=7, title="Harbor Fog")

    @pytest.mark.asyncio
    async def test_title_tool_callback_saves_then_notifies(self) -> None:
        state = MagicMock()
        state.save = AsyncMock()
        notified: list[str] = []

        async def on_piece_titled(title: str) -> None:
            assert state.current_piece_title == title
            state.save.assert_awaited()
            notified.append(title)

        # Patch every global registration so this test leaks no tool callbacks.
        with (
            patch.multiple(
                "code_monet.agent.callbacks",
                set_paint_callback=MagicMock(),
                set_draw_callback=MagicMock(),
                set_get_canvas_callback=MagicMock(),
                set_add_strokes_callback=MagicMock(),
                set_workspace_dir_callback=MagicMock(),
                set_canvas_dimensions=MagicMock(),
            ),
            patch("code_monet.agent.callbacks.set_piece_title_callback") as register,
        ):
            setup_tool_callbacks(
                state=state,
                get_canvas_png=lambda: b"",
                canvas_width=800,
                canvas_height=600,
                on_paths_collected=AsyncMock(),
                on_piece_titled=on_piece_titled,
            )
            [set_title] = register.call_args.args

        await set_title("Storm")

        assert notified == ["Storm"]


@pytest.mark.asyncio
async def test_init_reports_turn_active(tmp_path: Path) -> None:
    user_dir = tmp_path / "user"
    (user_dir / "gallery").mkdir(parents=True)
    workspace = WorkspaceState(user_id="user", user_dir=user_dir)
    workspace._loaded = True

    assert (await _init_message(workspace, paused=False))["turn_active"] is False
    init = await _init_message(workspace, paused=False, turn_active=True)
    assert init["turn_active"] is True


class _StopTurn(Exception):
    pass


@pytest.mark.asyncio
async def test_openai_agent_wires_the_title_callback() -> None:
    from code_monet.agent import AgentCallbacks
    from code_monet.agent.openai_agent import OpenAIDrawingAgent

    state = MagicMock()
    state.save = AsyncMock()
    agent = OpenAIDrawingAgent(state=state)
    agent._paused = False
    on_piece_titled = AsyncMock()
    captured: dict[str, Any] = {}

    def capture(**kwargs: Any) -> None:
        captured.update(kwargs)
        raise _StopTurn

    with (
        patch("code_monet.agent.openai_agent.settings") as settings,
        patch("code_monet.agent.openai_agent.AsyncOpenAI"),
        patch("code_monet.agent.openai_agent.setup_tool_callbacks", side_effect=capture),
        pytest.raises(_StopTurn),
    ):
        settings.openai_api_key = "test"
        async for _ in agent.run_turn(AgentCallbacks(on_piece_titled=on_piece_titled)):
            pass

    assert captured["on_piece_titled"] is on_piece_titled


class TestConnectInit:
    @pytest.mark.asyncio
    async def test_turn_state_is_sampled_after_building_init(self, tmp_path: Path) -> None:
        """A turn ending while init is built must not leave a stale turn_active."""
        from code_monet.main import _connect_init

        user_dir = tmp_path / "user"
        (user_dir / "gallery").mkdir(parents=True)
        state = WorkspaceState(user_id="user", user_dir=user_dir)
        state._loaded = True
        orchestrator = MagicMock()
        orchestrator.turn_active = True
        list_gallery = state.list_gallery

        async def gallery_while_turn_ends() -> Any:
            orchestrator.turn_active = False  # turn_state false broadcast happens here
            return await list_gallery()

        workspace = MagicMock()
        workspace.state = state
        workspace.agent.paused = False
        workspace.orchestrator = orchestrator

        with patch.object(state, "list_gallery", gallery_while_turn_ends):
            init = await _connect_init(workspace)

        assert init["turn_active"] is False


def test_server_data_symlink_is_ignored() -> None:
    import subprocess

    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", "server/data"], cwd=repo, check=False
    )
    assert result.returncode == 0
