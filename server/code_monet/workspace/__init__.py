"""Filesystem-backed workspace state for multi-user isolation.

This package provides per-user workspace management with:
- Atomic file persistence
- Gallery management
- Stroke queue for client-side rendering
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path as FilePath
from typing import TYPE_CHECKING

import aiofiles
import aiofiles.os

from code_monet.types import (
    AgentStatus,
    CanvasState,
    DrawingStyleType,
    GalleryEntry,
    Path,
    PauseReason,
    PendingStrokeDict,
    SavedCanvas,
)
from code_monet.workspace.gallery import (
    load_gallery_piece,
    parse_drawing_style,
    scan_gallery_entries,
    scan_gallery_with_strokes,
)
from code_monet.workspace.persistence import (
    atomic_write,
    ensure_user_dirs,
    get_user_dir,
)
from code_monet.workspace.strokes import (
    enforce_pending_limit,
    interpolate_paths_to_pending,
)

if TYPE_CHECKING:
    from code_monet.config import Settings

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility
__all__ = ["WorkspaceState"]


class WorkspaceState:
    """Per-user workspace state backed by the filesystem.

    Each user has their own directory under workspace_base_dir:
        users/{user_id}/
            workspace.json      - Current canvas state and agent metadata
            gallery/
                piece_001.json  - Saved artwork
                piece_002.json
    """

    def __init__(self, user_id: str, user_dir: FilePath) -> None:
        self.user_id = user_id
        self._user_dir = user_dir
        self._workspace_file = user_dir / "workspace.json"
        self._gallery_dir = user_dir / "gallery"
        self._write_lock = asyncio.Lock()
        self._stroke_lock = asyncio.Lock()  # Protects stroke/canvas modifications

        # In-memory state
        self._canvas: CanvasState = CanvasState()
        self._status: AgentStatus = AgentStatus.PAUSED
        self._pause_reason: PauseReason = PauseReason.NONE
        self._piece_number: int = 0
        self._notes: str = ""
        self._monologue: str = ""
        self._current_piece_title: str | None = None  # Title for current piece
        self._loaded = False

        # Pending strokes for client-side rendering
        self._pending_strokes: list[PendingStrokeDict] = []
        self._stroke_batch_id: int = 0

        # Save debouncing - coalesce rapid saves
        self._save_pending: bool = False
        self._save_task: asyncio.Task[None] | None = None

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def workspace_dir(self) -> str:
        """Return the user's workspace directory path as string."""
        return str(self._user_dir)

    @classmethod
    async def load_for_user(cls, user_id: str) -> WorkspaceState:
        """Load or create workspace state for a user."""
        user_dir = get_user_dir(user_id)
        await ensure_user_dirs(user_dir)

        state = cls(user_id, user_dir)
        await state._load_from_file()
        return state

    async def _load_from_file(self) -> None:
        """Load state from workspace.json."""
        if await aiofiles.os.path.exists(self._workspace_file):
            try:
                async with aiofiles.open(self._workspace_file) as f:
                    data = json.loads(await f.read())
            except json.JSONDecodeError as e:
                logger.error(
                    f"Corrupted workspace.json for user {self.user_id}: {e}. "
                    "Starting with fresh state."
                )
                # Backup corrupted file for debugging
                backup_file = self._workspace_file.with_suffix(".json.corrupted")
                await aiofiles.os.rename(self._workspace_file, backup_file)
                self._loaded = True
                return

            canvas_data = data.get("canvas", {})
            self._canvas = CanvasState(
                width=canvas_data.get("width", 800),
                height=canvas_data.get("height", 600),
                strokes=[Path.model_validate(s) for s in canvas_data.get("strokes", [])],
                drawing_style=parse_drawing_style(canvas_data.get("drawing_style", "plotter")),
            )
            self._status = AgentStatus(data.get("status", "paused"))
            # Load pause_reason, default to NONE for backwards compatibility
            pause_reason_str = data.get("pause_reason", "none")
            try:
                self._pause_reason = PauseReason(pause_reason_str)
            except ValueError:
                self._pause_reason = PauseReason.NONE
            self._piece_number = data.get("piece_number", 0)
            self._notes = data.get("notes", "")
            self._monologue = data.get("monologue", "")
            self._current_piece_title = data.get("current_piece_title")
            self._pending_strokes = data.get("pending_strokes", [])
            self._stroke_batch_id = data.get("stroke_batch_id", 0)

            logger.info(
                f"Workspace loaded for user {self.user_id}: "
                f"piece {self._piece_number}, {len(self._canvas.strokes)} strokes"
            )
        else:
            logger.info(f"New workspace created for user {self.user_id}")

        self._loaded = True

    async def save(self, debounce_ms: int = 0) -> None:
        """Save state to filesystem atomically.

        Args:
            debounce_ms: If > 0, debounce saves by this many milliseconds.
                         Multiple calls within the window will be coalesced.

        Enforces max_workspace_size_bytes limit to prevent disk exhaustion.
        """
        from code_monet.config import settings as app_settings

        if debounce_ms > 0:
            # Debounced save - schedule and return immediately
            self._save_pending = True
            if self._save_task is None or self._save_task.done():
                self._save_task = asyncio.create_task(self._debounced_save(debounce_ms))
            return

        await self._do_save(app_settings)

    async def _debounced_save(self, debounce_ms: int) -> None:
        """Wait for debounce period then save if still pending."""
        from code_monet.config import settings as app_settings

        await asyncio.sleep(debounce_ms / 1000.0)
        if self._save_pending:
            self._save_pending = False
            await self._do_save(app_settings)

    async def _do_save(self, app_settings: Settings) -> None:
        """Actually perform the save."""
        async with self._write_lock:
            data = {
                "canvas": self._canvas.model_dump(),
                "status": self._status.value,
                "pause_reason": self._pause_reason.value,
                "piece_number": self._piece_number,
                "notes": self._notes,
                "monologue": self._monologue,
                "current_piece_title": self._current_piece_title,
                "pending_strokes": self._pending_strokes,
                "stroke_batch_id": self._stroke_batch_id,
                "updated_at": datetime.now(UTC).isoformat(),
            }

            # Serialize and check size
            json_data = json.dumps(data, indent=2)
            if len(json_data) > app_settings.max_workspace_size_bytes:
                logger.warning(
                    f"User {self.user_id}: workspace size ({len(json_data)} bytes) "
                    f"exceeds limit ({app_settings.max_workspace_size_bytes} bytes), "
                    "truncating old strokes"
                )
                # Remove oldest strokes until under limit
                while (
                    len(json_data) > app_settings.max_workspace_size_bytes
                    and len(self._canvas.strokes) > 10
                ):
                    self._canvas.strokes = self._canvas.strokes[10:]
                    data["canvas"] = self._canvas.model_dump()
                    json_data = json.dumps(data, indent=2)

            await atomic_write(self._workspace_file, json_data)

    # --- Properties ---

    @property
    def canvas(self) -> CanvasState:
        return self._canvas

    @property
    def status(self) -> AgentStatus:
        return self._status

    @status.setter
    def status(self, value: AgentStatus) -> None:
        self._status = value

    @property
    def pause_reason(self) -> PauseReason:
        return self._pause_reason

    @pause_reason.setter
    def pause_reason(self, value: PauseReason) -> None:
        self._pause_reason = value

    @property
    def piece_number(self) -> int:
        return self._piece_number

    @piece_number.setter
    def piece_number(self, value: int) -> None:
        self._piece_number = value

    @property
    def notes(self) -> str:
        return self._notes

    @notes.setter
    def notes(self, value: str) -> None:
        self._notes = value

    @property
    def monologue(self) -> str:
        return self._monologue

    @monologue.setter
    def monologue(self, value: str) -> None:
        self._monologue = value

    @property
    def current_piece_title(self) -> str | None:
        return self._current_piece_title

    @current_piece_title.setter
    def current_piece_title(self, value: str | None) -> None:
        self._current_piece_title = value

    @property
    def has_pending_strokes(self) -> bool:
        """Check if there are pending strokes to render."""
        return len(self._pending_strokes) > 0

    @property
    def pending_stroke_count(self) -> int:
        """Number of pending strokes."""
        return len(self._pending_strokes)

    @property
    def stroke_batch_id(self) -> int:
        """Current stroke batch ID."""
        return self._stroke_batch_id

    # --- Stroke Queue Operations ---

    async def queue_strokes(self, paths: list[Path]) -> tuple[int, int]:
        """Interpolate paths and queue for client-side rendering.

        Returns (batch_id, total_point_count) for this set of strokes.
        Thread-safe: uses stroke lock to prevent race conditions.
        Enforces max_pending_strokes limit to prevent memory exhaustion.
        """
        from code_monet.config import settings

        async with self._stroke_lock:
            # Check pending strokes limit
            self._pending_strokes = enforce_pending_limit(
                self._pending_strokes,
                len(paths),
                settings.max_pending_strokes,
                self.user_id,
            )

            self._stroke_batch_id += 1
            batch_id = self._stroke_batch_id

            new_strokes, total_points = interpolate_paths_to_pending(
                paths, batch_id, settings.path_steps_per_unit
            )
            self._pending_strokes.extend(new_strokes)

        await self.save()
        return batch_id, total_points

    async def pop_strokes(self) -> list[PendingStrokeDict]:
        """Get and clear pending strokes.

        Thread-safe: uses stroke lock to prevent race conditions.
        """
        async with self._stroke_lock:
            strokes = self._pending_strokes.copy()
            self._pending_strokes.clear()
        await self.save()
        return strokes

    # --- Canvas Operations ---

    async def add_stroke(self, path: Path) -> None:
        """Add a stroke to the canvas.

        Thread-safe: uses stroke lock to prevent race conditions.
        """
        async with self._stroke_lock:
            self._canvas.strokes.append(path)
        await self.save()

    async def clear_canvas(self) -> None:
        """Clear the canvas.

        Thread-safe: uses stroke lock to prevent race conditions.
        """
        async with self._stroke_lock:
            self._canvas.strokes = []
        await self.save()

    async def save_to_gallery(self) -> str | None:
        """Save current canvas to gallery without clearing. Returns saved ID."""
        async with self._write_lock:
            if not self._canvas.strokes:
                return None

            # Save to gallery as JSON file (use 6 digits for scalability)
            piece_file = self._gallery_dir / f"piece_{self._piece_number:06d}.json"
            created_at = datetime.now(UTC).isoformat()
            piece_data = {
                "piece_number": self._piece_number,
                "width": self._canvas.width,
                "height": self._canvas.height,
                "strokes": [s.model_dump() for s in self._canvas.strokes],
                "created_at": created_at,
                "drawing_style": self._canvas.drawing_style.value,
                "title": self._current_piece_title,
            }

            await atomic_write(piece_file, json.dumps(piece_data, indent=2))

            saved_id = f"piece_{self._piece_number:06d}"
            title_info = (
                f' titled "{self._current_piece_title}"' if self._current_piece_title else ""
            )
            logger.info(f"Saved piece {self._piece_number}{title_info} to gallery as {saved_id}")

        await self.save()
        return saved_id

    async def new_canvas(self, *, width: int = 800, height: int = 600) -> str | None:
        """Save current canvas to gallery and start fresh. Returns saved ID."""
        # First save to gallery
        saved_id = await self.save_to_gallery()

        # Then clear for new canvas
        async with self._write_lock:
            self._canvas.width = width
            self._canvas.height = height
            self._canvas.strokes = []
            self._piece_number += 1
            self._monologue = ""  # Clear thinking for new piece
            self._notes = ""  # Clear notes for new piece
            self._current_piece_title = None  # Clear title for new piece

        # Clear pending strokes from previous canvas to prevent them
        # from being rendered on the new canvas
        async with self._stroke_lock:
            self._pending_strokes.clear()

        await self.save()
        return saved_id

    # --- Gallery Operations ---

    async def list_gallery(self) -> list[GalleryEntry]:
        """List gallery pieces by scanning piece files."""
        return await scan_gallery_entries(self._gallery_dir)

    async def list_gallery_with_strokes(self) -> list[SavedCanvas]:
        """List gallery pieces with full stroke data.

        This loads all strokes for each piece - use sparingly.
        For listings, prefer list_gallery() which returns metadata only.
        """
        return await scan_gallery_with_strokes(self._gallery_dir)

    async def load_from_gallery(
        self, piece_number: int
    ) -> tuple[list[Path], DrawingStyleType, int, int] | None:
        """Load strokes, drawing style, and dimensions from a gallery piece.

        Returns (strokes, drawing_style, width, height) tuple or None if not found.
        """
        return await load_gallery_piece(self._gallery_dir, piece_number)
