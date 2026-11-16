#!/usr/bin/env python3
"""Decide whether a push to main may reuse the merged pull request's passed run.

A push-to-main run after an up-to-date merge tests the same tree the pull request
already tested. This check proves that equivalence from GitHub's own records and
prints ``reused=true`` only when every condition holds:

1. The event is a push to ``refs/heads/main``.
2. Exactly one merged pull request into main names this commit as its merge
   commit.
3. This commit's tree is byte-identical to the pull request head's tree.
4. The pre-merge main commit (the first parent) is an ancestor of the pull request
   head. Main only moves forward, so the base of every earlier pull request run
   was also an ancestor of the head, and that run's merge ref had the head's tree.
5. The pull request was never retargeted, and every pull request from its head
   branch targets main, so a run on that branch tested a merge into main.
6. The newest completed ``pull_request`` run of the same workflow file on that
   head, from this repository's head branch and created after the pull request
   opened, concluded ``success``.

Identical trees include identical workflow files and tests, so the push run
would execute the same jobs on the same inputs. Anything else, including any
API error, prints ``reused=false`` and the caller runs normally: the check can
only skip work it can prove already passed, never block it.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

MAIN_REF = "refs/heads/main"
# limit: GitHub REST API maximum page size for list endpoints.
PAGE_SIZE = 100
# limit: GitHub REST API guidance; a decision step should fail open well before a job timeout.
REQUEST_TIMEOUT_SECONDS = 20
ANCESTOR_STATUSES = frozenset({"ahead", "identical"})

Getter = Callable[[str], Any]


class ApiError(Exception):
    """A GitHub API read failed; the caller runs the work normally."""


@dataclass(frozen=True)
class Decision:
    reused: bool
    reason: str
    source_run: str = ""


def github_getter(api_url: str, token: str) -> Getter:
    def get(path: str) -> Any:
        request = urllib.request.Request(
            f"{api_url}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=REQUEST_TIMEOUT_SECONDS
            ) as response:
                return json.load(response)
        # OSError covers URLError, timeouts and connection resets; HTTPException covers a
        # response cut off mid-body (IncompleteRead). All of them mean "not proven".
        except (OSError, http.client.HTTPException, ValueError) as error:
            # Content-free: the path names only public identifiers, never response bodies.
            raise ApiError(
                f"GET {path.split('?')[0]} failed: {type(error).__name__}"
            ) from error

    return get


def workflow_file(workflow_ref: str, repository: str) -> str:
    """Return the workflow file name from GITHUB_WORKFLOW_REF, or '' if it is not this repository's."""
    prefix = f"{repository}/.github/workflows/"
    path = workflow_ref.split("@", 1)[0]
    if not path.startswith(prefix):
        return ""
    name = path[len(prefix) :]
    return name if name and "/" not in name else ""


def merged_pull_request(
    get: Getter, repository: str, sha: str
) -> Mapping[str, Any] | None:
    pulls = get(f"/repos/{repository}/commits/{sha}/pulls?per_page={PAGE_SIZE}")
    matches = [
        pull
        for pull in pulls
        if pull.get("merged_at")
        and pull.get("merge_commit_sha") == sha
        and pull.get("base", {}).get("ref") == "main"
        and pull.get("head", {}).get("repo", {}).get("full_name") == repository
    ]
    return matches[0] if len(matches) == 1 else None


def only_ever_targeted_main(
    get: Getter, repository: str, pull: Mapping[str, Any]
) -> bool:
    """True when this pull request was never retargeted and no other one from its branch targets elsewhere."""
    events = get(
        f"/repos/{repository}/issues/{pull['number']}/events?per_page={PAGE_SIZE}"
    )
    if len(events) >= PAGE_SIZE or any(
        event.get("event") == "base_ref_changed" for event in events
    ):
        return False
    owner = repository.split("/", 1)[0]
    head = urllib.parse.quote(f"{owner}:{pull['head']['ref']}", safe=":")
    siblings = get(
        f"/repos/{repository}/pulls?state=all&head={head}&per_page={PAGE_SIZE}"
    )
    return len(siblings) < PAGE_SIZE and all(
        sibling.get("base", {}).get("ref") == "main" for sibling in siblings
    )


def newest_pull_request_run(
    get: Getter, repository: str, workflow: str, pull: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    head_sha = pull["head"]["sha"]
    query = urllib.parse.urlencode(
        {"event": "pull_request", "head_sha": head_sha, "per_page": PAGE_SIZE}
    )
    body = get(f"/repos/{repository}/actions/workflows/{workflow}/runs?{query}")
    runs = [
        run
        for run in body.get("workflow_runs", [])
        if run.get("head_sha") == head_sha
        and run.get("status") == "completed"
        and run.get("head_repository", {}).get("full_name") == repository
        and run.get("head_branch") == pull["head"]["ref"]
        and run.get("created_at", "") >= pull["created_at"]
    ]
    if not runs:
        return None
    return max(
        runs, key=lambda run: (run.get("created_at", ""), run.get("run_attempt", 0))
    )


def decide(
    get: Getter, *, repository: str, sha: str, ref: str, event: str, workflow_ref: str
) -> Decision:
    if event != "push" or ref != MAIN_REF:
        return Decision(False, "not a push to main")
    workflow = workflow_file(workflow_ref, repository)
    if not workflow:
        return Decision(False, "workflow file is not this repository's")
    commit = get(f"/repos/{repository}/git/commits/{sha}")
    parents = commit.get("parents") or []
    if not parents:
        return Decision(False, "commit has no parent")
    pull = merged_pull_request(get, repository, sha)
    if pull is None:
        return Decision(False, "no single merged pull request for this commit")
    head_sha = pull["head"]["sha"]
    head = get(f"/repos/{repository}/git/commits/{head_sha}")
    if head.get("tree", {}).get("sha") != commit.get("tree", {}).get("sha"):
        return Decision(False, f"tree differs from pull request #{pull['number']} head")
    base_sha = parents[0]["sha"]
    compare = get(f"/repos/{repository}/compare/{base_sha}...{head_sha}")
    if compare.get("status") not in ANCESTOR_STATUSES:
        return Decision(
            False, f"pull request #{pull['number']} was not up to date with main"
        )
    if not only_ever_targeted_main(get, repository, pull):
        return Decision(
            False, f"pull request #{pull['number']} or its branch targeted another base"
        )
    run = newest_pull_request_run(get, repository, workflow, pull)
    if run is None:
        return Decision(
            False, f"no completed run of {workflow} on pull request #{pull['number']}"
        )
    if run.get("conclusion") != "success":
        return Decision(
            False,
            f"newest run of {workflow} on pull request #{pull['number']} did not succeed",
        )
    return Decision(
        True,
        f"pull request #{pull['number']} passed {workflow} on this exact tree",
        str(run.get("html_url", "")),
    )


def safe_decide(get: Getter, **context: str) -> Decision:
    try:
        return decide(get, **context)
    except Exception as error:  # noqa: BLE001 - any failure means "not proven", never a failed job.
        return Decision(
            False, f"could not prove reuse ({type(error).__name__}); running normally"
        )


def write_outputs(decision: Decision, output_path: str) -> None:
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"reused={'true' if decision.reused else 'false'}\n")
        output.write(f"source_run={decision.source_run}\n")


def main(
    argv: list[str] | None = None, environ: Mapping[str, str] | None = None
) -> int:
    env = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repository", default=env.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--sha", default=env.get("GITHUB_SHA", ""))
    parser.add_argument("--ref", default=env.get("GITHUB_REF", ""))
    parser.add_argument("--event", default=env.get("GITHUB_EVENT_NAME", ""))
    parser.add_argument("--workflow-ref", default=env.get("GITHUB_WORKFLOW_REF", ""))
    parser.add_argument("--output", default=env.get("GITHUB_OUTPUT", ""))
    args = parser.parse_args(argv)
    get = github_getter(
        env.get("GITHUB_API_URL", "https://api.github.com"), env.get("GITHUB_TOKEN", "")
    )
    decision = safe_decide(
        get,
        repository=args.repository,
        sha=args.sha,
        ref=args.ref,
        event=args.event,
        workflow_ref=args.workflow_ref,
    )
    if decision.reused:
        print(
            f"::notice title=Reused pull request result::{decision.reason}: {decision.source_run}"
        )
    else:
        print(f"Running normally: {decision.reason}")
    if args.output:
        write_outputs(decision, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
