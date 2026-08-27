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

platform_source="$(dirname "$main")/platform.dmfenton.net"
platform_target="$root/vendor/platform.dmfenton.net"
platform_url="https://github.com/dmfenton/platform.dmfenton.net.git"
platform_pin="$(tr -d '[:space:]' <"$root/fenton-platform.lock")"

if [[ ! "$platform_pin" =~ ^[0-9a-f]{40}$ ]]; then
  echo "worktree-bootstrap: invalid fenton-platform.lock" >&2
  exit 1
fi

if [[ ! -e "$platform_source/.git" ]]; then
  echo "worktree-bootstrap: missing sibling platform.dmfenton.net checkout at $platform_source" >&2
  exit 1
fi

platform_common_dir="$(cd "$platform_source" && cd "$(git rev-parse --git-common-dir)" && pwd)"
platform_lock="$platform_common_dir/fenton-platform-bootstrap.v2.lock"
ensure_platform_checkout() {
  if ! git -C "$platform_source" cat-file -e "${platform_pin}^{commit}" 2>/dev/null; then
    git -C "$platform_source" fetch origin "$platform_pin"
  fi

  mkdir -p "$(dirname "$platform_target")"
  if [[ -L "$platform_target" ]]; then
    if ! unlink "$platform_target" && [[ -L "$platform_target" ]]; then
      echo "worktree-bootstrap: failed to replace legacy platform symlink" >&2
      exit 1
    fi
  fi
  if [[ ! -e "$platform_target" ]]; then
    if git clone --no-checkout "$platform_source" "$platform_target"; then
      git -C "$platform_target" remote set-url origin "$platform_url"
      git -C "$platform_target" checkout --detach "$platform_pin"
    fi
  fi
  for ((_attempt = 0; _attempt < 50; _attempt++)); do
    # A concurrent bootstrap may still be cloning.
    platform_actual="$(git -C "$platform_target" rev-parse HEAD 2>/dev/null || true)"
    [[ -n "$platform_actual" ]] && break
    sleep 0.1
  done

  platform_actual="$(git -C "$platform_target" rev-parse HEAD 2>/dev/null || true)"
  if [[ -z "$platform_actual" ]]; then
    echo "worktree-bootstrap: vendor/platform.dmfenton.net is not a checkout" >&2
    exit 1
  fi
  if [[ -n "$(git -C "$platform_target" status --porcelain)" ]]; then
    echo "worktree-bootstrap: vendor/platform.dmfenton.net has changes" >&2
    exit 1
  fi
  if [[ "$platform_actual" != "$platform_pin" ]]; then
    if ! git -C "$platform_target" cat-file -e "${platform_pin}^{commit}" 2>/dev/null; then
      git -C "$platform_target" fetch "$platform_source" "$platform_pin" || \
        git -C "$platform_target" fetch origin "$platform_pin" || true
    fi
    git -C "$platform_target" checkout --detach "$platform_pin" || true
  fi
  for ((_attempt = 0; _attempt < 50; _attempt++)); do
    platform_actual="$(git -C "$platform_target" rev-parse HEAD 2>/dev/null || true)"
    [[ "$platform_actual" == "$platform_pin" ]] && break
    sleep 0.1
  done
  if [[ "$platform_actual" != "$platform_pin" ]]; then
    echo "worktree-bootstrap: vendor/platform.dmfenton.net is not the locked commit" >&2
    exit 1
  fi
  echo "worktree-bootstrap: ready vendor/platform.dmfenton.net at ${platform_pin:0:12}"

  if [[ ! -d "$platform_target/python" ]]; then
    echo "worktree-bootstrap: locked platform checkout does not provide python/" >&2
    exit 1
  fi
}

if [[ ${FENTON_PLATFORM_CHECKOUT_ONLY:-false} == true ]]; then
  ensure_platform_checkout
  exit 0
fi

if command -v flock >/dev/null 2>&1; then
  flock -w 60 "$platform_lock" env FENTON_PLATFORM_CHECKOUT_ONLY=true bash "$0"
elif command -v lockf >/dev/null 2>&1; then
  lockf -t 60 "$platform_lock" env FENTON_PLATFORM_CHECKOUT_ONLY=true bash "$0"
else
  echo "worktree-bootstrap: flock or lockf is required" >&2
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
