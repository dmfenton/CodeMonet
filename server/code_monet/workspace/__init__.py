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
import uuid
from datetime import UTC, datetime
from pathlib import Path as FilePath
from typing import TYPE_CHECKING, Any

import aiofiles
import aiofiles.os

from code_monet.rendering import RenderOptions, render_strokes_async
from code_monet.types import (
    AgentStatus,
    CanvasState,
    DrawingStyleType,
    GalleryEntry,
    PaintingVersion,
    Path,
    PauseReason,
    PendingStrokeDict,
    SavedCanvas,
)
from code_monet.workspace.gallery import (
    gallery_version_record,
    load_gallery_piece,
    parse_drawing_style,
    read_gallery_piece_json,
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
        self._current_piece_prompt: str | None = None  # User's direction for current piece
        # Every rendered version of the current program painting, oldest first (paint mode)
        self._painting_versions: list[PaintingVersion] = []
        # Bumped whenever the painting resets, so stale paint runs can be discarded
        self._painting_generation: int = 0
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
            self._current_piece_prompt = data.get("current_piece_prompt")
            self._painting_versions = _load_painting_versions(data, self.user_id)

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
                "current_piece_prompt": self._current_piece_prompt,
                "pending_strokes": self._pending_strokes,
                "stroke_batch_id": self._stroke_batch_id,
                "painting_versions": [v.model_dump() for v in self._painting_versions],
                # Latest version under the legacy key, so an older server can still load it
                "painting": self.painting.model_dump() if self.painting else None,
                "updated_at": datetime.now(UTC).isoformat(),
            }

            # Never drop strokes to fit a size budget: that silently erases the
            # painting (and re-serializing per drop blocked the event loop).
            json_data = json.dumps(data)
            if len(json_data) > app_settings.max_workspace_size_bytes:
                logger.warning(
                    f"User {self.user_id}: workspace size ({len(json_data)} bytes) "
                    f"exceeds {app_settings.max_workspace_size_bytes} bytes"
                )

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
    def current_piece_prompt(self) -> str | None:
        """The user's direction for the current piece (from new_canvas), if any."""
        return self._current_piece_prompt

    @property
    def painting(self) -> PaintingVersion | None:
        """Latest rendered version of the current program painting."""
        return self._painting_versions[-1] if self._painting_versions else None

    @property
    def painting_versions(self) -> list[PaintingVersion]:
        """Every rendered version of the current program painting, oldest first."""
        return list(self._painting_versions)

    @property
    def painting_generation(self) -> int:
        """Changes whenever the painting resets (new canvas, clear)."""
        return self._painting_generation

    @property
    def paintings_dir(self) -> FilePath:
        """Directory holding rendered painting versions, one subdirectory per token."""
        return self._user_dir / "paintings"

    @property
    def studio_program(self) -> FilePath:
        """The agent's current painting program."""
        return self._user_dir / "studio" / "painting.py"

    async def record_painting_version(
        self,
        token: str,
        image_width: int,
        image_height: int,
        stages: list[str],
        *,
        ops: int,
        generation: int,
    ) -> PaintingVersion | None:
        """Make a rendered version the current picture of this piece.

        `generation` is `painting_generation` captured when the run started;
        if the painting was reset since, the result belongs to no piece and
        nothing is recorded (returns None).
        """
        if generation != self._painting_generation:
            return None
        latest = self.painting
        version = PaintingVersion(
            piece_number=self._piece_number,
            version=(latest.version + 1) if latest else 1,
            token=token,
            image_width=image_width,
            image_height=image_height,
            stages=stages,
            ops=ops,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._painting_versions.append(version)
        await self.save()
        return version

    def _reset_painting(self) -> None:
        """Forget the current painting; the next program starts from scratch."""
        self._painting_versions = []
        self._painting_generation += 1
        self.studio_program.unlink(missing_ok=True)

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

    async def add_strokes(self, paths: list[Path]) -> None:
        """Append a batch of strokes and persist once.

        A save serializes the whole canvas, so saving per stroke makes a batch
        cost O(batch x canvas) and blocks the event loop for minutes on dense
        paintings. Thread-safe: uses stroke lock to prevent race conditions.
        """
        if not paths:
            return
        async with self._stroke_lock:
            self._canvas.strokes.extend(paths)
        await self.save()

    async def clear_canvas(self) -> None:
        """Clear the canvas.

        Thread-safe: uses stroke lock to prevent race conditions.
        """
        self._painting_generation += 1  # before any await; see new_canvas
        async with self._stroke_lock:
            self._canvas.strokes = []
            self._reset_painting()
            self._current_piece_prompt = None
        await self.save()

    async def save_to_gallery(self) -> str | None:
        """Save current canvas to gallery without clearing. Returns saved ID."""
        async with self._write_lock:
            painting = self.painting
            if not self._canvas.strokes and painting is None:
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
                "prompt": self._current_piece_prompt,
            }
            if painting is not None:
                piece_data["format"] = "raster"
                piece_data["image_token"] = painting.token
                piece_data["image_width"] = painting.image_width
                piece_data["image_height"] = painting.image_height
                piece_data["versions"] = [
                    gallery_version_record(v) for v in self._painting_versions
                ]

            await atomic_write(piece_file, json.dumps(piece_data, indent=2))

            piece_number = self._piece_number
            saved_id = f"piece_{piece_number:06d}"
            title_info = (
                f' titled "{self._current_piece_title}"' if self._current_piece_title else ""
            )
            logger.info(f"Saved piece {self._piece_number}{title_info} to gallery as {saved_id}")

        # The gallery is read far more often than pieces are saved. Render once
        # here so opening it never queues a full canvas render for every tile.
        try:
            await self.gallery_thumbnail(piece_number)
        except (OSError, ValueError) as exc:
            logger.warning("Could not prepare gallery thumbnail for %s: %s", saved_id, exc)

        await self.save()
        return saved_id

    async def new_canvas(
        self, *, width: int = 800, height: int = 600, prompt: str | None = None
    ) -> str | None:
        """Save current canvas to gallery and start fresh. Returns saved ID.

        `prompt` is the user's direction for the new piece; it is recorded after
        the previous piece is saved so it never lands on that piece.
        """
        # Invalidate in-flight paint runs before the first await: a run that
        # finishes during the gallery save must not join a piece being retired.
        self._painting_generation += 1
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
            self._current_piece_prompt = prompt
            self._reset_painting()

        # Clear pending strokes from previous canvas to prevent them
        # from being rendered on the new canvas
        async with self._stroke_lock:
            self._pending_strokes.clear()

        await self.save()
        return saved_id

    # --- Gallery Operations ---

    async def gallery_piece_data(self, piece_number: int) -> dict[str, Any] | None:
        """Raw gallery piece JSON, or None if missing/corrupt."""
        return await read_gallery_piece_json(self._gallery_dir, piece_number)

    async def gallery_raster(self, piece_number: int) -> tuple[str, str] | None:
        """(image_token, final image path) for a raster gallery piece, else None."""
        data = await self.gallery_piece_data(piece_number)
        return self.raster_final(data) if data else None

    async def gallery_thumbnail(self, piece_number: int) -> bytes | None:
        """Return a small persisted thumbnail, creating it for older pieces on demand."""
        data_path = self._gallery_dir / f"piece_{piece_number:06d}.json"
        if not await aiofiles.os.path.exists(data_path):
            data_path = self._gallery_dir / f"piece_{piece_number:03d}.json"
        if not await aiofiles.os.path.exists(data_path):
            return None
        thumbnail_path = self._gallery_dir / f"piece_{piece_number:06d}.thumb.png"
        if await aiofiles.os.path.exists(thumbnail_path):
            thumbnail_stat, data_stat = await asyncio.gather(
                aiofiles.os.stat(thumbnail_path), aiofiles.os.stat(data_path)
            )
            if thumbnail_stat.st_mtime_ns >= data_stat.st_mtime_ns:
                async with aiofiles.open(thumbnail_path, "rb") as thumbnail_file:
                    return await thumbnail_file.read()

        data = await self.gallery_piece_data(piece_number)
        if data is None:
            return None
        from code_monet.workspace.gallery import parse_gallery_piece

        strokes, style, width, height = parse_gallery_piece(data)
        if width <= 0 or height <= 0:
            return None
        raster = self.raster_final(data)
        if not strokes and raster is None:
            return None

        target_width = min(width, 640)
        target_height = max(1, round(height * target_width / width))
        result = await render_strokes_async(
            strokes,
            RenderOptions(
                width=target_width,
                height=target_height,
                drawing_style=style,
                scale_from=(width, height),
                base_image=raster[1] if raster else None,
            ),
        )
        assert isinstance(result, bytes)

        # A unique temporary name keeps simultaneous first requests for an old
        # piece from racing over the same temporary file.
        temporary_path = thumbnail_path.with_name(f"{thumbnail_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            async with aiofiles.open(temporary_path, "wb") as thumbnail_file:
                await thumbnail_file.write(result)
            await aiofiles.os.replace(temporary_path, thumbnail_path)
        finally:
            if await aiofiles.os.path.exists(temporary_path):
                await aiofiles.os.remove(temporary_path)
        return result

    def raster_final(self, data: dict[str, Any]) -> tuple[str, str] | None:
        """(image_token, final image path) for gallery piece JSON, if its image exists."""
        token = data.get("image_token")
        if not isinstance(token, str):
            return None
        path = self.paintings_dir / token / "final.png"
        return (token, str(path)) if path.exists() else None

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


def _load_painting_versions(data: dict[str, Any], user_id: str) -> list[PaintingVersion]:
    """Painting versions from workspace.json; older files stored only the latest.

    Malformed entries are skipped so one bad record cannot block loading.
    """
    versions = data.get("painting_versions")
    if versions is None:
        painting = data.get("painting")
        versions = [painting] if painting else []
    if not isinstance(versions, list):
        logger.warning(f"User {user_id}: ignoring malformed painting_versions in workspace.json")
        return []
    loaded: list[PaintingVersion] = []
    for entry in versions:
        try:
            loaded.append(PaintingVersion.model_validate(entry))
        except ValueError as e:
            logger.warning(f"User {user_id}: skipping malformed painting version: {e}")
    return loaded
