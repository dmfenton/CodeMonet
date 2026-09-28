---
description: Create PR, run code review, fix issues
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

### 7. Return PR URL

Output the PR URL for the user.
