#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
audit_requirements=$(mktemp)
trap 'rm -f "$audit_requirements"' EXIT

cd "$project_root/server"
uv export \
  --frozen \
  --no-dev \
  --no-emit-project \
  --no-emit-package fenton-platform \
  --output-file "$audit_requirements" \
  >/dev/null

uv run --frozen --extra dev pip-audit \
  --requirement "$audit_requirements" \
  --require-hashes \
  --disable-pip \
  --strict \
  --progress-spinner=off
