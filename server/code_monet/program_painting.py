"""Run the agent's painting program and publish the result as a painting version.

Paint mode is program painting: the agent keeps `studio/painting.py` in its
workspace, and each successful run renders a new version (keyframes, final
image, reveal log) under `paintings/{token}/`. See docs/program-painting.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path as FilePath

from pydantic import BaseModel, ConfigDict, PositiveInt

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
    preview: FilePath
    final: FilePath
    seconds: float


@dataclass(frozen=True)
class PaintFailure:
    error: str
    seconds: float


PaintResult = PaintSuccess | PaintFailure


class _RevealKeyframe(BaseModel):
    model_config = ConfigDict(strict=True)
    label: str
    ops: list[object]


class _RevealManifest(BaseModel):
    """The shape of reveal.json the server derives version metadata from."""

    model_config = ConfigDict(strict=True)
    width: PositiveInt
    height: PositiveInt
    keyframes: list[_RevealKeyframe]


async def run_painting_program(state: WorkspaceState) -> PaintResult:
    """Execute studio/painting.py in a subprocess; on success record a new version."""
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

    # The program runs from a throwaway copy it may freely rewrite; what gets
    # published is `source`, the bytes read before the run.
    with tempfile.TemporaryDirectory(prefix="paint-run-") as run_dir:
        run_program = FilePath(run_dir) / "painting.py"
        run_program.write_bytes(source)
        return await _run_and_record(
            state, source, run_program, out_dir, token, generation, width, height, started
        )


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
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "code_monet.tools.paint_runner",
        "--program",
        str(run_program),
        "--out",
        str(out_dir),
        "--width",
        str(width),
        "--height",
        str(height),
        "--seed",
        str(state.piece_number),
        "--human",
        str(human_file),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=state.workspace_dir,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=PAINT_TIMEOUT_S)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        shutil.rmtree(out_dir, ignore_errors=True)
        return PaintFailure(
            f"Program exceeded {PAINT_TIMEOUT_S}s and was stopped. Reduce mark counts or "
            "per-pixel work (vectorize, work on smaller regions).",
            time.monotonic() - started,
        )

    seconds = time.monotonic() - started
    if proc.returncode != 0:
        shutil.rmtree(out_dir, ignore_errors=True)
        err = stderr.decode(errors="replace")[-_ERROR_TAIL_CHARS:]
        out = stdout.decode(errors="replace")[-500:]
        return PaintFailure(
            f"Program failed:\n{err}" + (f"\nstdout:\n{out}" if out.strip() else ""), seconds
        )

    # The published reveal.json, not stdout (which the program shares), is the
    # record of what was painted.
    summary = _read_reveal_summary(out_dir)
    if isinstance(summary, str):
        shutil.rmtree(out_dir, ignore_errors=True)
        out = stdout.decode(errors="replace")[-500:]
        return PaintFailure(summary + (f"\nstdout:\n{out}" if out.strip() else ""), seconds)
    human_file.unlink(missing_ok=True)
    try:
        _publish_program(out_dir, source)
    except OSError as e:
        shutil.rmtree(out_dir, ignore_errors=True)
        return PaintFailure(f"Could not publish the program: {e.strerror or e}", seconds)
    version = await state.record_painting_version(
        token,
        summary["width"],
        summary["height"],
        summary["stages"],
        ops=summary["ops"],
        generation=generation,
    )
    if version is None:
        shutil.rmtree(out_dir, ignore_errors=True)
        return PaintFailure(
            "The canvas was reset while this program ran; its result was discarded.", seconds
        )
    logger.info(
        f"User {state.user_id}: painting v{version.version} rendered in {seconds:.1f}s "
        f"({version.ops} ops, {len(version.stages)} stages)"
    )
    return PaintSuccess(
        version=version,
        preview=out_dir / "preview.jpg",
        final=out_dir / "final.png",
        seconds=seconds,
    )


def _read_reveal_summary(out_dir: FilePath) -> RevealSummary | str:
    """Version metadata from the run's reveal.json, or an error for the agent."""
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
    except ValueError as e:  # bad JSON or a failed validation
        return (
            f"The painting's reveal.json is malformed ({str(e)[:300]}). "
            "Do not write into the output directory."
        )
    return reveal_summary(manifest.model_dump())


def _read_no_follow(path: FilePath) -> bytes:
    """Read a file without following a symlink at its final component."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
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
