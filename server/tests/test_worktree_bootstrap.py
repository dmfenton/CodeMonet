from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(*args: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    if completed.returncode != 0:
        raise AssertionError(
            f"command failed ({completed.returncode}): {' '.join(args)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout.strip()


def _commit(repository: Path, message: str) -> str:
    _run("git", "add", ".", cwd=repository)
    _run("git", "commit", "-m", message, cwd=repository)
    return _run("git", "rev-parse", "HEAD", cwd=repository)


def _write_tool(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def test_worktree_bootstrap_needs_no_platform_checkout() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        repositories = Path(temporary_directory) / "repos"
        app = repositories / "CodeMonet"
        worktree = repositories / "codemonet-feature"
        tools = repositories / "tools"
        app.mkdir(parents=True)
        tools.mkdir()
        _run("git", "init", "-b", "main", cwd=app)
        _run("git", "config", "user.email", "test@example.test", cwd=app)
        _run("git", "config", "user.name", "Test", cwd=app)
        (app / "scripts").mkdir()
        (app / "scripts/worktree-bootstrap.sh").write_text(
            (ROOT / "scripts/worktree-bootstrap.sh").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (app / "server").mkdir()
        (app / "server/.keep").write_text("", encoding="utf-8")
        _commit(app, "bootstrap")
        _run("git", "worktree", "add", "-b", "feature", str(worktree), cwd=app)

        calls = repositories / "calls"
        _write_tool(tools / "node", "echo 24")
        _write_tool(tools / "npm", f'echo "npm $*" >> "{calls}"')
        _write_tool(tools / "uv", f'echo "uv $*" >> "{calls}"')
        environment = {
            **os.environ,
            "PATH": f"{tools}:{os.environ['PATH']}",
            "VOLTA_HOME": str(tools / "volta"),
        }
        _run("bash", "scripts/worktree-bootstrap.sh", cwd=worktree, env=environment)

        assert not (worktree / "vendor").exists()
        recorded = calls.read_text(encoding="utf-8")
        assert "uv sync --frozen --extra dev --all-groups --quiet" in recorded
        assert "npm ci" in recorded
