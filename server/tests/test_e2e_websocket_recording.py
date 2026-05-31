"""E2E tests that record WebSocket messages for app replay testing.

This module provides infrastructure to:
1. Record all WebSocket messages broadcast during an agent turn
2. Save them as JSON fixtures for deterministic app reducer testing
3. Validate message sequences without making API calls in CI

Usage:
    # Record a new fixture (requires API key)
    make test-record-fixture

    # Run with a specific fixture name
    pytest tests/test_e2e_websocket_recording.py -v -k test_record \
        --fixture-name my_custom_fixture

The recorded fixtures are saved to server/tests/fixtures/ and symlinked
to app/src/__tests__/fixtures/ for use in app reducer tests.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from code_monet.agent import DrawingAgent
from code_monet.orchestrator import AgentOrchestrator
from code_monet.types import DrawingStyleType
from code_monet.workspace import WorkspaceState


@dataclass
class MessageCapture:
    """Captures broadcast messages with timing info."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    start_time_ms: int = 0

    def start(self) -> None:
        """Mark the start time for relative timestamps."""
        self.start_time_ms = int(time.time() * 1000)

    async def capture(self, message: BaseModel | dict[str, Any]) -> None:
        """Capture a message with relative timestamp."""
        if isinstance(message, BaseModel):
            data = message.model_dump()
            msg_type = data.get("type", message.__class__.__name__.lower())
        else:
            data = message
            msg_type = data.get("type", "unknown")

        elapsed_ms = int(time.time() * 1000) - self.start_time_ms

        self.messages.append(
            {
                "type": msg_type,
                "data": data,
                "timestamp_ms": elapsed_ms,
            }
        )

    def to_fixture(
        self,
        model: str = "claude-3-5-haiku-latest",
        style: str = "plotter",
        description: str = "",
    ) -> dict[str, Any]:
        """Convert captured messages to fixture format."""
        from datetime import datetime

        return {
            "metadata": {
                "model": model,
                "style": style,
                "recorded_at": datetime.now(UTC).isoformat(),
                "description": description,
                "message_count": len(self.messages),
            },
            "messages": self.messages,
        }


# Mark all tests as e2e (excluded from default pytest run, use -m e2e to include)
pytestmark = pytest.mark.e2e


@pytest.fixture
async def workspace(tmp_path: Path) -> WorkspaceState:
    """Create a minimal workspace for testing."""
    user_dir = tmp_path / "1"
    user_dir.mkdir(parents=True)
    (user_dir / "gallery").mkdir()

    state = WorkspaceState(user_id="1", user_dir=user_dir)
    state._loaded = True
    return state


@pytest.fixture
def use_haiku(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use haiku for faster/cheaper tests."""
    monkeypatch.setattr(
        "code_monet.config.settings.agent_model",
        "claude-3-5-haiku-latest",
    )


@pytest.fixture
def fixture_dir() -> Path:
    """Get the fixtures directory, creating if needed."""
    fixtures = Path(__file__).parent / "fixtures"
    fixtures.mkdir(exist_ok=True)
    return fixtures


class TestMessageRecording:
    """Tests that record WebSocket messages for app replay."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(240)
    @pytest.mark.usefixtures("use_haiku")
    async def test_record_agent_turn_plotter(
        self,
        workspace: WorkspaceState,
        fixture_dir: Path,
    ) -> None:
        """Record all messages broadcast during a plotter-style agent turn.

        This test captures the full message sequence that the app reducer
        needs to process. The fixture is saved for deterministic replay tests.
        """
        workspace.canvas.drawing_style = DrawingStyleType.PLOTTER

        capture = MessageCapture()

        # Create broadcaster mock that captures messages
        broadcaster = MagicMock()
        broadcaster.broadcast = AsyncMock(side_effect=capture.capture)
        broadcaster.active_connections = [MagicMock()]  # Fake connected client

        agent = DrawingAgent(state=workspace)
        await agent.resume()

        orchestrator = AgentOrchestrator(agent=agent, broadcaster=broadcaster)

        # Start timing and run turn
        capture.start()
        done = await orchestrator.run_turn()

        # Verify we captured messages
        assert len(capture.messages) > 0, "Expected to capture at least one message"

        # Build fixture
        fixture = capture.to_fixture(
            model="claude-3-5-haiku-latest",
            style="plotter",
            description="Agent turn with plotter style, simple diagonal line",
        )

        # Save fixture
        fixture_path = fixture_dir / "agent_turn_plotter.json"
        fixture_path.write_text(json.dumps(fixture, indent=2))

        # Log results for visibility
        print(f"\nRecorded {len(capture.messages)} messages to {fixture_path}")
        print(f"Turn complete (piece done: {done})")
        for i, msg in enumerate(capture.messages[:5]):
            print(f"  [{i}] {msg['type']} @ {msg['timestamp_ms']}ms")
        if len(capture.messages) > 5:
            print(f"  ... and {len(capture.messages) - 5} more")

    @pytest.mark.asyncio
    @pytest.mark.timeout(240)
    @pytest.mark.usefixtures("use_haiku")
    async def test_record_agent_turn_paint(
        self,
        workspace: WorkspaceState,
        fixture_dir: Path,
    ) -> None:
        """Record all messages broadcast during a paint-style agent turn."""
        workspace.canvas.drawing_style = DrawingStyleType.PAINT

        capture = MessageCapture()

        broadcaster = MagicMock()
        broadcaster.broadcast = AsyncMock(side_effect=capture.capture)
        broadcaster.active_connections = [MagicMock()]

        agent = DrawingAgent(state=workspace)
        await agent.resume()

        orchestrator = AgentOrchestrator(agent=agent, broadcaster=broadcaster)

        capture.start()
        done = await orchestrator.run_turn()

        assert len(capture.messages) > 0

        fixture = capture.to_fixture(
            model="claude-3-5-haiku-latest",
            style="paint",
            description="Agent turn with paint style",
        )

        fixture_path = fixture_dir / "agent_turn_paint.json"
        fixture_path.write_text(json.dumps(fixture, indent=2))

        print(f"\nRecorded {len(capture.messages)} messages to {fixture_path}")
        print(f"Turn complete (piece done: {done})")


class TestFixtureValidation:
    """Validate existing fixtures without API calls."""

    def test_fixture_structure_plotter(self, fixture_dir: Path) -> None:
        """Validate the plotter fixture has correct structure."""
        fixture_path = fixture_dir / "agent_turn_plotter.json"

        if not fixture_path.exists():
            pytest.skip("Fixture not yet recorded - run test_record_agent_turn_plotter first")

        fixture = json.loads(fixture_path.read_text())

        # Validate structure
        assert "metadata" in fixture
        assert "messages" in fixture
        assert isinstance(fixture["messages"], list)

        metadata = fixture["metadata"]
        assert "model" in metadata
        assert "style" in metadata
        assert metadata["style"] == "plotter"
        assert "recorded_at" in metadata

        # Validate message structure
        for msg in fixture["messages"]:
            assert "type" in msg
            assert "data" in msg
            assert "timestamp_ms" in msg
            assert isinstance(msg["timestamp_ms"], int)

    def test_fixture_message_sequence(self, fixture_dir: Path) -> None:
        """Validate the message sequence is reasonable."""
        fixture_path = fixture_dir / "agent_turn_plotter.json"

        if not fixture_path.exists():
            pytest.skip("Fixture not yet recorded")

        fixture = json.loads(fixture_path.read_text())
        messages = fixture["messages"]

        # Should have at least iteration + some other messages
        assert len(messages) >= 2, f"Expected at least 2 messages, got {len(messages)}"

        # Timestamps should be monotonically increasing
        timestamps = [m["timestamp_ms"] for m in messages]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1], (
                f"Timestamps not monotonic: {timestamps[i - 1]} > {timestamps[i]}"
            )

        # Extract message types
        types = [m["type"] for m in messages]

        # Should have an iteration message
        assert "iteration" in types, "Expected at least one iteration message"
