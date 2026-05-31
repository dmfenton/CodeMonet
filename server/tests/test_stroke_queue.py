"""Tests for pending stroke queue functionality."""

from pathlib import Path

import pytest

from code_monet.types import Path as DrawPath
from code_monet.types import PathType, Point
from code_monet.workspace import WorkspaceState


class TestWorkspaceStateStrokeQueue:
    """Tests for WorkspaceState pending stroke queue methods."""

    @pytest.fixture
    async def workspace_state(self, tmp_path: Path) -> WorkspaceState:
        """Create a test workspace state with temp directory."""
        user_dir = tmp_path / "test_user"
        user_dir.mkdir(parents=True)
        state = WorkspaceState(user_id="1", user_dir=user_dir)
        await state._load_from_file()  # Initialize state
        return state

    @pytest.mark.asyncio
    async def test_queue_strokes_empty(self, workspace_state: WorkspaceState) -> None:
        """Test that empty queue has correct initial state."""
        assert workspace_state.has_pending_strokes is False
        assert workspace_state.pending_stroke_count == 0
        assert workspace_state.stroke_batch_id == 0

    @pytest.mark.asyncio
    async def test_queue_strokes_single_path(self, workspace_state: WorkspaceState) -> None:
        """Test queueing a single path."""
        path = DrawPath(
            type=PathType.LINE,
            points=[Point(x=0, y=0), Point(x=100, y=100)],
        )

        batch_id, total_points = await workspace_state.queue_strokes([path])

        assert batch_id == 1
        assert total_points > 0  # Should have interpolated points
        assert workspace_state.has_pending_strokes is True
        assert workspace_state.pending_stroke_count == 1
        assert workspace_state.stroke_batch_id == 1

    @pytest.mark.asyncio
    async def test_queue_strokes_multiple_paths(self, workspace_state: WorkspaceState) -> None:
        """Test queueing multiple paths in one batch."""
        paths = [
            DrawPath(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)]),
            DrawPath(type=PathType.LINE, points=[Point(x=100, y=100), Point(x=200, y=0)]),
        ]

        batch_id, total_points = await workspace_state.queue_strokes(paths)

        assert batch_id == 1
        assert total_points > 0
        assert workspace_state.pending_stroke_count == 2

    @pytest.mark.asyncio
    async def test_queue_strokes_increments_batch_id(self, workspace_state: WorkspaceState) -> None:
        """Test that batch ID increments with each queue call."""
        path = DrawPath(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])

        batch1, _ = await workspace_state.queue_strokes([path])
        batch2, _ = await workspace_state.queue_strokes([path])

        assert batch1 == 1
        assert batch2 == 2
        assert workspace_state.pending_stroke_count == 2

    @pytest.mark.asyncio
    async def test_pop_strokes_clears_queue(self, workspace_state: WorkspaceState) -> None:
        """Test that pop_strokes returns and clears pending strokes."""
        path = DrawPath(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])
        await workspace_state.queue_strokes([path])

        strokes = await workspace_state.pop_strokes()

        assert len(strokes) == 1
        assert workspace_state.has_pending_strokes is False
        assert workspace_state.pending_stroke_count == 0

    @pytest.mark.asyncio
    async def test_pop_strokes_returns_interpolated_points(
        self, workspace_state: WorkspaceState
    ) -> None:
        """Test that popped strokes contain pre-interpolated points."""
        path = DrawPath(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])
        await workspace_state.queue_strokes([path])

        strokes = await workspace_state.pop_strokes()

        assert len(strokes) == 1
        stroke = strokes[0]
        assert "batch_id" in stroke
        assert "path" in stroke
        assert "points" in stroke
        # Points should be interpolated (more than original 2 points)
        assert len(stroke["points"]) > 2

    @pytest.mark.asyncio
    async def test_pop_strokes_empty_returns_empty(self, workspace_state: WorkspaceState) -> None:
        """Test that pop_strokes on empty queue returns empty list."""
        strokes = await workspace_state.pop_strokes()
        assert strokes == []

    @pytest.mark.asyncio
    async def test_strokes_persist_across_save_load(self, tmp_path: Path) -> None:
        """Test that pending strokes are persisted to disk."""
        user_dir = tmp_path / "persist_user"
        user_dir.mkdir(parents=True)

        # Create state and queue strokes
        state1 = WorkspaceState(user_id="1", user_dir=user_dir)
        await state1._load_from_file()
        path = DrawPath(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])
        await state1.queue_strokes([path])

        # Create new state instance and load from disk
        state2 = WorkspaceState(user_id="1", user_dir=user_dir)
        await state2._load_from_file()

        assert state2.has_pending_strokes is True
        assert state2.pending_stroke_count == 1
        assert state2.stroke_batch_id == 1
