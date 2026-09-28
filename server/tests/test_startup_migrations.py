"""Startup migrations must leave the server's logging alone."""

import logging
from pathlib import Path

import pytest

from code_monet import main
from code_monet.config import settings


@pytest.mark.asyncio
async def test_migrations_keep_app_loggers_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{tmp_path}/auth.db")
    monkeypatch.chdir(Path(__file__).parent.parent)  # alembic.ini lives in server/
    app_logger = logging.getLogger("code_monet.orchestrator")
    root_level = logging.getLogger().level

    await main.run_migrations()

    assert (tmp_path / "auth.db").exists(), "migrations ran"
    assert app_logger.disabled is False
    assert logging.getLogger().level == root_level
