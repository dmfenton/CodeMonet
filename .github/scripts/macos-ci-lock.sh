#!/usr/bin/env bash
# Shared macOS CI lock, used by ci.yml's iOS job and testflight.yml's
# build-ios job so only one Xcode build runs at a time under a given
# self-hosted macOS account.
#
# macOS has no flock(1) by default, so exclusivity comes from mkdir's
# atomicity instead: creating a directory is atomic, so exactly one
# concurrent `mkdir` call can succeed. The lock directory and its `owner`
# file keep the same name and format garden's workflows already use
# (~/.fenton-ci-macos.lock, an `owner` file inside it), so a lock held by
# a garden job is recognized and respected here, and vice versa.
#
# Staleness: if the runner that acquired the lock is terminated or
# power-cycled before its cleanup step runs, the lock directory is never
# removed and every later job would wait forever on an owner that no
# longer exists. This script also stamps an `acquired_at` file (epoch
# seconds) and, once a lock has been held longer than `stale_seconds`
# (longer than any job that can legitimately hold it, plus margin),
# treats it as abandoned and reclaims it. A garden-held lock predates
# this file, so its age falls back to the lock directory's own mtime.
#
# Reclaiming is rename-then-verify-then-remove: `mv` is atomic, so only
# one waiter can rename the directory away, and the renamed copy is only
# deleted if it is the same generation (inode + owner) that was judged
# stale; a lock re-acquired in between is moved straight back.
#
# Usage:
#   macos-ci-lock.sh acquire <owner> <wait_seconds> <stale_seconds>
#   macos-ci-lock.sh release <owner>

set -euo pipefail

LOCK_DIR="$HOME/.fenton-ci-macos.lock"
POLL_INTERVAL_SECONDS=10

lock_age_seconds() {
  local now acquired_at dir_mtime
  now="$(date +%s)"
  if [[ -f "$LOCK_DIR/acquired_at" ]]; then
    acquired_at="$(cat "$LOCK_DIR/acquired_at" 2>/dev/null || echo "")"
    if [[ "$acquired_at" =~ ^[0-9]+$ ]]; then
      echo $(( now - acquired_at ))
      return
    fi
  fi
  # No timestamp file: either a garden job holds the lock, or it predates
  # this script. Fall back to the lock directory's own mtime.
  dir_mtime="$(stat -f %m "$LOCK_DIR" 2>/dev/null || echo "$now")"
  echo $(( now - dir_mtime ))
}

# Identity of one lock acquisition: a released-and-reacquired lock is a new
# directory (new inode) with a new owner line.
lock_generation() {
  local dir="$1"
  printf '%s:%s' "$(stat -f %i "$dir" 2>/dev/null || echo none)" "$(cat "$dir/owner" 2>/dev/null || true)"
}

reclaim_stale_lock() {
  local expected="$1" stale_path="$LOCK_DIR.stale.$$"
  # Atomic: at most one racing process can rename the directory away.
  mv "$LOCK_DIR" "$stale_path" 2>/dev/null || return 1
  # The owner may have released and a new job re-acquired between the age
  # check and the rename; only delete the generation that was judged stale.
  if [[ "$(lock_generation "$stale_path")" == "$expected" ]]; then
    rm -rf "$stale_path"
    return 0
  fi
  if ! mv "$stale_path" "$LOCK_DIR" 2>/dev/null; then
    echo "::warning::moved a fresh macOS CI lock during reclaim and could not restore it; left at $stale_path"
  fi
  return 1
}

acquire() {
  local owner="$1" wait_seconds="$2" stale_seconds="$3"
  local waited=0 age held_by generation

  while true; do
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      printf '%s\n' "$owner" > "$LOCK_DIR/owner"
      date +%s > "$LOCK_DIR/acquired_at"
      return 0
    fi

    generation="$(lock_generation "$LOCK_DIR")"
    held_by="$(cat "$LOCK_DIR/owner" 2>/dev/null || echo unknown)"
    age="$(lock_age_seconds)"

    if (( age > stale_seconds )); then
      echo "::warning::macOS CI lock held ${age}s (> ${stale_seconds}s stale threshold) by $held_by; reclaiming as abandoned"
      reclaim_stale_lock "$generation" || true
      # Whether we won the reclaim race or lost it to another waiter,
      # loop back around and retry the mkdir / re-check staleness.
      continue
    fi

    if (( waited >= wait_seconds )); then
      echo "::error::Timed out after ${wait_seconds}s waiting for macOS CI lock held by $held_by"
      return 1
    fi

    if (( waited % 60 == 0 )); then
      echo "Waiting for shared macOS CI lock held by $held_by (age ${age}s, waited ${waited}s of ${wait_seconds}s budget)"
    fi
    sleep "$POLL_INTERVAL_SECONDS"
    waited=$(( waited + POLL_INTERVAL_SECONDS ))
  done
}

release() {
  local owner="$1"
  if [[ "$(cat "$LOCK_DIR/owner" 2>/dev/null || true)" == "$owner" ]]; then
    rm -f "$LOCK_DIR/owner" "$LOCK_DIR/acquired_at"
    rmdir "$LOCK_DIR" 2>/dev/null || rm -rf "$LOCK_DIR"
  fi
}

case "${1:-}" in
  acquire)
    [[ $# -eq 4 ]] || { echo "usage: $0 acquire <owner> <wait_seconds> <stale_seconds>" >&2; exit 2; }
    acquire "$2" "$3" "$4"
    ;;
  release)
    [[ $# -eq 2 ]] || { echo "usage: $0 release <owner>" >&2; exit 2; }
    release "$2"
    ;;
  *)
    echo "usage: $0 {acquire|release} ..." >&2
    exit 2
    ;;
esac
