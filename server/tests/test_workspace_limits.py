"""Tests for workspace size and rate limits."""

from pathlib import Path as FilePath

import pytest

from code_monet.types import Path, PathType, Point
from code_monet.workspace import WorkspaceState


@pytest.fixture
async def workspace(tmp_path: FilePath) -> WorkspaceState:
    """Create a workspace state with a temp directory."""
    user_dir = tmp_path / "1"
    user_dir.mkdir(parents=True)
    (user_dir / "gallery").mkdir()

    state = WorkspaceState(user_id="1", user_dir=user_dir)
    state._loaded = True
    return state


class TestPendingStrokesLimit:
    """Test pending strokes queue limits."""

    @pytest.mark.asyncio
    async def test_queue_strokes_under_limit(self, workspace: WorkspaceState) -> None:
        """Strokes under limit should be queued normally."""
        path = Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])

        batch_id, total_points = await workspace.queue_strokes([path])

        assert batch_id == 1
        assert total_points > 0
        assert len(workspace._pending_strokes) == 1
        assert workspace._pending_strokes[0]["batch_id"] == 1

    @pytest.mark.asyncio
    async def test_queue_strokes_multiple_batches(self, workspace: WorkspaceState) -> None:
        """Multiple batches should have incrementing IDs."""
        path = Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])

        batch1, _ = await workspace.queue_strokes([path])
        batch2, _ = await workspace.queue_strokes([path])
        batch3, _ = await workspace.queue_strokes([path])

        assert batch1 == 1
        assert batch2 == 2
        assert batch3 == 3
        assert len(workspace._pending_strokes) == 3

    @pytest.mark.asyncio
    async def test_pop_strokes_clears_queue(self, workspace: WorkspaceState) -> None:
        """Pop should return strokes and clear the queue."""
        path = Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])

        await workspace.queue_strokes([path])
        await workspace.queue_strokes([path])

        strokes = await workspace.pop_strokes()

        assert len(strokes) == 2
        assert len(workspace._pending_strokes) == 0

    @pytest.mark.asyncio
    async def test_pop_strokes_returns_correct_structure(self, workspace: WorkspaceState) -> None:
        """Popped strokes should have correct TypedDict structure."""
        path = Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])

        await workspace.queue_strokes([path])
        strokes = await workspace.pop_strokes()

        stroke = strokes[0]
        assert "batch_id" in stroke
        assert "path" in stroke
        assert "points" in stroke
        assert isinstance(stroke["batch_id"], int)
        assert isinstance(stroke["path"], dict)
        assert isinstance(stroke["points"], list)


class TestWorkspaceSizeLimits:
    """Test workspace file size limits."""

    @pytest.mark.asyncio
    async def test_save_small_workspace(self, workspace: WorkspaceState) -> None:
        """Small workspace should save without truncation."""
        path = Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])
        workspace._canvas.strokes.append(path)

        await workspace.save()

        # Should still have the stroke
        assert len(workspace._canvas.strokes) == 1

    @pytest.mark.asyncio
    async def test_canvas_operations_thread_safe(self, workspace: WorkspaceState) -> None:
        """Canvas operations should use stroke lock."""
        import asyncio

        path = Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])

        # Run multiple operations concurrently
        async def add_strokes():
            for _ in range(10):
                await workspace.add_stroke(path)
                await asyncio.sleep(0.001)

        await asyncio.gather(add_strokes(), add_strokes())

        # Should have 20 strokes (no race conditions)
        assert len(workspace._canvas.strokes) == 20

    @pytest.mark.asyncio
    async def test_clear_canvas_thread_safe(self, workspace: WorkspaceState) -> None:
        """Clear canvas should use stroke lock."""
        path = Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])

        for _ in range(10):
            workspace._canvas.strokes.append(path)

        await workspace.clear_canvas()

        assert len(workspace._canvas.strokes) == 0


class TestGalleryIndex:
    """Test gallery index operations."""

    @pytest.mark.asyncio
    async def test_gallery_starts_empty(self, workspace: WorkspaceState) -> None:
        """New workspace should have empty gallery."""
        gallery = await workspace.list_gallery()
        assert len(gallery) == 0

    @pytest.mark.asyncio
    async def test_new_canvas_updates_gallery_index(self, workspace: WorkspaceState) -> None:
        """Saving a canvas should update the gallery index."""
        path = Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])
        workspace._canvas.strokes.append(path)

        # Ensure we start with piece_number > 0 to avoid race with rebuild
        workspace._piece_number = 1

        saved_id = await workspace.new_canvas()

        assert saved_id is not None
        assert saved_id == "piece_000001"
        gallery = await workspace.list_gallery()
        # Filter to only our saved piece (in case of any fixture issues)
        our_pieces = [g for g in gallery if g.id == saved_id]
        assert len(our_pieces) == 1

    @pytest.mark.asyncio
    async def test_gallery_index_persists(
        self, workspace: WorkspaceState, tmp_path: FilePath
    ) -> None:
        """Gallery index should persist across workspace reloads."""
        path = Path(type=PathType.LINE, points=[Point(x=0, y=0), Point(x=100, y=100)])
        workspace._canvas.strokes.append(path)

        # Use a unique piece number
        workspace._piece_number = 5

        saved_id = await workspace.new_canvas()

        # Create new workspace instance
        workspace2 = WorkspaceState(user_id="1", user_dir=tmp_path / "1")
        await workspace2._load_from_file()

        gallery = await workspace2.list_gallery()
        # Should have exactly one piece matching our saved ID
        matching = [g for g in gallery if g.id == saved_id]
        assert len(matching) == 1
