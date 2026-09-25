"""WebSocket handshake authenticates with the same authority as REST."""

import base64
import json
from collections.abc import Iterator
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from code_monet import main
from code_monet.auth import dependencies, platform
from code_monet.auth.jwt import create_access_token
from code_monet.config import settings
from code_monet.db import User

# A server that never closes the socket would otherwise hang receive_text().
pytestmark = pytest.mark.timeout(30)


class _StopAfterAuth(Exception):
    """Raised by the workspace stub once auth has succeeded."""


@pytest.fixture
def activate(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Workspace activation stub: reaching it means the handshake authenticated."""
    stub = AsyncMock(side_effect=_StopAfterAuth)
    monkeypatch.setattr(main.workspace_registry, "get_or_activate", stub)
    return stub


@pytest.fixture
def client(activate: AsyncMock) -> TestClient:  # noqa: ARG001 - installs the activation stub
    # No lifespan: auth is decided before any startup-owned state is touched.
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def fresh_verifier() -> Iterator[None]:
    platform.jwks_provider.cache_clear()
    platform.access_token_verifier.cache_clear()
    yield
    platform.jwks_provider.cache_clear()
    platform.access_token_verifier.cache_clear()


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_: object) -> None:
        return None


def _close_code(client: TestClient, url: str) -> tuple[int, str]:
    with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect(url) as ws:
        ws.receive_text()
    return closed.value.code, closed.value.reason


def _user(*, active: bool = True) -> User:
    return User(id="user-1", email="owner@example.com", password_hash="unused", is_active=active)


def test_platform_token_is_accepted_in_production(
    client: TestClient, activate: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolver = AsyncMock(return_value=_user())
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(dependencies, "user_for_platform_token", resolver)

    with pytest.raises(_StopAfterAuth), client.websocket_connect("/ws?token=platform-token"):
        pass

    resolver.assert_awaited_once_with("platform-token")
    activate.assert_awaited_once_with("user-1")


def test_legacy_token_is_rejected_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Real verifier: an HS256 token fails the RS256 algorithm check before any key fetch.
    monkeypatch.setattr(settings, "dev_mode", False)
    legacy = create_access_token("user-1", "owner@example.com")

    code, _ = _close_code(client, f"/ws?token={legacy}")

    assert code == 4001


def test_legacy_token_is_accepted_in_dev_mode(
    client: TestClient, activate: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setattr(dependencies, "get_session", lambda: _SessionContext())
    monkeypatch.setattr(dependencies.repository, "get_user_by_id", AsyncMock(return_value=_user()))
    legacy = create_access_token("user-1", "owner@example.com")

    with pytest.raises(_StopAfterAuth), client.websocket_connect(f"/ws?token={legacy}"):
        pass

    activate.assert_awaited_once_with("user-1")


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


def _well_formed_token(kid: str = "rotated-key") -> str:
    """A syntactically valid RS256 token whose key id the verifier must look up."""

    def segment(value: dict[str, str]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return f"{segment({'alg': 'RS256', 'kid': kid})}.{segment({'sub': 'x'})}.c2ln"


@pytest.fixture
def identity_down(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Real verifier and provider; only the network call to identity fails."""

    async def unreachable(_self: platform.HTTPJwksProvider) -> list[object]:
        raise httpx.ConnectError("identity unreachable")

    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(platform.HTTPJwksProvider, "_fetch", unreachable)
    yield


@pytest.mark.usefixtures("identity_down")
def test_identity_outage_is_not_a_rejection_through_real_verifier(client: TestClient) -> None:
    # First attempt fails the JWKS fetch; the second lands inside the verifier's
    # refresh cooldown, which reports "unknown key" — neither may become 4001.
    assert _close_code(client, f"/ws?token={_well_formed_token()}")[0] == 1011
    assert _close_code(client, f"/ws?token={_well_formed_token()}")[0] == 1011

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {_well_formed_token()}"})
    assert response.status_code == 503


@pytest.mark.usefixtures("identity_down")
def test_malformed_token_is_still_rejected_during_outage(client: TestClient) -> None:
    # Malformed tokens fail before any key lookup, so no fetch has failed yet.
    assert _close_code(client, "/ws?token=not-a-jwt")[0] == 4001
