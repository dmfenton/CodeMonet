"""Anthropic workload identity boundary tests."""

from pathlib import Path

import pytest

from code_monet.anthropic_wif import (
    AnthropicWifConfiguration,
    anthropic_claude_environment,
    anthropic_wif_configuration,
)
from code_monet.config import settings


def _configure(monkeypatch: pytest.MonkeyPatch, token: Path) -> None:
    monkeypatch.setattr(settings, "anthropic_federation_rule_id", "fdrl_test")
    monkeypatch.setattr(
        settings, "anthropic_organization_id", "00000000-0000-4000-8000-000000000000"
    )
    monkeypatch.setattr(settings, "anthropic_service_account_id", "svac_test")
    monkeypatch.setattr(settings, "anthropic_workspace_id", "wrkspc_test")
    monkeypatch.setattr(settings, "anthropic_identity_token_file", str(token))


def test_wif_environment_removes_static_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure(monkeypatch, tmp_path / "token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-survive")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")

    environment = anthropic_claude_environment()

    assert environment["ANTHROPIC_FEDERATION_RULE_ID"] == "fdrl_test"
    assert "ANTHROPIC_API_KEY" not in environment
    assert "ANTHROPIC_API_KEY" not in __import__("os").environ
    assert "CLAUDE_CODE_USE_BEDROCK" not in __import__("os").environ


def test_production_requires_complete_wif(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(settings, "anthropic_federation_rule_id", "")
    monkeypatch.setattr(settings, "anthropic_organization_id", "")
    monkeypatch.setattr(settings, "anthropic_service_account_id", "")

    with pytest.raises(ValueError, match="incomplete"):
        anthropic_wif_configuration()


def test_identity_token_readiness_is_bounded(tmp_path: Path) -> None:
    token = tmp_path / "identity-token"
    configuration = AnthropicWifConfiguration(
        federation_rule_id="fdrl_test",
        organization_id="00000000-0000-4000-8000-000000000000",
        service_account_id="svac_test",
        workspace_id="default",
        identity_token_file=token,
    )
    assert not configuration.identity_token_available()
    token.write_text("signed-token", encoding="utf-8")
    assert configuration.identity_token_available()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"federation_rule_id": "rule"}, "federation rule"),
        ({"organization_id": "organization"}, "organization ID"),
        ({"service_account_id": "account"}, "service account"),
        ({"workspace_id": "workspace"}, "workspace ID"),
        ({"identity_token_file": Path("relative")}, "token file"),
    ],
)
def test_wif_configuration_rejects_invalid_identifiers(
    overrides: dict[str, object], message: str, tmp_path: Path
) -> None:
    values: dict[str, object] = {
        "federation_rule_id": "fdrl_test",
        "organization_id": "00000000-0000-4000-8000-000000000000",
        "service_account_id": "svac_test",
        "workspace_id": "default",
        "identity_token_file": tmp_path / "token",
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        AnthropicWifConfiguration(**values)  # type: ignore[arg-type]


def test_development_without_wif_uses_isolated_subscription_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setattr(settings, "anthropic_federation_rule_id", "")
    monkeypatch.setattr(settings, "anthropic_organization_id", "")
    monkeypatch.setattr(settings, "anthropic_service_account_id", "")

    assert anthropic_wif_configuration() is None


def test_identity_token_rejects_oversized_file(tmp_path: Path) -> None:
    token = tmp_path / "identity-token"
    token.write_bytes(b"x" * (16 * 1024 + 1))
    configuration = AnthropicWifConfiguration(
        federation_rule_id="fdrl_test",
        organization_id="00000000-0000-4000-8000-000000000000",
        service_account_id="svac_test",
        identity_token_file=token,
    )

    assert not configuration.identity_token_available()
