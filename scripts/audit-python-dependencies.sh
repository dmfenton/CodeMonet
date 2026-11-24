#!/usr/bin/env bash
# Managed by dmfenton/platform tools/review-kit: change the canonical file there and sync; never edit this copy.
#
# Audit one uv project's locked dependencies for known vulnerabilities.
#   scripts/audit-python-dependencies.sh <uv project dir> [uv export options, e.g. --no-dev]
# The project itself, its workspace members and Platform's own libraries (git sources, audited
# in Platform) are left out; everything else in the lock is checked against its pinned hashes.
set -euo pipefail

if [ "$#" -lt 1 ] || [ ! -f "$1/uv.lock" ]; then
  echo "Usage: $0 <uv project dir with a uv.lock> [uv export options]" >&2
  exit 2
fi
project=$1
shift

audit_requirements=$(mktemp)
trap 'rm -f "$audit_requirements"' EXIT

uv export --project "$project" --frozen --no-emit-workspace \
  --no-emit-package fenton-platform \
  --no-emit-package fenton-communications \
  --no-emit-package fenton-identity-service \
  "$@" --output-file "$audit_requirements" >/dev/null

uvx --from pip-audit==2.10.1 pip-audit \
  --requirement "$audit_requirements" \
  --require-hashes \
  --disable-pip \
  --strict \
  --progress-spinner=off
