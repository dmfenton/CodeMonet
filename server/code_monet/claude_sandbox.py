"""Exec the Claude CLI inside the sandbox (the Agent SDK's `cli_path` target).

`bin/claude-sandboxed` runs `python -I -m code_monet.claude_sandbox ARGS...`.
The server puts the launch spec (see `claude_runtime`) in the CODE_MONET_SANDBOX
environment variable; the SDK passes the server's whole environment alongside
it. This builds the CLI's environment from the spec plus the few variables the
SDK sets for the CLI, confines the process (Linux), and execs the real CLI, so
the agent's tools and every command they run inherit the sandbox.

Without a spec it refuses to run (the SDK's version probe, which never gets
one, treats that as "version unknown").
"""

from __future__ import annotations

import json
import os
import sys

from code_monet import sandbox

SPEC_ENV = "CODE_MONET_SANDBOX"
_SDK_PREFIXES = ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK_")
_SDK_NAMES = frozenset({"PWD", "TRACEPARENT", "TRACESTATE"})


def cli_environment(inherited: dict[str, str], spec_env: dict[str, str]) -> dict[str, str]:
    """The spec's environment plus what the SDK sets for the CLI; nothing else."""
    sdk = {k: v for k, v in inherited.items() if k in _SDK_NAMES or k.startswith(_SDK_PREFIXES)}
    return {**sdk, **spec_env}


def main(argv: list[str]) -> int:
    raw = os.environ.get(SPEC_ENV)
    if raw is None:
        print(f"claude-sandboxed: no {SPEC_ENV} launch spec; refusing to run", file=sys.stderr)
        return 2
    spec = json.loads(raw)
    env = cli_environment(dict(os.environ), spec["env"])
    if sandbox.available():
        sandbox.confine(
            sandbox.Policy(
                read=tuple(spec["read"]),
                write=tuple(spec["write"]),
                protected_pids=(1, os.getppid()),
            )
        )
    cli = spec["cli"]
    os.execve(cli, [cli, *argv], env)
    return 1  # not reached


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
