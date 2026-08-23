"""Shared Fenton Identity resource-server tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fenton_identity import InvalidAccessToken

from code_monet.auth import dependencies, platform, routes
from code_monet.config import settings
from code_monet.db import User


class _Response:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class _HTTPClient:
    response: _Response

    def __init__(self, *, timeout: int) -> None:
        assert timeout == 5

    async def __aenter__(self) -> "_HTTPClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, url: str) -> _Response:
        assert url == "https://identity.example/.well-known/jwks.json"
        return self.response


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_: object) -> None:
        return None


def test_platform_subject_is_normalized_and_stable() -> None:
    assert platform.platform_subject_for_email(" Owner@Example.com ") == (
        platform.platform_subject_for_email("owner@example.com")
    )
    assert platform.platform_subject_for_email("owner@example.com").startswith("owner-")


@pytest.mark.asyncio
async def test_jwks_provider_accepts_empty_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _HTTPClient.response = _Response({"keys": []})
    monkeypatch.setattr(platform.httpx, "AsyncClient", _HTTPClient)

    provider = platform.HTTPJwksProvider("https://identity.example/.well-known/jwks.json")

    assert await provider.fetch_jwks() == []


@pytest.mark.asyncio
async def test_jwks_provider_rejects_invalid_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _HTTPClient.response = _Response({"keys": "invalid"})
    monkeypatch.setattr(platform.httpx, "AsyncClient", _HTTPClient)

    provider = platform.HTTPJwksProvider("https://identity.example/.well-known/jwks.json")

    with pytest.raises(ValueError, match="JWKS response"):
        await provider.fetch_jwks()


def test_access_token_verifier_is_cached() -> None:
    platform.access_token_verifier.cache_clear()

    first = platform.access_token_verifier()

    assert platform.access_token_verifier() is first
    platform.access_token_verifier.cache_clear()


@pytest.mark.asyncio
async def test_invalid_platform_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = SimpleNamespace(verify=AsyncMock(side_effect=InvalidAccessToken("invalid")))
    monkeypatch.setattr(platform, "access_token_verifier", lambda: verifier)

    assert await platform.user_for_platform_token("invalid") is None


@pytest.mark.asyncio
async def test_platform_token_maps_one_existing_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    user = User(id="user-1", email="owner@example.com", password_hash="unused", is_active=True)
    claims = SimpleNamespace(
        household_id=settings.identity_household_id,
        subject_id=platform.platform_subject_for_email(user.email),
    )
    verifier = SimpleNamespace(verify=AsyncMock(return_value=claims))
    monkeypatch.setattr(platform, "access_token_verifier", lambda: verifier)
    monkeypatch.setattr(platform, "get_session", lambda: _SessionContext())
    monkeypatch.setattr(platform.repository, "list_users", AsyncMock(return_value=[user]))

    assert await platform.user_for_platform_token("valid") is user


@pytest.mark.asyncio
async def test_wrong_household_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = SimpleNamespace(
        verify=AsyncMock(return_value=SimpleNamespace(household_id="other", subject_id="owner-x"))
    )
    monkeypatch.setattr(platform, "access_token_verifier", lambda: verifier)

    assert await platform.user_for_platform_token("valid") is None


@pytest.mark.asyncio
async def test_production_dependency_uses_platform_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = User(id="user-1", email="owner@example.com", password_hash="unused")
    resolver = AsyncMock(return_value=expected)
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(dependencies, "user_for_platform_token", resolver)

    assert await dependencies._authenticated_user("token") is expected
    resolver.assert_awaited_once_with("token")


def test_legacy_auth_routes_are_hidden_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "dev_mode", False)

    with pytest.raises(HTTPException) as error:
        routes.require_legacy_auth()

    assert error.value.status_code == 404
