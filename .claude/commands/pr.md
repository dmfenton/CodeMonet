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

This part is the same in every repository that uses `dmfenton/codex-review-gate`. Codex does not
review drafts, and marking a PR ready has not reliably started a review, so the review is always
requested explicitly, right after the PR is ready.

1. The PR is open from step 2 and the local code review from steps 3 to 6 is done.
2. When validation is green and the change is complete, mark it ready and immediately request the
   review. `gh pr ready <PR>` uses GraphQL, which Claude cloud sessions cannot reach; there use
   `gh api -X POST repos/<owner>/<repo>/pulls/<PR>/ccr/ready_for_review`. Then:
   `python3 scripts/request-review.py <PR> --request`
   Without `--request` the script only reports whether a request is allowed. Never post
   `@codex review` by hand: the script refuses a draft, a head that already has a review, a review
   that is running or pending, and a third round.
3. Wait for CI and the review. Triage every finding in one pass: fix P0/P1 findings and anything
   that will actually bite; answer the rest with a one-line reason and resolve the thread.
4. If round 1 reported P0/P1 findings, push all fixes together, rerun the checks, and request round
   2 with the same command. Round 2 is final. A round with no P0/P1 finding is already final.
5. After the final round, fix any remaining blockers in child commits (never amend or rebase the
   reviewed commit), rerun the checks, resolve those threads, and dispatch the gate:
   `gh workflow run codex-p1-gate.yml -f pr_number=<PR>`. Never request a third review or open a
   replacement PR to reset the budget.
6. Merge when the `Codex review gate` status and every repository check are green and live
   `reviewThreads` shows no unresolved P0/P1 Codex thread (in a Claude cloud session, read
   `gh api repos/<owner>/<repo>/pulls/<PR>/ccr/review_threads`). Merging is not deploying.

The gate publishes "Exact-head Codex review is not ready" for every failure, including an open
P0/P1 thread or a non-`main` base. Open the status link and read the run log for the real reason
before acting. Dependabot PRs always fail the gate by design; do not request reviews on them.

`scripts/request-review.py` is a copy of the canonical script in `dmfenton/codex-review-gate`;
change it there first, then copy it here unchanged.

### 8. Report

Output the PR URL and its gate state for the user.
