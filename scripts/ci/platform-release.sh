#!/usr/bin/env bash
# Runs Platform's shared release step (dmfenton/platform .github/actions/deploy-release) from this
# public repository, which cannot `uses:` an action in the private Platform repository. It fetches
# Platform at the one reviewed commit below with the job's Platform git access
# (scripts/ci/platform-git-access.sh) and runs the action's own script with the same inputs,
# passed as the action's environment variables (DEPLOY_DOCUMENT, DEPLOY_PARAMETERS, ...; see that
# action's README).
# Usage: DEPLOY_DOCUMENT=... DEPLOY_PARAMETERS=... bash scripts/ci/platform-release.sh
set -euo pipefail
PLATFORM_RELEASE_COMMIT=d2de56b3f61ffd44b8a20703f7d25718d587102d # platform#513
dest="$RUNNER_TEMP/platform-release-$PLATFORM_RELEASE_COMMIT"
if [[ ! -d "$dest" ]]; then
  git init -q "$dest"
  git -C "$dest" fetch -q --depth 1 https://github.com/dmfenton/platform.git "$PLATFORM_RELEASE_COMMIT"
  git -C "$dest" checkout -q --detach FETCH_HEAD
fi
PLATFORM_ROOT="$dest" exec python3 -I "$dest/.github/actions/deploy-release/deploy_release.py"
