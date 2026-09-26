"""Fenton Identity access-token verification and CodeMonet user mapping."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
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


class IdentityUnavailableError(RuntimeError):
    """The identity authority's keys are unavailable; this is not an auth verdict."""


class HTTPJwksProvider:
    """Fetch public signing keys from the shared identity authority."""

    def __init__(self, url: str) -> None:
        self._url = url
        self.last_fetch_failed = False

    async def fetch_jwks(self) -> list[RSAJsonWebKey]:
        try:
            keys = await self._fetch()
        except Exception:
            self.last_fetch_failed = True
            raise
        self.last_fetch_failed = False
        return keys

    async def _fetch(self) -> list[RSAJsonWebKey]:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(self._url)
            response.raise_for_status()
        payload = response.json()
        keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(keys, list):
            raise ValueError("identity JWKS response is invalid")
        return [RSAJsonWebKey(**key) for key in keys if isinstance(key, dict)]


@lru_cache(maxsize=1)
def jwks_provider() -> HTTPJwksProvider:
    """Process-local JWKS provider; its fetch health gates negative verdicts."""
    return HTTPJwksProvider(settings.identity_jwks_url)


@lru_cache(maxsize=1)
def jwks_cache() -> MemoryJwksCache:
    """Process-local key cache shared with the verifier."""
    return MemoryJwksCache()


@lru_cache(maxsize=1)
def access_token_verifier() -> RS256AccessTokenVerifier:
    """Build the process-local verifier and bounded JWKS cache."""
    return RS256AccessTokenVerifier(
        configuration=AccessTokenVerifierConfiguration(
            issuer=settings.identity_issuer,
            audience=settings.identity_audience,
            client_id=settings.identity_client_id,
        ),
        jwks=jwks_cache(),
        provider=jwks_provider(),
    )


def _signing_key_unavailable(token: str) -> bool:
    """True when the token names a key we lack and the last attempt to fetch keys failed."""
    kid = _header_kid(token)
    return (
        kid is not None and jwks_cache().key_for(kid) is None and jwks_provider().last_fetch_failed
    )


def _header_kid(token: str) -> str | None:
    header_segment = token.split(".", 1)[0]
    try:
        padded = header_segment + "=" * (-len(header_segment) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded))
    except (binascii.Error, ValueError):
        return None
    kid = header.get("kid") if isinstance(header, dict) else None
    return kid if isinstance(kid, str) and kid else None


def platform_subject_for_email(email: str) -> str:
    """Return the current platform seed identity for an application-owned email."""
    normalized = email.strip().casefold()
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"owner-{digest}"


async def user_for_platform_token(token: str) -> User | None:
    """Verify a platform token and map its subject to the existing domain user.

    Raises IdentityUnavailableError instead of rejecting when this token's
    signing key could not be obtained because the authority's key fetch failed:
    the verifier reports that (and unknown keys during its refresh cooldown) as
    an invalid token, and a rejection makes clients discard valid sessions.
    Tokens that fail against a cached key are always rejected.
    """
    try:
        claims = await access_token_verifier().verify(token)
    except InvalidAccessToken as error:
        if _signing_key_unavailable(token):
            raise IdentityUnavailableError("identity keys unavailable") from error
        return None
    if claims.household_id != settings.identity_household_id:
        return None

    async with get_session() as session:
        users = await repository.list_users(session)
    matches = [
        user for user in users if platform_subject_for_email(user.email) == claims.subject_id
    ]
    return matches[0] if len(matches) == 1 else None
