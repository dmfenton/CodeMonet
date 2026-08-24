#!/usr/bin/env bash
# Prepare isolated Codex worktree dependencies without copying credentials.
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
common_dir="$(git rev-parse --git-common-dir)"
common_dir="$(cd "$root" && cd "$common_dir" && pwd)"
main="$(dirname "$common_dir")"

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

platform_source="$(dirname "$main")/fenton-platform"
platform_target="$root/vendor/fenton-platform"
platform_pin="$(tr -d '[:space:]' <"$root/fenton-platform.lock")"
platform_cache="$main/.worktrees/fenton-platform-${platform_pin:0:12}"

if [[ ! "$platform_pin" =~ ^[0-9a-f]{40}$ ]]; then
  echo "worktree-bootstrap: invalid fenton-platform.lock" >&2
  exit 1
fi

if [[ ! -e "$platform_source/.git" ]]; then
  echo "worktree-bootstrap: missing sibling fenton-platform checkout at $platform_source" >&2
  exit 1
fi

if ! git -C "$platform_source" cat-file -e "${platform_pin}^{commit}" 2>/dev/null; then
  git -C "$platform_source" fetch origin "$platform_pin"
fi

if [[ ! -e "$platform_cache" ]]; then
  mkdir -p "$(dirname "$platform_cache")"
  git -C "$platform_source" worktree add --detach "$platform_cache" "$platform_pin"
fi

if [[ "$(git -C "$platform_cache" rev-parse HEAD 2>/dev/null || true)" != "$platform_pin" ]]; then
  echo "worktree-bootstrap: invalid platform cache at $platform_cache" >&2
  exit 1
fi

mkdir -p "$(dirname "$platform_target")"
if [[ -L "$platform_target" ]]; then
  if [[ "$(readlink "$platform_target")" != "$platform_cache" ]]; then
    ln -sfn "$platform_cache" "$platform_target"
    echo "worktree-bootstrap: relinked vendor/fenton-platform -> ${platform_pin:0:12}"
  fi
elif [[ -e "$platform_target" ]]; then
  if [[ "$(git -C "$platform_target" rev-parse HEAD 2>/dev/null || true)" != "$platform_pin" ]]; then
    echo "worktree-bootstrap: vendor/fenton-platform is not the locked commit" >&2
    exit 1
  fi
else
  ln -s "$platform_cache" "$platform_target"
  echo "worktree-bootstrap: linked vendor/fenton-platform -> ${platform_pin:0:12}"
fi

if [[ ! -d "$platform_target/python" ]]; then
  echo "worktree-bootstrap: locked platform checkout does not provide python/" >&2
  exit 1
fi

if ! (cd "$root" && npm ci --legacy-peer-deps --no-audit --no-fund --loglevel=error); then
  echo "worktree-bootstrap: failed to install npm workspaces" >&2
  exit 1
fi
echo "worktree-bootstrap: ready npm workspaces"

# npm's legacy peer resolution can omit the root TypeScript peer needed by the
# shared ESLint configuration. Reuse the locked app workspace installation.
if [[ ! -e "$root/node_modules/typescript" && -d "$root/app/node_modules/typescript" ]]; then
  ln -s ../app/node_modules/typescript "$root/node_modules/typescript"
  echo "worktree-bootstrap: linked root TypeScript peer"
fi

if ! (cd "$root/server" && uv sync --frozen --extra dev --all-groups --quiet); then
  echo "worktree-bootstrap: failed to sync server" >&2
  exit 1
fi
echo "worktree-bootstrap: ready server"

(cd "$root" && npm run build -w shared --silent)
echo "worktree-bootstrap: built shared workspace"
