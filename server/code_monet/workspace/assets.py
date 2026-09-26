"""Program-painting version assets on disk: the single check before any read."""

from __future__ import annotations

import stat
from pathlib import Path


def version_asset(user_dir: Path, token: str, file: str) -> Path | None:
    """`{user_dir}/paintings/{token}/{file}` if it is safe to read and publish.

    A painting program runs with the server's filesystem access, so it may have
    planted symlinks (anywhere under the user directory) or hard links to other
    files. Accept only a single-link regular file whose real path is exactly
    that location; the user directory itself may sit behind a server-configured
    link (the data volume).
    """
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
