"""Anthropic workload-identity configuration shared by Claude runtimes."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from fenton_agent import ClaudeFederationProfile, configure_claude_federation_profile

from code_monet.config import settings

_SHADOW_CREDENTIALS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_IDENTITY_TOKEN",
        "ANTHROPIC_PROFILE",
        "ANTHROPIC_WORKSPACE_ID",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_FOUNDRY",
        "CLAUDE_CODE_USE_MANTLE",
        "CLAUDE_CODE_USE_VERTEX",
    }
)


class AnthropicWifConfiguration(ClaudeFederationProfile):
    def identity_token_available(self) -> bool:
        try:
            token = self.identity_token_file.stat()
        except OSError:
            return False
        return (
            stat.S_ISREG(token.st_mode)
            and 0 < token.st_size <= 16 * 1024
            and os.access(self.identity_token_file, os.R_OK)
        )


def anthropic_wif_configuration() -> AnthropicWifConfiguration | None:
    """Build the WIF contract; development may use isolated Claude subscription auth."""
    for key in _SHADOW_CREDENTIALS:
        os.environ.pop(key, None)
    required = (
        settings.anthropic_federation_rule_id,
        settings.anthropic_organization_id,
        settings.anthropic_service_account_id,
    )
    if not any(required) and settings.dev_mode:
        return None
    if not all(required):
        raise ValueError("Anthropic workload identity configuration is incomplete")
    workspace = settings.anthropic_workspace_id or None
    return AnthropicWifConfiguration(
        federation_rule_id=settings.anthropic_federation_rule_id,
        organization_id=settings.anthropic_organization_id,
        service_account_id=settings.anthropic_service_account_id,
        identity_token_file=Path(settings.anthropic_identity_token_file),
        workspace_id=workspace,
    )


def anthropic_claude_environment() -> dict[str, str]:
    configuration = anthropic_wif_configuration()
    if configuration is None:
        return {}
    return configure_claude_federation_profile(
        configuration,
        config_directory=Path(settings.anthropic_config_directory),
    )
