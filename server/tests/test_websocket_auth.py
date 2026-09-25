"""WebSocket handshake authenticates with the same authority as REST."""

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from code_monet import main
from code_monet.auth import dependencies
from code_monet.auth.jwt import create_access_token
from code_monet.config import settings
from code_monet.db import User


class _StopAfterAuth(Exception):
    """Raised by the workspace stub once auth has succeeded."""


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    activate = AsyncMock(side_effect=_StopAfterAuth)
    monkeypatch.setattr(main.workspace_registry, "get_or_activate", activate)
    # No lifespan: auth is decided before any startup-owned state is touched.
    yield TestClient(main.app)


def _close_code(client: TestClient, url: str) -> tuple[int, str]:
    with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect(url) as ws:
        ws.receive_text()
    return closed.value.code, closed.value.reason


def _user(*, active: bool = True) -> User:
    return User(id="user-1", email="owner@example.com", password_hash="unused", is_active=active)


def test_platform_token_is_accepted_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolver = AsyncMock(return_value=_user())
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(dependencies, "user_for_platform_token", resolver)

    with pytest.raises(_StopAfterAuth), client.websocket_connect("/ws?token=platform-token"):
        pass

    resolver.assert_awaited_once_with("platform-token")
    main.workspace_registry.get_or_activate.assert_awaited_once_with("user-1")  # type: ignore[attr-defined]


def test_legacy_token_is_rejected_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(dependencies, "user_for_platform_token", AsyncMock(return_value=None))
    legacy = create_access_token("user-1", "owner@example.com")

    code, _ = _close_code(client, f"/ws?token={legacy}")

    assert code == 4001


def test_legacy_token_is_accepted_in_dev_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setattr(dependencies, "authenticate_access_token", AsyncMock(return_value=_user()))

    with pytest.raises(_StopAfterAuth), client.websocket_connect("/ws?token=dev-token"):
        pass


def test_inactive_user_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dependencies, "authenticate_access_token", AsyncMock(return_value=_user(active=False))
    )

    code, _ = _close_code(client, "/ws?token=token")

    assert code == 4001


def test_missing_token_is_rejected(client: TestClient) -> None:
    code, reason = _close_code(client, "/ws")

    assert (code, reason) == (4001, "Missing authentication token")


def test_identity_outage_closes_retriable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        dependencies,
        "authenticate_access_token",
        AsyncMock(side_effect=OSError("identity unreachable")),
    )

    code, _ = _close_code(client, "/ws?token=token")

    assert code == 1011
