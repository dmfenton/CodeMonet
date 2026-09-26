"""Two users' agents in one process: each tool call must act only on its own agent.

Reproduces the multi-user bug where tool handlers read process-global callbacks
that every turn overwrote: with user B's turn set up after user A's, A's `paint`
ran B's program, A's `draw_paths` wrote into B's workspace, A's `view_canvas`
showed B's canvas, and B's failed critique blocked A's finish tools.

The tools are called through each agent's own in-process MCP server over the SDK's
JSON-RPC bridge — the same path the Claude CLI uses.
"""

from __future__ import annotations

import asyncio
import base64
import re
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from claude_agent_sdk._internal.sdk_mcp_bridge import SdkMcpBridge

from code_monet.agent import DrawingAgent
from code_monet.agent.openai_agent import OpenAIDrawingAgent
from code_monet.config import settings
from code_monet.program_painting import PaintFailure, PaintResult
from code_monet.types import AgentTurnComplete, DrawingStyleType, Path


@dataclass
class FakeCanvas:
    width: int
    height: int
    drawing_style: DrawingStyleType = DrawingStyleType.PLOTTER
    strokes: list[Path] = field(default_factory=list)


@dataclass
class FakeState:
    """The slice of WorkspaceState a turn and the drawing tools touch."""

    name: str
    canvas: FakeCanvas
    workspace_dir: str
    status: Any = None
    added: list[Path] = field(default_factory=list)

    async def save(self) -> None:
        return None

    async def add_strokes(self, paths: list[Path]) -> None:
        self.added.extend(paths)


class FakeClient:
    """Stands in for ClaudeSDKClient; the turn body runs `script`."""

    def __init__(self, script: Callable[[], Awaitable[None]]) -> None:
        self.script = script

    async def query(self, _prompt: AsyncGenerator[dict[str, Any], None]) -> None:
        return None


class ToolCaller:
    """Speaks MCP JSON-RPC to one agent's drawing server, like the CLI does."""

    def __init__(self, agent: DrawingAgent) -> None:
        self._bridge = SdkMcpBridge("drawing", agent._drawing_server["instance"])
        self._next_id = 0

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        response = await self._bridge.handle(
            {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        )
        assert response is not None
        assert "result" in response, response
        result: dict[str, Any] = response["result"]
        return result

    async def start(self) -> None:
        await self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "isolation-test", "version": "0"},
            },
        )
        await self._bridge.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("tools/call", {"name": name, "arguments": arguments or {}})

    async def close(self) -> None:
        await self._bridge.aclose()


def _text(result: dict[str, Any]) -> str:
    return "\n".join(c["text"] for c in result["content"] if c["type"] == "text")


def _image(result: dict[str, Any]) -> bytes:
    images = [c for c in result["content"] if c["type"] == "image"]
    assert len(images) == 1
    return base64.standard_b64decode(images[0]["data"])


def _make_agent(name: str, width: int, height: int) -> tuple[DrawingAgent, FakeState]:
    state = FakeState(
        name=name, canvas=FakeCanvas(width, height), workspace_dir=f"/workspaces/{name}"
    )
    agent = DrawingAgent(state=state)  # type: ignore[arg-type]
    agent._paused = False

    def canvas_bytes(highlight_human: bool = True) -> bytes:  # noqa: ARG001
        return f"canvas-{name}".encode()

    agent._get_canvas_image = canvas_bytes  # type: ignore[method-assign]
    return agent, state


async def _fake_paint(state: FakeState) -> PaintResult:
    return PaintFailure(error=f"ran program of {state.name}", seconds=0.0)


async def _fake_critique(brief: str, canvas: bytes, *_rest: Any) -> str:
    verdict = "PASS" if brief.startswith("pass") else "FAIL"
    return f"VERDICT: {verdict}\nFINDINGS:\n- canvas was {canvas.decode()}"


async def _fake_process(client: FakeClient, **_kwargs: Any) -> SimpleNamespace:
    await client.script()
    return SimpleNamespace(aborted=False, thinking="")


@pytest.mark.asyncio
async def test_overlapping_turns_keep_tool_calls_on_their_own_agent() -> None:
    agent_a, state_a = _make_agent("A", 800, 600)
    agent_b, state_b = _make_agent("B", 400, 300)
    caller_a, caller_b = ToolCaller(agent_a), ToolCaller(agent_b)
    b_turn_started = asyncio.Event()
    release_b = asyncio.Event()
    results: dict[str, dict[str, Any]] = {}

    async def turn_b() -> None:
        b_turn_started.set()
        await release_b.wait()

    async def turn_a() -> None:
        # User B's turn starts while A's is still running: B's setup runs now.
        b_task = asyncio.create_task(anext(agent_b.run_turn()))
        await b_turn_started.wait()
        try:
            await caller_a.start()
            await caller_b.start()
            results["paint"] = await caller_a.call("paint")
            results["draw"] = await caller_a.call(
                "draw_paths",
                {
                    "paths": [
                        {"type": "line", "points": [{"x": 700, "y": 500}, {"x": 790, "y": 590}]}
                    ]
                },
            )
            results["view"] = await caller_a.call("view_canvas")
            results["critique_a"] = await caller_a.call("critique_canvas", {"brief": "pass: A"})
            results["critique_b"] = await caller_b.call("critique_canvas", {"brief": "fail: B"})
            results["name_a"] = await caller_a.call("name_piece", {"title": "A's Harbor"})
            results["name_b"] = await caller_b.call("name_piece", {"title": "B's Field"})
            results["sign_a"] = await caller_a.call("sign_canvas")
        finally:
            release_b.set()
            results["b_turn"] = {"event": await b_task}

    agent_a._client = FakeClient(turn_a)  # type: ignore[assignment]
    agent_b._client = FakeClient(turn_b)  # type: ignore[assignment]

    with (
        patch("code_monet.agent._process_turn_messages", _fake_process),
        patch("code_monet.agent.run_painting_program", _fake_paint),
        patch("code_monet.agent.image_to_jpeg_bytes", lambda img: img),
        patch("code_monet.tools.critique._run_critique", _fake_critique),
    ):
        try:
            event = await anext(agent_a.run_turn())
        finally:
            await caller_a.close()
            await caller_b.close()

    assert isinstance(event, AgentTurnComplete)
    assert isinstance(results["b_turn"]["event"], AgentTurnComplete)

    # paint ran A's program, not the one B's turn registered last
    assert "ran program of A" in _text(results["paint"])

    # draw_paths wrote into A's workspace and A's animation queue only
    assert not results["draw"].get("isError"), _text(results["draw"])
    assert state_a.added and state_a.added[0].points[0].x == 700
    assert state_b.added == []
    assert agent_a._collected_paths and agent_b._collected_paths == []

    # view_canvas / critique saw A's canvas
    assert _image(results["view"]) == b"canvas-A"
    assert "canvas was canvas-A" in _text(results["critique_a"])
    assert "canvas was canvas-B" in _text(results["critique_b"])

    # B's failed critique must not block A's finish gate, nor A's pass open B's
    assert not results["name_a"].get("isError"), _text(results["name_a"])
    assert results["name_b"].get("isError"), _text(results["name_b"])

    # sign_canvas used A's canvas size (bottom-right of 800x600, not 400x300)
    assert not results["sign_a"].get("isError"), _text(results["sign_a"])
    signature = state_a.added[1:]
    assert signature and state_b.added == []
    coords = [float(n) for p in signature for n in re.findall(r"[-+]?\d*\.?\d+", p.d or "")]
    assert coords and min(coords) > 400


@pytest.mark.asyncio
async def test_openai_backend_overlapping_turns_keep_tool_calls_on_their_own_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The OpenAI backend dispatches handlers directly; they must get its own context."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    state_a = FakeState(name="A", canvas=FakeCanvas(800, 600), workspace_dir="/workspaces/A")
    state_b = FakeState(name="B", canvas=FakeCanvas(400, 300), workspace_dir="/workspaces/B")
    agent_a = OpenAIDrawingAgent(state_a)
    agent_b = OpenAIDrawingAgent(state_b)
    for agent in (agent_a, agent_b):
        await agent.resume()
        agent._build_input = AsyncMock(return_value=[])  # type: ignore[method-assign]
        agent._build_canvas_feedback_input = AsyncMock(return_value=[])  # type: ignore[method-assign]

    line = '{"paths":[{"type":"line","points":[{"x":700,"y":500},{"x":790,"y":590}]}]}'
    draw_call = SimpleNamespace(
        type="function_call", call_id="call_1", name="draw_paths", arguments=line
    )
    responses_a = iter(
        [
            SimpleNamespace(id="a1", output_text="", output=[draw_call]),
            SimpleNamespace(id="a2", output_text="", output=[]),
        ]
    )

    async def create_a(**_request: Any) -> SimpleNamespace:
        # User B's whole turn (and its tool binding) happens while A awaits the model.
        [_ async for _ in agent_b.run_turn()]
        return next(responses_a)

    async def create_b(**_request: Any) -> SimpleNamespace:
        return SimpleNamespace(id="b1", output_text="", output=[])

    agent_a._client = cast(Any, SimpleNamespace(responses=SimpleNamespace(create=create_a)))
    agent_b._client = cast(Any, SimpleNamespace(responses=SimpleNamespace(create=create_b)))

    [_ async for _ in agent_a.run_turn()]

    assert len(state_a.added) == 1
    assert state_a.added[0].points[0].x == 700
    assert state_b.added == []
