"""Pre-rendered public site: data gathering, atomic writes and scheduling."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_monet import prerender
from code_monet.config import settings
from code_monet.prerender import (
    PrerenderScheduler,
    SiteFiles,
    page_file,
    site_files,
    site_input,
    write_site,
)

USER = "12345678-1234-1234-1234-123456789abc"
REPO = Path(__file__).resolve().parents[2]
BUNDLE_DIR = REPO / "web/dist/prerender"


def piece(number: int, **extra: object) -> dict[str, object]:
    return {
        "piece_number": number,
        "strokes": [{"type": "line", "points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]}],
        "created_at": f"2026-10-{number:02d}T00:00:00+00:00",
        "title": f"Piece title {number}",
        "prompt": "water lilies",
        **extra,
    }


class TestPageFile:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/", "index.html"),
            ("/gallery", "gallery.html"),
            (f"/gallery/{USER}/piece_000012", f"gallery/{USER}/piece_000012.html"),
        ],
    )
    def test_maps_public_routes(self, path: str, expected: str) -> None:
        assert page_file(path) == expected

    @pytest.mark.parametrize(
        "path",
        [
            "/studio",
            "/gallery/../../etc/passwd",
            f"/gallery/{USER}/../piece_000001",
            "/gallery/not-a-user/piece_000001",
            f"/gallery/{USER}/piece_1",
            "gallery",
        ],
    )
    def test_rejects_anything_else(self, path: str) -> None:
        with pytest.raises(ValueError, match="not a pre-renderable page"):
            page_file(path)


class TestSiteInput:
    def test_lists_newest_first_with_full_detail(self) -> None:
        records = [
            (USER, "piece_000001", piece(1)),
            (USER, "piece_000003", piece(3)),
            (USER, "piece_000002", piece(2, piece_number="bad")),  # unreadable
        ]
        result = site_input(records)
        assert [p["id"] for p in result["pieces"]] == ["piece_000003", "piece_000001"]
        detail = result["details"][f"{USER}/piece_000003"]
        assert detail["title"] == "Piece title 3"
        assert detail["prompt"] == "water lilies"
        assert detail["strokes"], "pages embed the detail the client would fetch"
        assert f"{USER}/piece_000002" not in result["details"]


class TestWriteSite:
    def test_writes_world_readable_files_and_prunes_stale_pages(self, tmp_path: Path) -> None:
        root = tmp_path / "site"
        first = SiteFiles(
            {
                "index.html": b"home",
                "sitemap.xml": b"<urlset/>",
                f"gallery/{USER}/piece_000001.html": b"one",
                f"gallery/{USER}/piece_000002.html": b"two",
            }
        )
        assert write_site(root, first) == (4, 0)
        mode = stat.S_IMODE((root / f"gallery/{USER}/piece_000001.html").stat().st_mode)
        assert mode == 0o644
        assert stat.S_IMODE((root / "gallery").stat().st_mode) & 0o005 == 0o005

        # Unpublishing a gallery removes its pages and their empty directory.
        second = SiteFiles({"index.html": b"home", "sitemap.xml": b"<urlset/>"})
        assert write_site(root, second) == (0, 2)
        assert sorted(p.name for p in root.iterdir()) == ["index.html", "sitemap.xml"]

    def test_unchanged_files_are_not_rewritten(self, tmp_path: Path) -> None:
        site = SiteFiles({"index.html": b"home"})
        write_site(tmp_path, site)
        inode = (tmp_path / "index.html").stat().st_ino
        assert write_site(tmp_path, site) == (0, 0)
        assert (tmp_path / "index.html").stat().st_ino == inode

    def test_replaces_a_planted_symlink_instead_of_following_it(self, tmp_path: Path) -> None:
        secret = tmp_path / "secret.db"
        secret.write_bytes(b"private")
        root = tmp_path / "site"
        root.mkdir()
        os.symlink(secret, root / "index.html")
        os.symlink(secret, root / "extra.html")
        write_site(root, SiteFiles({"index.html": b"home"}))
        assert not (root / "index.html").is_symlink()
        assert (root / "index.html").read_bytes() == b"home"
        assert not (root / "extra.html").exists()
        assert secret.read_bytes() == b"private"

    def test_failed_write_leaves_no_temporary_file(self, tmp_path: Path) -> None:
        with (
            patch("code_monet.prerender.os.replace", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
        ):
            write_site(tmp_path, SiteFiles({"index.html": b"home"}))
        assert list(tmp_path.iterdir()) == []


class TestSiteFiles:
    def test_adds_the_sitemap(self) -> None:
        site = site_files([{"path": "/", "html": "home"}], "<urlset/>")
        assert site.files == {"index.html": b"home", "sitemap.xml": b"<urlset/>"}


class TestScheduler:
    @pytest.mark.asyncio
    async def test_requests_during_a_run_coalesce_into_one_more_run(self) -> None:
        runs = 0
        release = asyncio.Event()

        async def job() -> None:
            nonlocal runs
            runs += 1
            if runs == 1:
                await release.wait()

        scheduler = PrerenderScheduler(job)
        scheduler.request()
        await asyncio.sleep(0)
        scheduler.request()
        scheduler.request()
        release.set()
        await scheduler.wait()
        assert runs == 2

    @pytest.mark.asyncio
    async def test_a_failed_run_is_logged_not_raised(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        async def job() -> None:
            raise RuntimeError("boom")

        scheduler = PrerenderScheduler(job)
        scheduler.request()
        await scheduler.wait()
        assert "Pre-rendering the public site failed" in caplog.text


@pytest.fixture
def public_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    gallery = tmp_path / "users" / USER / "gallery"
    gallery.mkdir(parents=True)
    for number in (1, 2):
        (gallery / f"piece_{number:06d}.json").write_text(json.dumps(piece(number)))
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path / "users"))
    monkeypatch.setattr(settings, "prerender_dir", str(tmp_path / "site"))
    return tmp_path


@pytest.fixture
def public_users() -> object:
    user = MagicMock(id=USER, gallery_public=True)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=MagicMock())
    context.__aexit__ = AsyncMock(return_value=None)
    with (
        patch("code_monet.routes.public_gallery.repository") as repository,
        patch("code_monet.routes.public_gallery.get_session", return_value=context),
    ):
        repository.list_users_with_public_gallery = AsyncMock(return_value=[user])
        yield repository


@pytest.mark.usefixtures("public_users")
class TestRegenerate:
    @pytest.mark.asyncio
    async def test_skips_without_a_bundle(
        self, public_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "prerender_bundle_dir", str(public_workspace / "none"))
        await prerender.regenerate()
        assert not (public_workspace / "site").exists()

    @pytest.mark.asyncio
    async def test_bundle_failure_raises_with_its_error(
        self, public_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bundle = public_workspace / "bundle"
        bundle.mkdir()
        (bundle / "prerender.mjs").write_text("process.stderr.write('bad input'); process.exit(3)")
        monkeypatch.setattr(settings, "prerender_bundle_dir", str(bundle))
        if shutil.which(settings.prerender_node) is None:
            pytest.skip("node is not installed")
        with pytest.raises(RuntimeError, match="exited 3: bad input"):
            await prerender.regenerate()

    @pytest.mark.asyncio
    async def test_bundle_timeout_kills_it(
        self, public_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bundle = public_workspace / "bundle"
        bundle.mkdir()
        (bundle / "prerender.mjs").write_text("setInterval(() => {}, 1000)")
        monkeypatch.setattr(settings, "prerender_bundle_dir", str(bundle))
        monkeypatch.setattr(settings, "prerender_timeout_seconds", 0.5)
        if shutil.which(settings.prerender_node) is None:
            pytest.skip("node is not installed")
        with pytest.raises(RuntimeError, match="timed out"):
            await prerender.regenerate()

    @pytest.mark.asyncio
    async def test_real_bundle_writes_pages_and_sitemap(
        self, public_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        if not (BUNDLE_DIR / "prerender.mjs").is_file() or shutil.which("node") is None:
            pytest.skip("web/dist/prerender is not built (npm run build -w web)")
        monkeypatch.setattr(settings, "prerender_bundle_dir", str(BUNDLE_DIR))
        await prerender.regenerate()
        site = public_workspace / "site"
        page = (site / f"gallery/{USER}/piece_000002.html").read_text()
        assert 'property="og:title" content="Piece title 2"' in page
        assert f"/api/public/gallery/{USER}/piece_000002/og-image.png" in page
        assert "window.__INITIAL_DATA__" in page
        assert (site / "index.html").is_file() and (site / "gallery.html").is_file()
        sitemap = (site / "sitemap.xml").read_text()
        assert f"https://monet.dmfenton.net/gallery/{USER}/piece_000001" in sitemap
