from __future__ import annotations

import hashlib
import json
import os
import subprocess
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


def test_tenant_manifest_publisher_adds_immutable_source() -> None:
    manifest_path = ROOT / "fenton-platform.tenant.json"
    result = subprocess.run(
        [str(ROOT / "scripts/publish-tenant-manifest.sh"), "codemonet"],
        cwd=ROOT,
        env={
            **os.environ,
            "GITHUB_REPOSITORY": "dmfenton/CodeMonet",
            "GITHUB_SHA": "c" * 40,
            "GITHUB_REF": "refs/heads/main",
            "FENTON_PLATFORM_INSTANCE_ID": "i-test",
            "FENTON_TENANT_MANIFEST_RENDER_ONLY": "true",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    published = json.loads(result.stdout)
    assert published["app_id"] == "codemonet"
    assert published["source"] == {
        "repository": "dmfenton/CodeMonet",
        "commit": "c" * 40,
        "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }
    publisher = (ROOT / "scripts/publish-tenant-manifest.sh").read_text(encoding="utf-8")
    assert '"repos/${repository}/contents/${manifest}?ref=main"' in publisher
    assert "Main manifest changed during activation" in publisher
    assert '--parameters "AppId=${app_id},Commit=${commit},Digest=${digest}"' in publisher
    assert "refresh_poll_attempts=750" in publisher
    workflow = (ROOT / ".github/workflows/publish-tenant-manifest.yml").read_text(encoding="utf-8")
    trigger = workflow.split("permissions:", maxsplit=1)[0]
    assert "workflow_dispatch:" in trigger
    assert "push:" in trigger
    assert "branches: [main]" in trigger
    for path in (
        "fenton-platform.tenant.json",
        "scripts/publish-tenant-manifest.sh",
        ".github/workflows/publish-tenant-manifest.yml",
    ):
        assert f"- '{path}'" in trigger
