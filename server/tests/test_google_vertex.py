"""Gemini credential selection: keyless Vertex in production, API key locally."""

from __future__ import annotations

from pathlib import Path

import pytest
from google.auth import identity_pool

from code_monet import google_vertex
from code_monet.config import settings


class TestGeminiClient:
    def test_identity_token_selects_keyless_vertex(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        token = tmp_path / "google-identity-token"
        token.write_text("header.claims.signature\n", encoding="utf-8")
        monkeypatch.setattr(settings, "google_identity_token_file", str(token))
        monkeypatch.setattr(settings, "google_api_key", "must-not-be-used")

        client = google_vertex.gemini_client()

        assert client.vertexai
        api = client._api_client
        assert api.project == "scientific-axle-606"
        assert api.location == "global"
        assert api.api_key is None
        credentials = api._credentials
        assert isinstance(credentials, identity_pool.Credentials)
        assert credentials._audience == settings.google_sts_audience
        assert credentials._token_url == "https://sts.googleapis.com/v1/token"
        # The rotated token is read again on every refresh, without its newline.
        assert credentials.retrieve_subject_token(None) == "header.claims.signature"
        token.write_text("header.rotated.signature\n", encoding="utf-8")
        assert credentials.retrieve_subject_token(None) == "header.rotated.signature"

    def test_malformed_identity_token_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        token = tmp_path / "google-identity-token"
        token.write_text("not-a-jwt\n", encoding="utf-8")
        monkeypatch.setattr(settings, "google_identity_token_file", str(token))

        credentials = google_vertex.gemini_client()._api_client._credentials
        assert isinstance(credentials, identity_pool.Credentials)

        with pytest.raises(RuntimeError, match="malformed"):
            credentials.retrieve_subject_token(None)

    def test_api_key_is_the_local_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "google_identity_token_file", "")
        monkeypatch.setattr(settings, "google_api_key", "local-dev-key")

        client = google_vertex.gemini_client()

        assert not client.vertexai
        assert google_vertex.gemini_available()

    def test_no_credential_disables_imagine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "google_identity_token_file", "")
        monkeypatch.setattr(settings, "google_api_key", "")

        assert not google_vertex.gemini_available()
        with pytest.raises(RuntimeError, match="No Gemini credential"):
            google_vertex.gemini_client()
