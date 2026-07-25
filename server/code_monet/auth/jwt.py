"""JWT token utilities."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError

from code_monet.config import settings


class TokenError(Exception):
    """Raised when token operations fail."""

    pass


def create_access_token(user_id: str, email: str) -> str:
    """Create a short-lived access token."""
    if not settings.jwt_secret:
        raise TokenError("JWT_SECRET not configured")

    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh token."""
    if not settings.jwt_secret:
        raise TokenError("JWT_SECRET not configured")

    expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Returns the payload if valid.
    Raises TokenError if invalid or expired.
    """
    if not settings.jwt_secret:
        raise TokenError("JWT_SECRET not configured")

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except InvalidTokenError as e:
        raise TokenError(f"Invalid token: {e}") from e


def get_user_id_from_token(token: str, expected_type: str = "access") -> str:
    """Extract user ID from token after validation.

    Args:
        token: The JWT token string
        expected_type: Expected token type ("access" or "refresh")

    Returns:
        The user ID (UUID string) from the token

    Raises:
        TokenError: If token is invalid or wrong type
    """
    payload = decode_token(token)

    token_type = payload.get("type")
    if token_type != expected_type:
        raise TokenError(f"Expected {expected_type} token, got {token_type}")

    user_id = payload.get("sub")
    if not user_id:
        raise TokenError("Token missing user ID")

    return user_id
