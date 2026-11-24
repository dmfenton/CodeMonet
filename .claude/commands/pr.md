---
description: Create PR, run code review, request the Codex review, take it through the gate to merge
argument-hint: <optional: title or PR number>
---

Create a Pull Request with automated code review and issue resolution.

## Arguments

The argument `$ARGUMENTS` can be:

- Empty: Create a PR for the current branch
- A PR number: Review an existing PR (e.g., `123`)
- A title: Create a PR with this title

## Process

### 1. Check Prerequisites

```bash
git status
git log Main..HEAD --oneline
```

Verify:

- `make test` passed once on the final content (see "Local test cadence" in
  `CLAUDE.md`; don't rerun it for a docs-only change)
- If `server/` changed: `make sandbox-e2e` and `make sandbox-tests` pass (paint
  programs run confined only on Linux, so macOS test runs cannot catch sandbox
  failures)
- Working directory is clean
- Current branch is not Main
- There are commits ahead of Main

### 2. Push and Create PR

```bash
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git push -u origin "$CURRENT_BRANCH"

# Create PR (or checkout existing if $ARGUMENTS is a number)
gh pr create --title "${ARGUMENTS:-$CURRENT_BRANCH}" --body "## Summary
[To be filled after code review]

## Test Plan
- [ ] Tests pass
- [ ] Manual verification
"
```

### 3. Run Code Review

Launch the `code-reviewer` agent to perform a full review.

### 4. Fix Issues

For each issue identified:

1. **Critical**: Must fix before proceeding
2. **Important**: Should fix, ask if any should be skipped
3. **Nits**: Apply if straightforward

After fixes:

```bash
git add -A
git commit -m "fix: Address code review feedback"
git push
```

### 5. Re-run Review

Repeat steps 3-4 until no Critical or Important issues remain.

### 6. Update PR Description

```bash
gh pr edit --body "## Summary
[Final summary]

## Changes
- [Bullet points]

## Test Plan
- [x] Lint passes
- [x] Type check passes
- [x] Tests pass

## Code Review
- [x] Automated review completed
- [x] All critical/important issues resolved
"
```

### 7. Request the Codex review and land

The PR is open from step 2 and the local code review from steps 3 to 6 is done. Follow
`.github/review-kit/review-gate.md`, the shared procedure synced from Platform's `tools/review-kit`,
with CodeMonet's review rule (`CLAUDE.md`, Codex Review Gate):

- Address every Codex comment regardless of severity: fix it (or reply why not), reply on the
  thread, and resolve it. P0/P1 findings block the gate; P2/P3 are advisory but still get a reply.
- Merge when live `reviewThreads` shows zero unresolved Codex threads.

`scripts/request-review.py`, `scripts/audit-python-dependencies.sh`, the gate caller and that
procedure are synced copies: never edit them here; change the kit in Platform and sync.

### 8. Report

Output the PR URL and its gate state for the user.
