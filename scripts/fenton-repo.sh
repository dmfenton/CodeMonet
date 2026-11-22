#!/bin/sh
# Identical thin entrypoint in each app (scripts/fenton-repo.sh), a copy of Platform's
# tools/repo-kit/adapter.sh. It runs Platform's repo kit, found in this order:
#   FENTON_REPO_KIT             a cli.py path; CI's repo-kit action sets it
#   ~/.local/bin/fenton-repo    installed once per Mac by dmfenton/machine (newest release tag)
#   a Platform checkout beside this repository (cloud sessions with Platform attached)
# With none of them, `gate` and `heavy` run the command without a stamp (behind heavy-run when the
# machine has it), `hooks install` sets core.hooksPath itself, and `check` fails in CI and is
# skipped elsewhere with a note, because CI runs it. See tools/repo-kit/README.md in dmfenton/platform.
set -eu
root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
kit=${FENTON_REPO_KIT:-}
if [ -z "$kit" ] && [ -x "$HOME/.local/bin/fenton-repo" ]; then
  exec "$HOME/.local/bin/fenton-repo" "$@"
fi
if [ -z "$kit" ]; then
  for dir in "${FENTON_PLATFORM_SOURCE:-}" "$root/../platform" "$root/../platform.dmfenton.net"; do
    if [ -n "$dir" ] && [ -f "$dir/tools/repo-kit/cli.py" ]; then
      kit="$dir/tools/repo-kit/cli.py"
      break
    fi
  done
fi
if [ -n "$kit" ]; then
  exec python3 "$kit" "$@"
fi

case "${1:-}" in
  gate | heavy)
    while [ $# -gt 0 ] && [ "$1" != "--" ]; do shift; done
    [ $# -gt 0 ] || { echo "fenton-repo: name the command after --" >&2; exit 2; }
    shift
    FENTON_GATE_HELD=1
    FENTON_GATE_SCOPE=full
    export FENTON_GATE_HELD FENTON_GATE_SCOPE
    if [ -z "${HEAVY_RUN_HELD:-}" ] && [ -x "$HOME/.local/bin/heavy-run" ]; then
      exec "$HOME/.local/bin/heavy-run" --label fenton-repo -- "$@"
    fi
    exec "$@"
    ;;
  hooks)
    if [ "${2:-}" = install ] && [ -n "${3:-}" ]; then
      chmod +x "$root/$3"/* 2>/dev/null || true
      exec git -C "$root" config core.hooksPath "$3"
    fi
    [ "$(git -C "$root" config --get core.hooksPath || true)" = "${3:-}" ] && exit 0
    echo "fenton-repo: core.hooksPath is not ${3:-}; run scripts/fenton-repo.sh hooks install ${3:-}" >&2
    exit 1
    ;;
  *)
    if [ -n "${CI:-}" ]; then
      echo "fenton-repo: the repo kit is not available; add dmfenton/platform's repo-kit action to this job" >&2
      exit 1
    fi
    echo "fenton-repo: no repo kit on this machine; skipped '$*' (CI runs it)" >&2
    exit 0
    ;;
esac
