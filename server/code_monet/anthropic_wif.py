"""Anthropic workload-identity configuration shared by Claude runtimes."""

from __future__ import annotations

import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True, slots=True)
class AnthropicWifConfiguration:
    federation_rule_id: str
    organization_id: str
    service_account_id: str
    identity_token_file: Path
    workspace_id: str | None = None

    def __post_init__(self) -> None:
        if not self.federation_rule_id.startswith("fdrl_"):
            raise ValueError("Anthropic federation rule ID must start with fdrl_")
        try:
            uuid.UUID(self.organization_id)
        except ValueError as error:
            raise ValueError("Anthropic organization ID must be a UUID") from error
        if not self.service_account_id.startswith("svac_"):
            raise ValueError("Anthropic service account ID must start with svac_")
        if self.workspace_id is not None and not (
            self.workspace_id == "default" or self.workspace_id.startswith("wrkspc_")
        ):
            raise ValueError("Anthropic workspace ID must be default or start with wrkspc_")
        if not self.identity_token_file.is_absolute():
            raise ValueError("Anthropic identity token file must be absolute")

    def claude_environment(self) -> dict[str, str]:
        values = {
            "ANTHROPIC_FEDERATION_RULE_ID": self.federation_rule_id,
            "ANTHROPIC_ORGANIZATION_ID": self.organization_id,
            "ANTHROPIC_SERVICE_ACCOUNT_ID": self.service_account_id,
            "ANTHROPIC_IDENTITY_TOKEN_FILE": str(self.identity_token_file),
        }
        if self.workspace_id is not None:
            values["ANTHROPIC_WORKSPACE_ID"] = self.workspace_id
        return values

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
    return configuration.claude_environment() if configuration is not None else {}
