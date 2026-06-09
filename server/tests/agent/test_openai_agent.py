"""Tests for the OpenAI drawing agent."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from code_monet.agent import AgentCallbacks
from code_monet.agent.openai_agent import (
    OpenAIDrawingAgent,
    _decode_tool_args,
    _response_function_calls,
)
from code_monet.config import settings
from code_monet.types import AgentTurnComplete, CanvasState, DrawingStyleType, Path, PathType, Point


class FakeState:
    def __init__(self, notes: str = "") -> None:
        self.canvas = CanvasState()
        self.notes = notes
        self.piece_number = 0
        self.workspace_dir = "/tmp"
        self.current_piece_title = None

    async def add_stroke(self, path: Any) -> None:
        self.canvas.strokes.append(path)

    async def save(self) -> None:
        return None


class TestOpenAIDrawingAgentPauseResume:
    def test_initial_state(self) -> None:
        agent = OpenAIDrawingAgent()
        assert agent.paused is True
        assert agent.container_id is None
        assert agent.pending_nudges == []

    @pytest.mark.asyncio
    async def test_run_turn_when_paused(self) -> None:
        agent = OpenAIDrawingAgent()
        await agent.pause()

        events = [event async for event in agent.run_turn()]

        assert len(events) == 1
        assert isinstance(events[0], AgentTurnComplete)
        assert events[0].thinking == ""
        assert events[0].done is False

    def test_reset_container_sets_abort(self) -> None:
        agent = OpenAIDrawingAgent()
        agent.reset_container()
        assert agent._abort is True

    def test_get_state_requires_constructor_state(self) -> None:
        agent = OpenAIDrawingAgent()

        with pytest.raises(RuntimeError, match="Agent state not initialized"):
            agent.get_state()

    def test_prompt_includes_notes_and_clears_nudges(self) -> None:
        agent = OpenAIDrawingAgent(FakeState(notes="Earlier: circles"))
        agent.add_nudge("Use blue")

        prompt = agent._build_prompt()

        assert "Earlier: circles" in prompt
        assert "Use blue" in prompt
        assert agent.pending_nudges == []

    def test_get_style_config_uses_canvas_style(self) -> None:
        state = FakeState()
        state.canvas.drawing_style = DrawingStyleType.PAINT
        agent = OpenAIDrawingAgent(state)

        assert agent.get_style_config().type == DrawingStyleType.PAINT


def test_response_function_calls_extracts_calls() -> None:
    response = SimpleNamespace(
        output=[
            SimpleNamespace(type="message", content=[]),
            SimpleNamespace(
                type="function_call",
                call_id="call_123",
                name="draw_paths",
                arguments='{"paths":[]}',
            ),
        ]
    )

    assert _response_function_calls(response) == [
        {"call_id": "call_123", "name": "draw_paths", "arguments": '{"paths":[]}'}
    ]


def test_response_function_calls_skips_incomplete_calls() -> None:
    response = SimpleNamespace(
        output=[
            SimpleNamespace(type="function_call", call_id=None, name="draw_paths"),
            SimpleNamespace(type="function_call", call_id="call_123", name=None),
        ]
    )

    assert _response_function_calls(response) == []


@pytest.mark.parametrize(
    ("raw_args", "expected"),
    [
        ('{"title":"Quiet Lines"}', {"title": "Quiet Lines"}),
        ("[]", {}),
        ("not-json", {}),
        (None, {}),
    ],
)
def test_decode_tool_args(raw_args: str | None, expected: dict[str, Any]) -> None:
    assert _decode_tool_args(raw_args) == expected


@pytest.mark.asyncio
async def test_run_turn_requires_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "")
    agent = OpenAIDrawingAgent(FakeState())
    await agent.resume()

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        [event async for event in agent.run_turn()]


@pytest.mark.asyncio
async def test_flush_collected_paths_calls_draw_callback() -> None:
    agent = OpenAIDrawingAgent(FakeState())
    on_draw = AsyncMock()
    agent.set_on_draw(on_draw)
    agent._collected_paths = [Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=1, y=1)])]

    await agent._flush_collected_paths()

    on_draw.assert_awaited_once()
    assert agent._collected_paths == []


@pytest.mark.asyncio
async def test_run_tool_reports_unknown_tool() -> None:
    agent = OpenAIDrawingAgent(FakeState())
    on_code_start = AsyncMock()
    on_code_result = AsyncMock()
    on_tool_complete = AsyncMock()
    agent.set_on_tool_complete(on_tool_complete)

    result = await agent._run_tool(
        "missing_tool",
        {},
        AgentCallbacks(on_code_start=on_code_start, on_code_result=on_code_result),
    )

    assert result["is_error"] is True
    on_code_start.assert_awaited_once()
    on_code_result.assert_awaited_once()
    on_tool_complete.assert_awaited_once_with(
        "missing_tool",
        {},
        1,
        "Error: unknown tool missing_tool",
        1,
    )


@pytest.mark.asyncio
async def test_run_turn_executes_openai_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    first_response = SimpleNamespace(
        id="resp_1",
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                call_id="call_123",
                name="draw_paths",
                arguments=(
                    '{"paths":[{"type":"line","points":[{"x":0,"y":0},{"x":10,"y":10}]}],'
                    '"done":true}'
                ),
            )
        ],
    )
    second_response = SimpleNamespace(id="resp_2", output_text="looks good", output=[])
    create = AsyncMock(side_effect=[first_response, second_response])
    on_iteration_start = AsyncMock()
    on_thinking = AsyncMock()

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    agent = OpenAIDrawingAgent(FakeState())
    agent._client = cast(Any, SimpleNamespace(responses=SimpleNamespace(create=create)))
    await agent.resume()

    events = [
        event
        async for event in agent.run_turn(
            AgentCallbacks(on_iteration_start=on_iteration_start, on_thinking=on_thinking)
        )
    ]

    assert len(events) == 1
    assert isinstance(events[0], AgentTurnComplete)
    assert events[0].thinking == "looks good"
    assert events[0].done is True
    assert len(agent.get_state().canvas.strokes) == 1
    assert create.await_count == 2
    assert create.await_args_list[1].kwargs["previous_response_id"] == "resp_1"
    on_iteration_start.assert_any_await(1, settings.max_agent_iterations)
    on_thinking.assert_awaited_once_with("looks good", 2)
