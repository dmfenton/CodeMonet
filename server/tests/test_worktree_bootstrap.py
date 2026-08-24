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


def test_worktree_bootstrap_uses_locked_platform_commit() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        repositories = Path(temporary_directory) / "repos"
        app = repositories / "CodeMonet"
        platform = repositories / "fenton-platform"
        worktree = repositories / "codemonet-feature"
        tools = repositories / "tools"
        app.mkdir(parents=True)
        platform.mkdir()
        tools.mkdir()

        for repository in (app, platform):
            _run("git", "init", "-b", "main", cwd=repository)
            _run("git", "config", "user.email", "test@example.test", cwd=repository)
            _run("git", "config", "user.name", "Test", cwd=repository)

        (platform / "python").mkdir()
        (platform / "python/version.txt").write_text("locked\n", encoding="utf-8")
        locked = _commit(platform, "locked")
        (platform / "python/version.txt").write_text("live\n", encoding="utf-8")
        live = _commit(platform, "live")
        assert locked != live

        (app / "scripts").mkdir()
        (app / "scripts/worktree-bootstrap.sh").write_text(
            (ROOT / "scripts/worktree-bootstrap.sh").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (app / "server").mkdir()
        (app / "server/.keep").write_text("", encoding="utf-8")
        (app / "fenton-platform.lock").write_text(f"{locked}\n", encoding="utf-8")
        _commit(app, "bootstrap")
        _run("git", "worktree", "add", "-b", "feature", str(worktree), cwd=app)

        _write_tool(tools / "node", "echo 24")
        _write_tool(tools / "npm", "exit 0")
        _write_tool(tools / "uv", "exit 0")
        environment = {
            **os.environ,
            "PATH": f"{tools}:{os.environ['PATH']}",
            "VOLTA_HOME": str(tools / "volta"),
        }
        stale_lock = worktree / "vendor/.fenton-platform-bootstrap.lock"
        stale_lock.mkdir(parents=True)

        _run("bash", "scripts/worktree-bootstrap.sh", cwd=worktree, env=environment)

        linked = worktree / "vendor/fenton-platform"
        assert linked.is_dir()
        assert not linked.is_symlink()
        assert locked == _run("git", "rev-parse", "HEAD", cwd=linked)
        assert (linked / "python/version.txt").read_text(encoding="utf-8").strip() == "locked"

        (platform / "python/version.txt").write_text("next\n", encoding="utf-8")
        next_locked = _commit(platform, "next locked")
        (worktree / "fenton-platform.lock").write_text(f"{next_locked}\n", encoding="utf-8")
        _run("bash", "scripts/worktree-bootstrap.sh", cwd=worktree, env=environment)
        assert next_locked == _run("git", "rev-parse", "HEAD", cwd=linked)
        assert (linked / "python/version.txt").read_text(encoding="utf-8").strip() == "next"

        (linked / "python/version.txt").write_text("dirty\n", encoding="utf-8")
        completed = subprocess.run(
            ("bash", "scripts/worktree-bootstrap.sh"),
            cwd=worktree,
            capture_output=True,
            text=True,
            env=environment,
        )
        assert completed.returncode != 0
        assert "has tracked changes" in completed.stderr
