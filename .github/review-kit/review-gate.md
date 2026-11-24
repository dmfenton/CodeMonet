<!-- Managed by dmfenton/platform tools/review-kit: change the canonical file there and sync; never edit this copy. -->

# Open, review and land

Every repository that uses `dmfenton/codex-review-gate` lands pull requests this way. The
repository's own PR skill adds its validation and its review rule (which findings block, and
whether a thread may be resolved with a reply), and links here for the rest.

Codex does not review drafts, and marking a PR ready has not reliably started a review, so the
review is always requested explicitly, right after the PR is ready.

1. Push the branch and open the PR against `main`. A draft is fine while work continues.
2. When validation is green and the change is complete, mark it ready and immediately request the
   review. `gh pr ready <PR>` uses GraphQL, which Claude cloud sessions cannot reach; there use
   `gh api -X POST repos/<owner>/<repo>/pulls/<PR>/ccr/ready_for_review`. Then:
   `python3 scripts/request-review.py <PR> --request`
   Without `--request` the script only reports whether a request is allowed. Never post
   `@codex review` by hand: the script refuses a draft, a head that already has a review, a review
   that is running or pending, a third round, and a `gh` signed in as a bot (Codex ignores bots,
   so request from the laptop or a cloud session, never from a runner host).
3. Wait for CI and the review. Triage every finding in one pass by the repository's review rule.
4. If round 1 reported P0/P1 findings, push all fixes together, rerun the checks, and request round
   2 with the same command. Round 2 is final. A round with no P0/P1 finding is already final.
5. After the final round, fix any remaining blockers in child commits (never amend or rebase the
   reviewed commit), rerun the checks, resolve those threads, and dispatch the gate:
   `gh workflow run codex-p1-gate.yml -f pr_number=<PR>` (in a Claude cloud session, which has no
   GraphQL: `gh api -X POST repos/<owner>/<repo>/actions/workflows/codex-p1-gate.yml/dispatches
   -f ref=main -f 'inputs[pr_number]=<PR>'`). Never request a third review or open a replacement
   PR to reset the budget.
6. Before merging, run the friction retro: for each thing that cost real time (a check that only
   failed in CI, a missing tool or permission, an unclear doc, a slow or flaky step), comment
   "Hit again" on a matching open issue labelled `friction` in this repository, or open one with
   what happened, what it cost and a proposed fix. List them in the PR body, or write "none".
   Never put private content in an issue.
7. Merge when the `Codex review gate` status and every repository check are green and live
   `reviewThreads` satisfies the repository's review rule (in a Claude cloud session, read
   `gh api repos/<owner>/<repo>/pulls/<PR>/ccr/review_threads`). Merging is not deploying.

While a review is still owed (none completed yet, or the final round after blocking findings),
the gate shows `pending` ("Waiting for a Codex review ...") and the job passes; pending still
blocks merge. The gate publishes "Exact-head Codex review is not ready" for every real failure,
including an open P0/P1 thread or a non-`main` base. Open the status link and read the run log
for the real reason before acting.

Dependabot PRs go through the gate like any other PR: request the review with the script and
merge once the gate and CI pass. Runs Dependabot itself triggers get no gate job (and no write
token), so a Dependabot head shows no gate status until its review completes.

`scripts/request-review.py`, `.github/workflows/codex-p1-gate.yml`, this file and
`scripts/audit-python-dependencies.sh` (where present) come from `dmfenton/platform`
`tools/review-kit`. `.github/review-kit/manifest.json` records the Platform commit they were synced
from. Never edit them here: change the kit in Platform, then sync every repository.
