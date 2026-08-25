#!/usr/bin/env bash
set -Eeuo pipefail

if (($# != 1)); then
  echo "Usage: publish-tenant-manifest.sh <app-id>" >&2
  exit 2
fi

app_id=$1
manifest=fenton-platform.tenant.json
repository=${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}
commit=${GITHUB_SHA:?GITHUB_SHA is required}
ref=${GITHUB_REF:?GITHUB_REF is required}
region=${AWS_REGION:-us-east-1}
instance_id=${FENTON_PLATFORM_INSTANCE_ID:?FENTON_PLATFORM_INSTANCE_ID is required}
parameter_name="/fenton-platform/prod/app-manifests/${app_id}"
if [[ "$ref" != refs/heads/main ]]; then
  echo "Tenant manifests can be published only from main" >&2
  exit 2
fi

payload_file=$(mktemp)
trap 'rm -f "$payload_file"' EXIT
python3 - "$manifest" "$app_id" "$repository" "$commit" >"$payload_file" <<'PY'
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
app_id = sys.argv[2]
repository = sys.argv[3]
commit = sys.argv[4]
if re.fullmatch(r"[a-z][a-z0-9-]{0,31}", app_id) is None:
    raise SystemExit("app ID is invalid")
if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
    raise SystemExit("GITHUB_SHA must be a full Git commit SHA")
raw = path.read_bytes()
manifest = json.loads(raw)
if manifest.get("schema_version") != 1 or manifest.get("app_id") != app_id:
    raise SystemExit("manifest identity does not match publisher")
if "source" in manifest or "runtime" in manifest:
    raise SystemExit("app manifest cannot own source or runtime metadata")
manifest["source"] = {
    "repository": repository,
    "commit": commit,
    "sha256": hashlib.sha256(raw).hexdigest(),
}
print(json.dumps(manifest, separators=(",", ":"), sort_keys=True))
PY

payload=$(<"$payload_file")
if [[ ${FENTON_TENANT_MANIFEST_RENDER_ONLY:-false} == true ]]; then
  printf '%s\n' "$payload"
  exit 0
fi
: "${GH_TOKEN:?GH_TOKEN is required}"
digest=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["source"]["sha256"])' "$payload_file")
main_manifest_digest() {
  gh api -H "Accept: application/vnd.github.raw+json" \
    "repos/${repository}/contents/${manifest}?ref=main" \
    | shasum -a 256 | awk '{print $1}'
}
if [[ "$(main_manifest_digest)" != "$digest" ]]; then
  echo "Refusing to publish a manifest that differs from current main" >&2
  exit 1
fi
aws ssm put-parameter \
  --region "$region" \
  --name "$parameter_name" \
  --type String \
  --overwrite \
  --value "$payload" >/dev/null

command_id=$(aws ssm send-command \
  --region "$region" \
  --instance-ids "$instance_id" \
  --document-name Compute-RefreshFentonTenantCatalog \
  --parameters "AppId=${app_id},Commit=${commit},Digest=${digest}" \
  --comment "Published ${app_id} tenant manifest at ${commit}" \
  --query Command.CommandId \
  --output text)

status=Pending
for _ in $(seq 1 90); do
  status=$(aws ssm get-command-invocation \
    --region "$region" \
    --command-id "$command_id" \
    --instance-id "$instance_id" \
    --query Status \
    --output text 2>/dev/null || echo Pending)
  case "$status" in
    Success) break ;;
    Failed|Cancelled|TimedOut)
      aws ssm get-command-invocation \
        --region "$region" \
        --command-id "$command_id" \
        --instance-id "$instance_id"
      exit 1
      ;;
  esac
  sleep 2
done
if [[ "$status" != Success ]]; then
  echo "Catalog refresh timed out with status $status" >&2
  exit 1
fi
if [[ "$(main_manifest_digest)" != "$digest" ]]; then
  echo "Main manifest changed during activation; dispatch the current main release" >&2
  exit 1
fi
