"""JWT utility tests."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from code_monet.auth.jwt import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_user_id_from_token,
)
from code_monet.config import settings


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-at-least-32-bytes-long")


def test_access_token_round_trip() -> None:
    token = create_access_token("user-1", "user@example.com")

    payload = decode_token(token)

    assert payload["sub"] == "user-1"
    assert payload["email"] == "user@example.com"
    assert payload["type"] == "access"
    assert get_user_id_from_token(token) == "user-1"


def test_refresh_token_enforces_expected_type() -> None:
    token = create_refresh_token("user-1")

    assert get_user_id_from_token(token, expected_type="refresh") == "user-1"
    with pytest.raises(TokenError, match="Expected access token"):
        get_user_id_from_token(token)


def test_decode_rejects_expired_token() -> None:
    token = jwt.encode(
        {
            "sub": "user-1",
            "type": "access",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenError, match="Invalid token"):
        decode_token(token)


def test_token_creation_requires_configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "")

    with pytest.raises(TokenError, match="JWT_SECRET not configured"):
        create_access_token("user-1", "user@example.com")
    with pytest.raises(TokenError, match="JWT_SECRET not configured"):
        create_refresh_token("user-1")
    with pytest.raises(TokenError, match="JWT_SECRET not configured"):
        decode_token("token")


def test_token_requires_user_id() -> None:
    token = jwt.encode(
        {
            "type": "access",
            "exp": datetime.now(UTC) + timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenError, match="Token missing user ID"):
        get_user_id_from_token(token)
