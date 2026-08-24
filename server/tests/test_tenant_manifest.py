from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_tenant_manifest_matches_code_monet_identity_contract() -> None:
    manifest = json.loads((ROOT / "fenton-platform.tenant.json").read_text(encoding="utf-8"))
    client = manifest["oauth"]["clients"][0]
    shared_auth = (ROOT / "shared/src/auth/platform.ts").read_text(encoding="utf-8")
    app_config = (ROOT / "app/app.config.js").read_text(encoding="utf-8")
    server_config = (ROOT / "server/code_monet/config.py").read_text(encoding="utf-8")

    assert manifest["schema_version"] == 1
    assert manifest["app_id"] == "codemonet"
    assert len(manifest["oauth"]["clients"]) == 1
    assert f"PLATFORM_CLIENT_ID = '{client['client_id']}'" in shared_auth
    assert len(client["redirect_uris"]) == 1
    assert f"PLATFORM_REDIRECT_URI = '{client['redirect_uris'][0]}'" in shared_auth
    assert f'identity_audience: str = "{client["audience"]}"' in server_config
    assert f'identity_client_id: str = "{client["client_id"]}"' in server_config
    assert f"name: '{manifest['presentation']['sign_in_name']}'" in app_config
    assert "communications" not in manifest
