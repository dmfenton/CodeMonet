from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_tenant_manifest_matches_code_monet_identity_contract() -> None:
    manifest = json.loads((ROOT / "fenton-platform.tenant.json").read_text(encoding="utf-8"))
    client = manifest["oauth"]["clients"][0]
    shared_auth = (ROOT / "shared/src/auth/platform.ts").read_text(encoding="utf-8")
    ios_project = (ROOT / "ios/project.yml").read_text(encoding="utf-8")
    server_config = (ROOT / "server/code_monet/config.py").read_text(encoding="utf-8")

    assert manifest["schema_version"] == 1
    assert manifest["app_id"] == "codemonet"
    assert len(manifest["oauth"]["clients"]) == 1
    assert f"PLATFORM_CLIENT_ID = '{client['client_id']}'" in shared_auth
    assert len(client["redirect_uris"]) == 1
    assert f"PLATFORM_REDIRECT_URI = '{client['redirect_uris'][0]}'" in shared_auth
    assert f'identity_audience: str = "{client["audience"]}"' in server_config
    assert f'identity_client_id: str = "{client["client_id"]}"' in server_config
    assert f"CFBundleDisplayName: {manifest['presentation']['sign_in_name']}" in ios_project
    assert "communications" not in manifest


def test_tenant_manifest_publishes_through_platform_from_main() -> None:
    # Platform owns the publisher and its tests; this public repository runs its script from a
    # checkout of Platform pinned to a full commit.
    workflow = (ROOT / ".github/workflows/publish-tenant-manifest.yml").read_text(encoding="utf-8")
    trigger = workflow.split("permissions:", maxsplit=1)[0]
    assert "workflow_dispatch:" in trigger
    assert "push:" in trigger
    assert "branches: [main]" in trigger
    for path in ("fenton-platform.tenant.json", ".github/workflows/publish-tenant-manifest.yml"):
        assert f"- '{path}'" in trigger
    assert "repository: dmfenton/platform" in workflow
    assert re.search(r"ref: [0-9a-f]{40} ", workflow)
    assert "ssh-key: ${{ secrets.FENTON_PLATFORM_DEPLOY_KEY }}" in workflow
    assert (
        ".fenton-platform/.github/actions/publish-tenant-manifest/publish-tenant-manifest.sh codemonet"
        in workflow
    )
