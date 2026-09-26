"""Install the Claude Code CLI the Agent SDK pins, as the SDK's bundled CLI.

The SDK only publishes glibc (manylinux) wheels with the CLI bundled; the
server image is Alpine (musl), so the wheel's `_bundled/` is empty and the SDK
cannot start. This fetches the musl build of exactly `__cli_version__` from
Anthropic's release bucket (as the official installer does), verifies it
against the release manifest's SHA-256, and puts it where the SDK looks first.

Run with the venv's python at image build time.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import urllib.request
from pathlib import Path

import claude_agent_sdk
from claude_agent_sdk._cli_version import __cli_version__

RELEASES = (
    "https://storage.googleapis.com/"
    "claude-code-dist-86c565f3-f756-42ad-8dfa-d59b1c096819/claude-code-releases"
)
_ARCH = {"x86_64": "x64", "aarch64": "arm64"}


def main() -> int:
    target = f"linux-{_ARCH[platform.machine()]}-musl"
    with urllib.request.urlopen(f"{RELEASES}/{__cli_version__}/manifest.json") as resp:
        expected = json.load(resp)["platforms"][target]["checksum"]
    dest = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"
    partial = dest.with_suffix(".partial")
    digest = hashlib.sha256()
    url = f"{RELEASES}/{__cli_version__}/{target}/claude"
    with urllib.request.urlopen(url) as resp, partial.open("wb") as out:
        while chunk := resp.read(1 << 20):
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest() != expected:
        partial.unlink()
        print(f"claude {__cli_version__} {target}: checksum mismatch", file=sys.stderr)
        return 1
    os.chmod(partial, 0o755)
    partial.replace(dest)
    print(f"installed claude {__cli_version__} ({target}) at {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
