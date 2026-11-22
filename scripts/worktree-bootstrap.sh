#!/usr/bin/env bash
# Prepare isolated Codex worktree dependencies without copying credentials. Platform libraries
# come from the release tag server/uv.lock records; no Platform checkout is needed.
set -euo pipefail

root="$(git rev-parse --show-toplevel)"

# Prefer an already-installed Volta Node 24 runtime when the default still
# points at an older release. CI and package.json use Node 24.
volta_node_dir=""
for candidate in "${VOLTA_HOME:-$HOME/.volta}/tools/image/node"/24.*; do
  [[ -x "$candidate/bin/node" ]] && volta_node_dir="$candidate/bin"
done
if [[ -n "$volta_node_dir" ]]; then
  export PATH="$volta_node_dir:$PATH"
fi

for tool in npm uv; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "worktree-bootstrap: $tool is required" >&2
    exit 1
  fi
done

if [[ "$(node -p 'process.versions.node.split(".")[0]')" != "24" ]]; then
  echo "worktree-bootstrap: CodeMonet requires Node 24" >&2
  exit 1
fi

if ! (cd "$root" && npm ci --legacy-peer-deps --no-audit --no-fund --loglevel=error); then
  echo "worktree-bootstrap: failed to install npm workspaces" >&2
  exit 1
fi
echo "worktree-bootstrap: ready npm workspaces"

# npm's legacy peer resolution can omit the root TypeScript peer needed by the
# shared ESLint configuration. Reuse the locked web workspace installation.
if [[ ! -e "$root/node_modules/typescript" && -d "$root/web/node_modules/typescript" ]]; then
  ln -s ../web/node_modules/typescript "$root/node_modules/typescript"
  echo "worktree-bootstrap: linked root TypeScript peer"
fi

if ! (cd "$root/server" && uv sync --frozen --extra dev --all-groups --quiet); then
  echo "worktree-bootstrap: failed to sync server" >&2
  exit 1
fi
echo "worktree-bootstrap: ready server"

(cd "$root" && npm run build -w shared --silent)
echo "worktree-bootstrap: built shared workspace"
