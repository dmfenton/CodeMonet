#!/usr/bin/env bash
# Builds server/Dockerfile with the Platform library commit that server/uv.lock records.
# The image fetches nothing private itself: this script fetches that commit (and its release tag)
# into a throwaway local repository with whatever git access this machine or job already has (the
# laptop's GitHub credential, CI's scripts/ci/platform-git-access.sh), and passes it as the
# `platform-src` build context. uv inside the build reads it through a URL rewrite and still
# verifies the exact commit in uv.lock. No key or token reaches the image.
# Usage: scripts/docker-build.sh [docker build arguments...]   (the context is the repo root)
set -euo pipefail
root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
url="https://github.com/dmfenton/platform.git"
commits="$(grep -oE "git = \"${url}\?[^\"]*#[0-9a-f]{40}\"" "$root/server/uv.lock" | sed -E 's/.*#([0-9a-f]{40})"/\1/' | sort -u)"
if [[ "$(printf '%s\n' "$commits" | grep -c .)" -ne 1 ]]; then
  echo "docker-build: server/uv.lock must record exactly one Platform commit, found: ${commits:-none}" >&2
  exit 1
fi
src="$(mktemp -d "${TMPDIR:-/tmp}/platform-src.XXXXXX")"
trap 'rm -rf -- "$src"' EXIT
git init -q "$src"
git -C "$src" fetch -q --tags "$url" "$commits"
git -C "$src" cat-file -e "$commits^{commit}"
exec docker build --build-context platform-src="$src" -f "$root/server/Dockerfile" "$@" "$root"
