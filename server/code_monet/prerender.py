"""Pre-render the public site so nginx serves it while the server sleeps.

The web build owns every page: its markup, head tags (title, Open Graph,
JSON-LD) and initial data come from the same React render the SSR server used
(`web/src/entry-server.tsx`), run by the web build's `dist/prerender/prerender.mjs`.
This module only gathers the public gallery data those pages embed, runs that
bundle once per change, and writes its pages plus the sitemap atomically:

    /                        -> index.html
    /gallery                 -> gallery.html
    /gallery/{user}/{piece}  -> gallery/{user}/{piece}.html
    /sitemap.xml             -> sitemap.xml

nginx tries `$uri.html` in this directory before the SPA's index.html, so a
page that is missing here still loads, only with generic meta tags.
Regeneration runs at startup (every deploy and wake) and whenever a public
gallery changes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from code_monet.config import settings

logger = logging.getLogger(__name__)

BUNDLE = "prerender.mjs"
SITEMAP = "sitemap.xml"
_PAGE_PATH = re.compile(r"^/(gallery(/[0-9a-fA-F-]{36}/piece_[0-9]{6})?)?$")


@dataclass(frozen=True)
class SiteFiles:
    """Every file of the pre-rendered site, keyed by path relative to its root."""

    files: dict[str, bytes]


def page_file(path: str) -> str:
    """Relative file for a page path; rejects anything outside the public routes."""
    if not _PAGE_PATH.match(path):
        raise ValueError(f"not a pre-renderable page path: {path!r}")
    return "index.html" if path == "/" else f"{path[1:]}.html"


def site_input(records: list[tuple[str, str, dict[str, Any]]]) -> dict[str, Any]:
    """The renderer's input: every public piece (newest first) and its public detail.

    Pages embed this data, so visitors read the gallery without calling the server.
    """
    from code_monet.routes.public_gallery import public_gallery_entry, public_piece_detail

    pieces: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}
    for user_id, piece_id, data in records:
        try:
            pieces.append(public_gallery_entry(user_id, data))
            detail = public_piece_detail(user_id, piece_id, data)
        except (TypeError, ValueError, AttributeError, KeyError):
            continue
        details[f"{user_id}/{piece_id}"] = detail
    pieces.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return {"pieces": pieces, "details": details}


async def run_bundle(bundle_dir: Path, payload: dict[str, Any]) -> list[dict[str, str]]:
    """Run the web build's renderer: JSON input on stdin, pages on stdout.

    A thread runs it with subprocess's own timeout, which kills the child;
    cancelling asyncio's communicate() can leave a stuck child running.
    """
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [settings.prerender_node, str(bundle_dir / BUNDLE)],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=settings.prerender_timeout_seconds,
            env={"NODE_ENV": "production", "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"pre-render timed out after {settings.prerender_timeout_seconds}s"
        ) from None
    if result.returncode != 0:
        raise RuntimeError(
            f"pre-render exited {result.returncode}: "
            f"{result.stderr.decode(errors='replace')[-500:]}"
        )
    pages = json.loads(result.stdout)["pages"]
    if not isinstance(pages, list):
        raise RuntimeError("pre-render returned no page list")
    return pages


def site_files(pages: list[dict[str, str]], sitemap: str) -> SiteFiles:
    files = {page_file(page["path"]): page["html"].encode() for page in pages}
    files[SITEMAP] = sitemap.encode()
    return SiteFiles(files)


def _write_atomic(target: Path, content: bytes) -> None:
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            # nginx's unprivileged worker reads these through a read-only mount.
            os.fchmod(handle.fileno(), 0o644)
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def write_site(root: Path, site: SiteFiles) -> tuple[int, int]:
    """Make root hold exactly the site's files. Returns (written, removed).

    Files are replaced one at a time with atomic renames; the directory itself
    is never replaced, because nginx holds it through a bind mount.
    """
    root.mkdir(mode=0o755, parents=True, exist_ok=True)
    written = 0
    for relative, content in site.files.items():
        target = root / relative
        if target.is_file() and not target.is_symlink() and target.read_bytes() == content:
            continue
        _write_atomic(target, content)
        written += 1

    removed = 0
    for existing in sorted(root.rglob("*"), reverse=True):
        relative = existing.relative_to(root).as_posix()
        if existing.is_dir() and not existing.is_symlink():
            if relative.startswith("gallery") and not any(existing.iterdir()):
                existing.rmdir()
            continue
        if relative not in site.files:
            existing.unlink()
            removed += 1
    return written, removed


async def regenerate() -> None:
    """Rebuild the pre-rendered site from the current public gallery."""
    from code_monet.routes.public_gallery import public_piece_records
    from code_monet.routes.seo import sitemap_xml

    bundle_dir = Path(settings.prerender_bundle_dir)
    if not (bundle_dir / BUNDLE).is_file():
        logger.debug(f"No pre-render bundle at {bundle_dir.resolve()}; skipping")
        return
    records = await public_piece_records()
    pages = await run_bundle(bundle_dir, site_input(records))
    site = site_files(pages, sitemap_xml(records))
    root = Path(settings.prerender_dir)
    written, removed = await asyncio.to_thread(write_site, root, site)
    logger.info(
        f"Pre-rendered {len(site.files)} files in {root.resolve()} "
        f"({written} written, {removed} removed)"
    )


class PrerenderScheduler:
    """Single-flight, coalescing runner: requests during a run cause one more run."""

    def __init__(self, job: Callable[[], Awaitable[None]]) -> None:
        self._job = job
        self._dirty = False
        self._task: asyncio.Task[None] | None = None

    def request(self) -> None:
        self._dirty = True
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def wait(self) -> None:
        """Wait for any scheduled work (tests and orderly shutdown)."""
        while self._task is not None and not self._task.done():
            await self._task

    async def _run(self) -> None:
        while self._dirty:
            self._dirty = False
            try:
                await self._job()
            except Exception:
                logger.exception("Pre-rendering the public site failed")


prerender_scheduler = PrerenderScheduler(regenerate)
