"""Program-painting version assets on disk: the single check before any read."""

from __future__ import annotations

import re
import stat
from pathlib import Path

_TOKEN = re.compile(r"[0-9a-f]{32}")  # secrets.token_hex(16), from program_painting
_FILE = re.compile(r"[a-z0-9_]+\.[a-z]+")


def version_asset(user_dir: Path, token: str, file: str) -> Path | None:
    """`{user_dir}/paintings/{token}/{file}` if it is safe to read and publish.

    A painting program runs with the server's filesystem access, so it may have
    planted symlinks (below the user directory) or hard links to other files,
    which would keep exposing whatever those files hold later. Accept only a
    well-formed token and file name naming a single-link regular file whose real
    path is exactly that location; the user directory itself may sit behind a
    server-configured link (the data volume). This refuses live links, not
    copies: the program can still write any bytes it can read (see
    docs/program-painting.md).
    """
    if not _TOKEN.fullmatch(token) or not _FILE.fullmatch(file):
        return None
    path = user_dir / "paintings" / token / file
    try:
        info = path.lstat()
        real = path.resolve(strict=True)
        expected = user_dir.resolve(strict=True) / "paintings" / token / file
    except OSError:
        return None
    if real != expected or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        return None
    return path
