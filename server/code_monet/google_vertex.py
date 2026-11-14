"""Gemini client: keyless Vertex AI in production, an API key for local development.

Production has no Google key. The host mints a 15-minute AWS outbound identity token
for the CodeMonet role with the Google workload identity provider as its audience and
mounts it read-only (Platform `refresh-codemonet-wif-token.sh`). google-auth exchanges
that token at Google STS for a federated access token, reading the file again on every
refresh, so the rotated token is always the one presented.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from google.auth import identity_pool

from code_monet.config import settings

if TYPE_CHECKING:
    from google import genai
    from google.auth.external_account import SupplierContext
    from google.auth.transport import Request

_STS_URL = "https://sts.googleapis.com/v1/token"
_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class _TokenFileSupplier(identity_pool.SubjectTokenSupplier):
    """Read the host-rotated JWT, without the trailing newline the host writes."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def get_subject_token(self, context: SupplierContext, request: Request) -> str:
        del context, request  # The token is a local file; no request context applies.
        try:
            token = self._path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError("Google workload identity token is unreadable") from exc
        if token.count(".") != 2:
            raise RuntimeError("Google workload identity token is malformed")
        return token


def gemini_available() -> bool:
    return bool(settings.google_identity_token_file or settings.google_api_key)


def gemini_client() -> genai.Client:
    """Return a client for whichever credential is configured; Vertex wins."""
    from google import genai

    if settings.google_identity_token_file:
        credentials = identity_pool.Credentials(
            audience=settings.google_sts_audience,
            subject_token_type="urn:ietf:params:oauth:token-type:jwt",
            token_url=_STS_URL,
            subject_token_supplier=_TokenFileSupplier(settings.google_identity_token_file),
            scopes=[_SCOPE],
        )
        return genai.Client(
            vertexai=True,
            project=settings.vertex_project,
            location=settings.vertex_location,
            credentials=credentials,
        )
    if settings.google_api_key:
        return genai.Client(api_key=settings.google_api_key)
    raise RuntimeError("No Gemini credential is configured")
