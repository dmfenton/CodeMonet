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
# Reclaiming is rename-then-remove, not remove-then-mkdir, so two
# waiters racing to reclaim the same stale lock can't both succeed:
# `mv` is atomic, so only one of them can rename the directory away.
# That process then recreates the lock fresh and deletes the old
# (renamed) copy; the other process's `mv` fails, so it just loops and
# re-checks the now-fresh lock like any other waiter.
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

reclaim_stale_lock() {
  local stale_path="$LOCK_DIR.stale.$$"
  # Atomic: at most one racing process can rename the directory away.
  # A loser's `mv` fails and falls through to the normal wait/retry loop.
  if mv "$LOCK_DIR" "$stale_path" 2>/dev/null; then
    rm -rf "$stale_path"
    return 0
  fi
  return 1
}

acquire() {
  local owner="$1" wait_seconds="$2" stale_seconds="$3"
  local waited=0 age held_by

  while true; do
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      printf '%s\n' "$owner" > "$LOCK_DIR/owner"
      date +%s > "$LOCK_DIR/acquired_at"
      return 0
    fi

    held_by="$(cat "$LOCK_DIR/owner" 2>/dev/null || echo unknown)"
    age="$(lock_age_seconds)"

    if (( age > stale_seconds )); then
      echo "::warning::macOS CI lock held ${age}s (> ${stale_seconds}s stale threshold) by $held_by; reclaiming as abandoned"
      reclaim_stale_lock || true
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
