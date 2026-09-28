"""How the server launches the Claude CLI for one user: always through the sandbox.

Every Claude CLI process (the drawing agent and the critique) runs via
`bin/claude-sandboxed` (see `claude_sandbox`) with a launch spec that says what
it may see: read-only system and Python paths, and read-write only that
user's workspace and that user's own Claude home (config, sessions, access
token cache, temp files). Its environment is built from the spec, never
inherited from the server.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from code_monet.anthropic_wif import anthropic_claude_environment
from code_monet.claude_sandbox import SPEC_ENV
from code_monet.config import settings

SANDBOXED_CLI = Path(__file__).parent / "bin" / "claude-sandboxed"
_SYSTEM_READ = ("/usr", "/lib", "/bin", "/sbin", "/etc", "/proc")
# Development (no workload identity) uses the developer's own Claude login.
_DEV_PASSTHROUGH = ("HOME", "USER", "LOGNAME", "SHELL", "TMPDIR")


@dataclass(frozen=True)
class ClaudeLaunch:
    """ClaudeAgentOptions fields that route one user's CLI through the sandbox."""

    cli_path: str
    env: dict[str, str]
    cwd: str


def claude_launch(user_id: str, workspace_dir: str) -> ClaudeLaunch:
    cli = real_cli()
    home = Path(settings.anthropic_config_directory) / "users" / user_id
    wif = anthropic_claude_environment(home / "claude")
    if wif:
        (home / "tmp").mkdir(parents=True, exist_ok=True, mode=0o700)
        identity = {**wif, "HOME": str(home), "TMPDIR": str(home / "tmp")}
        write = (workspace_dir, str(home), "/dev")
        read = (*_python_and_cli(cli), str(Path(settings.anthropic_identity_token_file).parent))
    else:
        identity = {k: os.environ[k] for k in _DEV_PASSTHROUGH if k in os.environ}
        write = (workspace_dir, os.environ.get("HOME", workspace_dir), "/dev")
        read = _python_and_cli(cli)
    env = {"PATH": os.environ.get("PATH", os.defpath), "LANG": "C.UTF-8", **identity}
    if "USE_BUILTIN_RIPGREP" in os.environ:
        env["USE_BUILTIN_RIPGREP"] = os.environ["USE_BUILTIN_RIPGREP"]
    spec = {"cli": cli, "env": env, "read": [*_SYSTEM_READ, *read], "write": list(write)}
    return ClaudeLaunch(str(SANDBOXED_CLI), {SPEC_ENV: json.dumps(spec)}, workspace_dir)


def _python_and_cli(cli: str) -> tuple[str, ...]:
    """Python and its packages (the agent's shell uses them) and the CLI binary."""
    return (sys.base_prefix, sys.prefix, str(Path(cli).parent))


@lru_cache
def real_cli() -> str:
    """The CLI the Agent SDK would run (its bundled build, else one on PATH)."""
    from claude_agent_sdk import ClaudeAgentOptions
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

    return SubprocessCLITransport(prompt="", options=ClaudeAgentOptions())._find_cli()
