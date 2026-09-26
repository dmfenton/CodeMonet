"""Image smoke check: the Agent SDK finds a Claude CLI that runs.

Usage (from the repo root), with IMAGE the built server image:
docker run --rm -i --entrypoint /app/server/.venv/bin/python IMAGE - < server/docker/smoke_cli.py
"""

import shutil
import subprocess
import sys

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk._cli_version import __cli_version__
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

cli = SubprocessCLITransport(prompt="", options=ClaudeAgentOptions())._find_cli()
version = subprocess.run([cli, "--version"], capture_output=True, text=True, check=True).stdout
assert version.startswith(__cli_version__), (cli, version, __cli_version__)
assert shutil.which("rg"), "ripgrep missing (USE_BUILTIN_RIPGREP=0)"
assert shutil.which("bash"), "bash missing (the CLI's Bash tool requires it)"
# The agent's shell runs `python3` for image work; it must be the venv's.
python3 = subprocess.run(
    ["python3", "-c", "import PIL, sys; print(sys.prefix)"], capture_output=True, text=True
)
assert python3.returncode == 0 and python3.stdout.strip() == sys.prefix, python3
print(f"claude {version.strip()} at {cli}")
