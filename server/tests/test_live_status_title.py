"""Server-authoritative turn state and piece title, broadcast live to clients."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    """The title is stored and announced by the naming agent's own orchestrator."""

    @pytest.mark.asyncio
    async def test_successful_name_piece_stores_and_broadcasts_title(self) -> None:
        agent = _agent(MagicMock())
        state = agent.get_state.return_value
        state.save = AsyncMock()
        orchestrator, broadcast = _orchestrator(agent)

        await orchestrator._handle_tool_complete("name_piece", {"title": "  Harbor Fog "}, 1, "", 0)

        assert state.current_piece_title == "Harbor Fog"
        state.save.assert_awaited()
        titles = [m for m in _broadcast_types(broadcast) if isinstance(m, PieceTitleMessage)]
        assert titles == [PieceTitleMessage(piece_number=7, title="Harbor Fog")]

    @pytest.mark.asyncio
    async def test_failed_or_empty_name_piece_changes_nothing(self) -> None:
        agent = _agent(MagicMock())
        state = agent.get_state.return_value
        state.current_piece_title = None
        state.save = AsyncMock()
        orchestrator, broadcast = _orchestrator(agent)

        await orchestrator._handle_tool_complete("name_piece", {"title": "Blocked"}, 1, "", 1)
        await orchestrator._handle_tool_complete("name_piece", {"title": "   "}, 1, "", 0)

        assert state.current_piece_title is None
        assert not [m for m in _broadcast_types(broadcast) if isinstance(m, PieceTitleMessage)]

    @pytest.mark.asyncio
    async def test_each_workspace_records_only_its_own_title(self) -> None:
        """Concurrent users: one agent's name_piece never reaches another workspace."""
        agent_a, agent_b = _agent(MagicMock()), _agent(MagicMock())
        for agent in (agent_a, agent_b):
            agent.get_state.return_value.save = AsyncMock()
            agent.get_state.return_value.current_piece_title = None
        orchestrator_a, broadcast_a = _orchestrator(agent_a)
        orchestrator_b, broadcast_b = _orchestrator(agent_b)

        await orchestrator_a._handle_tool_complete("name_piece", {"title": "A's piece"}, 1, "", 0)

        assert agent_a.get_state.return_value.current_piece_title == "A's piece"
        assert agent_b.get_state.return_value.current_piece_title is None
        assert not [m for m in _broadcast_types(broadcast_b) if isinstance(m, PieceTitleMessage)]
        assert [
            m.title for m in _broadcast_types(broadcast_a) if isinstance(m, PieceTitleMessage)
        ] == ["A's piece"]


@pytest.mark.asyncio
async def test_init_reports_turn_active(tmp_path: Path) -> None:
    user_dir = tmp_path / "user"
    (user_dir / "gallery").mkdir(parents=True)
    workspace = WorkspaceState(user_id="user", user_dir=user_dir)
    workspace._loaded = True

    assert (await _init_message(workspace, paused=False))["turn_active"] is False
    init = await _init_message(workspace, paused=False, turn_active=True)
    assert init["turn_active"] is True


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
