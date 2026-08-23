"""Fenton Identity access-token verification and CodeMonet user mapping."""

from __future__ import annotations

import hashlib
from functools import lru_cache

import httpx
from fenton_identity import (
    AccessTokenVerifierConfiguration,
    InvalidAccessToken,
    MemoryJwksCache,
    RS256AccessTokenVerifier,
    RSAJsonWebKey,
)

from code_monet.config import settings
from code_monet.db import User, get_session, repository


class HTTPJwksProvider:
    """Fetch public signing keys from the shared identity authority."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def fetch_jwks(self) -> list[RSAJsonWebKey]:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(self._url)
            response.raise_for_status()
        payload = response.json()
        keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(keys, list):
            raise ValueError("identity JWKS response is invalid")
        return [RSAJsonWebKey(**key) for key in keys if isinstance(key, dict)]


@lru_cache(maxsize=1)
def access_token_verifier() -> RS256AccessTokenVerifier:
    """Build the process-local verifier and bounded JWKS cache."""
    return RS256AccessTokenVerifier(
        configuration=AccessTokenVerifierConfiguration(
            issuer=settings.identity_issuer,
            audience=settings.identity_audience,
            client_id=settings.identity_client_id,
        ),
        jwks=MemoryJwksCache(),
        provider=HTTPJwksProvider(settings.identity_jwks_url),
    )


def platform_subject_for_email(email: str) -> str:
    """Return the current platform seed identity for an application-owned email."""
    normalized = email.strip().casefold()
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"owner-{digest}"


async def user_for_platform_token(token: str) -> User | None:
    """Verify a platform token and map its subject to the existing domain user."""
    try:
        claims = await access_token_verifier().verify(token)
    except InvalidAccessToken:
        return None
    if claims.household_id != settings.identity_household_id:
        return None

    async with get_session() as session:
        users = await repository.list_users(session)
    matches = [
        user for user in users if platform_subject_for_email(user.email) == claims.subject_id
    ]
    return matches[0] if len(matches) == 1 else None
