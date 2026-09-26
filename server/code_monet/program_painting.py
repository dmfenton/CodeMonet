"""Run the agent's painting program and publish the result as a painting version.

Paint mode is program painting: the agent keeps `studio/painting.py` in its
workspace, and each successful run renders a new version (keyframes, final
image, reveal log) under `paintings/{token}/`. See docs/program-painting.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path as FilePath

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


async def run_painting_program(state: WorkspaceState) -> PaintResult:
    """Execute studio/painting.py in a subprocess; on success record a new version."""
    started = time.monotonic()
    program = state.studio_program
    if not program.exists():
        return PaintFailure(
            f"No program yet. Write your painting program to {program.relative_to(state.workspace_dir)} first.",
            0.0,
        )

    token = secrets.token_hex(16)
    out_dir = state.paintings_dir / token
    out_dir.mkdir(parents=True)
    width = state.canvas.width * RENDER_SCALE
    height = state.canvas.height * RENDER_SCALE
    human_file = out_dir / "human.json"
    human_file.write_text(json.dumps(_human_strokes(state)))

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "code_monet.tools.paint_runner",
        "--program",
        str(program),
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

    lines = stdout.decode(errors="replace").strip().splitlines()
    summary = json.loads(lines[-1])
    human_file.unlink(missing_ok=True)
    shutil.copyfile(program, out_dir / "painting.py")
    version = await state.record_painting_version(
        token,
        int(summary["width"]),
        int(summary["height"]),
        list(summary["stages"]),
        ops=int(summary["ops"]),
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


def _human_strokes(state: WorkspaceState) -> list[list[list[float]]]:
    """Human strokes as polylines in image pixels, for the program to respond to."""
    return [
        [[p.x * RENDER_SCALE, p.y * RENDER_SCALE] for p in s.points]
        for s in state.canvas.strokes
        if s.author == "human"
    ]
