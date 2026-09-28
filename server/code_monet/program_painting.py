"""Run the agent's painting program and publish the result as a painting version.

Paint mode is program painting: the agent keeps `studio/painting.py` in its
workspace, and each successful run renders a new version (keyframes, final
image, reveal log) under `paintings/{token}/`. See docs/program-painting.md.
"""

from __future__ import annotations

import asyncio
import errno
import json
import logging
import math
import os
import secrets
import shutil
import stat
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path as FilePath
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PositiveInt

from code_monet.paintlib.canvas import RevealSummary, reveal_summary
from code_monet.types import PaintingVersion
from code_monet.workspace import WorkspaceState

logger = logging.getLogger(__name__)

RENDER_SCALE = 2  # image pixels per logical canvas unit
PAINT_TIMEOUT_S = 240
_ERROR_TAIL_CHARS = 3000


@dataclass(frozen=True)
class PaintSuccess:
    version: PaintingVersion
    preview_jpeg: bytes
    seconds: float


@dataclass(frozen=True)
class PaintFailure:
    error: str
    seconds: float


PaintResult = PaintSuccess | PaintFailure


@dataclass(frozen=True)
class LiveStarted:
    """A paint run began streaming its performance into this version's directory."""

    piece_number: int
    token: str
    image_width: int
    image_height: int


@dataclass(frozen=True)
class LiveFailed:
    """The run streaming into `token` failed; its version was discarded."""

    piece_number: int
    token: str


PaintLive = LiveStarted | LiveFailed
OnLive = Callable[[PaintLive], Awaitable[None]]


@dataclass(frozen=True)
class _Exported:
    """A run's checked output: what the version records and what the agent sees."""

    summary: RevealSummary
    preview_jpeg: bytes
    continues: bool


def _check_reveal_op(op: list[object]) -> list[object]:
    """A reveal op as the clients decode it (parseRevealOp, MonetKit RevealOp).

    ["s", width > 0, x, y, ...more points] or ["a", x0, y0, x1, y1].
    """
    if not op:
        raise ValueError("empty reveal op")
    tag = op[0]
    nums = [
        n
        for n in op[1:]
        if isinstance(n, int | float) and not isinstance(n, bool) and math.isfinite(n)
    ]
    if len(nums) != len(op) - 1:
        raise ValueError("reveal op coordinates must be finite numbers")
    if tag == "s" and len(nums) >= 3 and len(nums) % 2 == 1 and nums[0] > 0:
        return op
    if tag == "a" and len(nums) == 4:
        return op
    raise ValueError(f"not a reveal op: {str(op)[:80]}")


class _RevealKeyframe(BaseModel):
    model_config = ConfigDict(strict=True)
    label: str
    image: str = Field(pattern=r"^kf_\d{2}\.jpg$")
    ops: list[Annotated[list[object], AfterValidator(_check_reveal_op)]]


class _RevealManifest(BaseModel):
    """The shape of reveal.json the server derives version metadata from."""

    model_config = ConfigDict(strict=True)
    width: PositiveInt
    height: PositiveInt
    # The run painted over the previous version's canvas (it did not start over).
    continues: bool = False
    keyframes: list[_RevealKeyframe]


async def run_painting_program(state: WorkspaceState, on_live: OnLive | None = None) -> PaintResult:
    """Execute studio/painting.py in a subprocess; on success record a new version.

    While it runs, the program's performance streams into the version's
    directory; `on_live` hears when that stream starts and, if the run fails,
    that it was discarded (success is the recorded version).
    """
    started = time.monotonic()
    program = state.studio_program
    program_name = program.relative_to(state.workspace_dir)
    if program.is_symlink():
        return PaintFailure(
            f"{program_name} is a symlink. Write your painting program as a regular file.", 0.0
        )
    if not program.exists():
        return PaintFailure(
            f"No program yet. Write your painting program to {program_name} first.", 0.0
        )
    try:
        source = _read_no_follow(program)
    except OSError as e:
        return PaintFailure(f"Could not read {program_name}: {e.strerror or e}", 0.0)

    # A run that finishes after new_canvas/clear belongs to no current piece.
    generation = state.painting_generation
    token = secrets.token_hex(16)
    out_dir = state.paintings_dir / token
    out_dir.mkdir(parents=True)
    width = state.canvas.width * RENDER_SCALE
    height = state.canvas.height * RENDER_SCALE
    human_file = out_dir / "human.json"
    human_file.write_text(json.dumps(_human_strokes(state)))

    # The stream exists before it is announced, so viewers can follow it at once
    # (the runner then writes it from the start).
    (out_dir / "performance.bin").touch(exist_ok=False)
    live = LiveStarted(state.piece_number, token, width, height)
    state.live_painting = live
    try:
        if on_live:
            await on_live(live)
        # The program runs from a throwaway copy it may freely rewrite; what gets
        # published is `source`, the bytes read before the run.
        with tempfile.TemporaryDirectory(
            prefix="paint-run-", ignore_cleanup_errors=True
        ) as run_dir:
            run_program = FilePath(run_dir) / "painting.py"
            run_program.write_bytes(source)
            result = await _run_and_record(
                state, source, run_program, out_dir, token, generation, width, height, started
            )
    except asyncio.CancelledError:
        if on_live:
            # Viewers following the stream must drop it. Notified from its own
            # task, since awaiting here would be cancelled too.
            _spawn(on_live(LiveFailed(live.piece_number, token)))
        raise
    finally:
        if state.live_painting is live:
            state.live_painting = None
    if isinstance(result, PaintFailure) and on_live:
        await on_live(LiveFailed(live.piece_number, token))
    return result


def paint_env(run_dir: FilePath) -> dict[str, str]:
    """The whole environment of a paint run: nothing inherited from the server.

    The program is agent-written and may be prompt-injected, and whatever it can
    read may end up in public assets, so it gets no credentials or server config.
    The runner starts isolated (`-I`), so Python path variables are not needed.
    """
    return {
        "PATH": os.defpath,
        "HOME": str(run_dir),
        "TMPDIR": str(run_dir),
        "LANG": "C.UTF-8",
    }


async def _run_and_record(
    state: WorkspaceState,
    source: bytes,
    run_program: FilePath,
    out_dir: FilePath,
    token: str,
    generation: int,
    width: int,
    height: int,
    started: float,
) -> PaintResult:
    human_file = out_dir / "human.json"
    run_dir = run_program.parent
    base = state.painting  # the version this run paints over (if it continues it)
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-m",
        "code_monet.paint_runner",
        "--program",
        str(run_program),
        "--out",
        str(out_dir),
        "--width",
        str(width),
        "--height",
        str(height),
        "--seed",
        str(state.piece_number * 1000 + _next_version(state)),
        "--human",
        str(human_file),
        *_previous_args(state),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=run_dir,
        env=paint_env(run_dir),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=PAINT_TIMEOUT_S)
    except asyncio.CancelledError:
        # The turn was interrupted. Stop the run and clean up from another task:
        # under the SDK's anyio cancel scope every further await here is cancelled.
        proc.kill()
        _spawn(_reap(proc, out_dir))
        raise
    except TimeoutError:
        proc.kill()
        await proc.wait()
        _discard(out_dir)
        return PaintFailure(
            f"Program exceeded {PAINT_TIMEOUT_S}s and was stopped. Reduce mark counts or "
            "per-pixel work (vectorize, work on smaller regions).",
            time.monotonic() - started,
        )

    seconds = time.monotonic() - started
    if proc.returncode != 0:
        _discard(out_dir)
        err = stderr.decode(errors="replace")[-_ERROR_TAIL_CHARS:]
        out = stdout.decode(errors="replace")[-500:]
        return PaintFailure(
            f"Program failed:\n{err}" + (f"\nstdout:\n{out}" if out.strip() else ""), seconds
        )

    # The exported files, not stdout (which the program shares), are the record
    # of what was painted; the program may also have altered them on its way out.
    exported = await asyncio.to_thread(_collect_export, out_dir, width, height)
    if isinstance(exported, str):
        _discard(out_dir)
        out = stdout.decode(errors="replace")[-500:]
        return PaintFailure(exported + (f"\nstdout:\n{out}" if out.strip() else ""), seconds)
    try:
        human_file.unlink(missing_ok=True)
        _publish_program(out_dir, source)
    except OSError as e:
        _discard(out_dir)
        return PaintFailure(f"Could not publish the program: {e.strerror or e}", seconds)
    summary = exported.summary
    # A revision adds its marks to the picture's.
    prior_ops = base.ops if (exported.continues and base is not None) else 0
    version = await state.record_painting_version(
        token,
        summary["width"],
        summary["height"],
        summary["stages"],
        ops=prior_ops + summary["ops"],
        generation=generation,
    )
    if version is None:
        _discard(out_dir)
        return PaintFailure(
            "The canvas was reset while this program ran; its result was discarded.", seconds
        )
    _start_next_revision(state, source, version.version)
    if base is not None:
        # Only the latest version's canvas is ever continued.
        discard_canvas_state(state, base.token)
    logger.info(
        f"User {state.user_id}: painting v{version.version} rendered in {seconds:.1f}s "
        f"({version.ops} ops, {len(version.stages)} stages)"
    )
    return PaintSuccess(version=version, preview_jpeg=exported.preview_jpeg, seconds=seconds)


REVISION_STUB = """\
# Version {next} paints over the current canvas (version {current}).
# Write only what this revision adds or changes. No erasing: paint new forms
# directly over old ones. Earlier programs: studio/versions/.
"""


def _start_next_revision(state: WorkspaceState, source: bytes, version: int) -> None:
    """Archive the program that made `version`; the working program starts empty.

    The next run paints over this version's canvas, so re-running the same program
    would paint it all again on top.
    """
    program = state.studio_program
    archive = program.parent / "versions" / f"v{version}.py"
    try:
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(source)
        if program.is_symlink():
            program.unlink()
        program.write_text(REVISION_STUB.format(next=version + 1, current=version))
    except OSError as e:
        logger.warning(f"User {state.user_id}: could not start revision file: {e}")


def discard_canvas_state(state: WorkspaceState, token: str) -> None:
    """Delete a version's saved canvas (canvas.npz) once nothing will continue it."""
    path = state.painting_asset(token, "canvas.npz")
    if path is not None:
        path.unlink(missing_ok=True)


def _next_version(state: WorkspaceState) -> int:
    latest = state.painting
    return latest.version + 1 if latest else 1


def _previous_args(state: WorkspaceState) -> list[str]:
    """`--previous DIR` when this run revises the current version (paints over its canvas).

    Versions from before canvas states were saved have none: the run starts fresh.
    """
    latest = state.painting
    if latest is None:
        return []
    canvas = state.painting_asset(latest.token, "canvas.npz")
    if canvas is None or state.painting_asset(latest.token, "final.png") is None:
        return []
    return ["--previous", str(canvas.parent)]


def _collect_export(out_dir: FilePath, width: int, height: int) -> _Exported | str:
    """Check the run's output directory holds a publishable version, or explain why not.

    A recorded version is a real directory whose published assets are regular
    files, and whose manifest has the size the server requested.
    """
    tampered = "Do not write into the output directory."
    malformed = "The painting's reveal.json is malformed ({}). " + tampered
    if not stat.S_ISDIR(_lstat_mode(out_dir)):
        return "The painting's output directory was moved or replaced. " + tampered
    try:
        raw = json.loads(_read_no_follow(out_dir / "reveal.json"))
        manifest = _RevealManifest.model_validate(raw)
    except FileNotFoundError:
        return (
            "Program exited without exporting the painting. Let it run to the end; "
            "do not call sys.exit() or os._exit()."
        )
    except OSError as e:
        return f"Could not read the painting's reveal.json: {e.strerror or e}"
    except (ValueError, RecursionError) as e:  # bad or too deeply nested JSON, bad shape
        return malformed.format(str(e)[:300])
    if (manifest.width, manifest.height) != (width, height):
        return malformed.format(
            f"size {manifest.width}x{manifest.height}, expected {width}x{height}"
        )
    assets = ["final.png", "performance.bin", *(kf.image for kf in manifest.keyframes)]
    for name in assets:
        if not stat.S_ISREG(_lstat_mode(out_dir / name)):
            return f"The painting's {name} is missing or not a regular file. " + tampered
    try:
        preview_jpeg = _read_no_follow(out_dir / "preview.jpg")
    except OSError as e:
        return f"Could not read the painting's preview.jpg: {e.strerror or e}. " + tampered
    return _Exported(
        summary=reveal_summary(raw), preview_jpeg=preview_jpeg, continues=manifest.continues
    )


def _lstat_mode(path: FilePath) -> int:
    """File type bits of `path` itself (0 if absent), never following a symlink."""
    try:
        return path.lstat().st_mode
    except OSError:
        return 0


def _discard(out_dir: FilePath) -> None:
    """Remove a run's output directory, or the link a program left in its place."""
    if out_dir.is_symlink():
        out_dir.unlink(missing_ok=True)
    else:
        shutil.rmtree(out_dir, ignore_errors=True)


# Cleanup outliving a cancelled run; held so the loop doesn't drop the tasks.
_background: set[asyncio.Future[None]] = set()


def _spawn(work: Awaitable[None]) -> None:
    task = asyncio.ensure_future(work)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _reap(proc: asyncio.subprocess.Process, out_dir: FilePath) -> None:
    """Wait out a killed run, then remove what it wrote."""
    await proc.wait()
    _discard(out_dir)


def _read_no_follow(path: FilePath) -> bytes:
    """Read a regular file without following a symlink at its final component.

    Non-blocking open so a FIFO left at the path cannot stall the read.
    """
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise OSError(errno.EINVAL, "not a regular file")
        return f.read()


def _publish_program(out_dir: FilePath, source: bytes) -> None:
    """Write the trusted program bytes as the version's painting.py.

    The finished run may have left anything at that path (a symlink, other
    contents); replace it with a fresh regular file, never following links.
    """
    target = out_dir / "painting.py"
    if target.is_symlink() or target.is_file():
        target.unlink()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write(source)


def _human_strokes(state: WorkspaceState) -> list[list[list[float]]]:
    """Human strokes as polylines in image pixels, for the program to respond to."""
    return [
        [[p.x * RENDER_SCALE, p.y * RENDER_SCALE] for p in s.points]
        for s in state.canvas.strokes
        if s.author == "human"
    ]
