"""generate_svg code is untrusted: the run gets no server environment."""

from __future__ import annotations

import json
import os
from pathlib import Path as FilePath

import pytest

from code_monet.tools import python_sandbox
from code_monet.tools.python_sandbox import run_python_code

PROBE = """
import os, sys
seen = {
    "env": dict(os.environ),
    "cwd": os.getcwd(),
    "file": __file__,
    "isolated": sys.flags.isolated,
    "modules": sorted(m for m in sys.modules if m.split(".")[0] in {"code_monet", "boto3", "claude_agent_sdk"}),
}
print("PROBE " + json.dumps(seen))
"""


@pytest.mark.asyncio
async def test_code_sees_no_server_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "jwt-canary")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-canary")
    monkeypatch.setenv("PYTHONPATH", "/nonexistent")

    result = await run_python_code(PROBE, 40, 30)

    assert result["return_code"] == 0, result["stderr"]
    assert "canary" not in result["stdout"] + result["stderr"]
    seen = json.loads(result["stdout"].split("PROBE ", 1)[1].splitlines()[0])
    seen["env"].pop("__CF_USER_TEXT_ENCODING", None)  # added by macOS to every process
    assert set(seen["env"]) == {"PATH", "HOME", "TMPDIR", "LANG"}
    assert seen["env"]["PATH"] == os.defpath
    assert seen["isolated"] == 1
    # The prelude loads no server code; agent code importing it explicitly is a
    # documented residual (docs/program-painting.md, "Untrusted programs").
    assert seen["modules"] == []
    run_dir = FilePath(seen["env"]["HOME"])
    assert seen["env"]["TMPDIR"] == str(run_dir)
    assert FilePath(seen["cwd"]).resolve() == run_dir.resolve()
    assert FilePath(seen["file"]).parent.resolve() == run_dir.resolve()
    assert run_dir.name.startswith("svg-run-")
    assert not run_dir.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    ["output_paths([line(0, 0, 10, 10)])", 'output_svg_paths(["M 0 0 L 10 10"])'],
)
async def test_paths_still_parse(code: str) -> None:
    result = await run_python_code(code, 40, 30)

    assert result["return_code"] == 0, result["stderr"]
    assert len(result["paths"]) == 1


@pytest.mark.asyncio
async def test_timeout_kills_the_run(monkeypatch: pytest.MonkeyPatch, tmp_path: FilePath) -> None:
    monkeypatch.setattr(python_sandbox, "PYTHON_TIMEOUT", 0.5)
    monkeypatch.setattr(python_sandbox.tempfile, "tempdir", str(tmp_path))

    result = await run_python_code("while True: pass", 40, 30)

    assert result["return_code"] == -1
    assert result["paths"] == []
    assert list(tmp_path.glob("svg-run-*")) == []
