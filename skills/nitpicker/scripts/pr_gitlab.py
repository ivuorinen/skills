#!/usr/bin/env python3
"""GitLab provider: merge-request discussions and status, in the shared envelope.

Library, not a CLI — `fetch-pr-comments.py` and `fetch-pr-status.py` dispatch
here. "PR number" means the MR **iid** (the per-project number in the URL), not
the global MR id; the iid is what a reviewer reads off the page, so it is what
the CLIs take.

Works against gitlab.com and self-hosted instances alike: GitLab serves its API
from the instance itself (`https://<host>/api/v4`), so the host parsed off the
git remote is the API host. That is the whole of the self-hosted support.

Transport priority:
    1. GITLAB_TOKEN + REST — deterministic Link-header pagination, the same code
       path as every other platform here.
    2. `glab api --paginate` — for a user whose only credential is the CLI's.

REST is preferred over the CLI here, the reverse of the GitHub provider's order,
because on GitHub the CLI unlocks GraphQL's `isResolved`, which REST cannot give;
on GitLab REST already reports resolution, so the CLI adds no information and
only removes control over paging.

Two fields the shared envelope carries are structurally empty for GitLab, and
that is deliberate rather than an omission:
  * `review_bodies` — GitLab has no review-body concept. An approval carries no
    text, and a reviewer's prose is an ordinary discussion note, which lands in
    `summary_comments`.
  * `diff_hunk` on a thread — GitLab reports a position (path + line), not the
    surrounding hunk. `line` carries the anchor instead, which is why the shared
    thread shape has that field at all.
"""

import os
import sys
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr_common

# GitLab job status -> (shared `status`, shared `conclusion`).
_JOB_STATES = {
    "success": ("completed", "success"),
    "failed": ("completed", "failure"),
    "canceled": ("completed", "cancelled"),
    "cancelled": ("completed", "cancelled"),
    "skipped": ("completed", "skipped"),
    "manual": ("completed", "neutral"),
    "created": ("queued", ""),
    "pending": ("queued", ""),
    "waiting_for_resource": ("queued", ""),
    "preparing": ("in_progress", ""),
    "running": ("in_progress", ""),
}

# GitLab MR state -> the shared open|closed|merged vocabulary. `locked` is an
# open MR whose discussion is frozen, so it normalises to open rather than closed.
_MR_STATES = {"opened": "open", "locked": "open", "closed": "closed", "merged": "merged"}


def _token_for(target: pr_common.Target) -> str:
    """GITLAB_TOKEN, but only when it belongs to the instance being addressed.

    GITLAB_HOST is how a user names the instance their token is for. When it is
    set and does not match the target, the token is withheld rather than sent —
    otherwise a gitlab.com token would be forwarded to whatever self-hosted host
    the git remote happened to name, which is a credential leak to a third party,
    not a failed request.
    """
    token = os.environ.get("GITLAB_TOKEN", "")
    declared = os.environ.get("GITLAB_HOST", "").strip()
    if not token or not declared:
        return token
    declared_host = urllib.parse.urlsplit(
        declared if "://" in declared else f"https://{declared}"
    ).netloc
    if declared_host and declared_host.lower() != target.host.lower():
        pr_common.warn(
            f"GITLAB_TOKEN is declared for {declared_host} but the target is "
            f"{target.host}; not sending it. Unset GITLAB_HOST or use glab."
        )
        return ""
    return token


def _transport(
    target: pr_common.Target,
) -> tuple[Callable[[str], list[Any]], Callable[[str], Any], str]:
    """(paginating list transport, single-object transport, label) — or raise."""
    token = _token_for(target)
    if token:
        headers = {"PRIVATE-TOKEN": token}

        def rest_list(path: str) -> list[Any]:
            joiner = "&" if "?" in path else "?"
            return pr_common.paginate_link(
                f"{target.api_base}/{path}{joiner}per_page=100", headers, target.api_netloc
            )

        def rest_get(path: str) -> Any:
            body, _ = pr_common.http_json(f"{target.api_base}/{path}", headers, target.api_netloc)
            return body

        return rest_list, rest_get, "token-rest"

    if pr_common.cli_available("glab"):
        base = ["glab", "api", "--hostname", target.host]

        def glab_list(path: str) -> list[Any]:
            """Normalise `glab`'s output to a list, whatever arrived.

            The CLI returns a bare object for a single-record endpoint and null
            for an empty one, so callers that iterate would otherwise have to
            re-check the type at each site.
            """
            joiner = "&" if "?" in path else "?"
            result = pr_common.cli_json([*base, "--paginate", f"{path}{joiner}per_page=100"])
            return result if isinstance(result, list) else ([] if result is None else [result])

        return glab_list, lambda path: pr_common.cli_json([*base, path]), "glab"

    raise pr_common.TransportError(
        "No auth available. Set GITLAB_TOKEN (and GITLAB_HOST for a self-hosted "
        "instance), or install and authenticate the glab CLI."
    )


def _mr_path(target: pr_common.Target, iid: int) -> str:
    return f"projects/{target.encoded_path}/merge_requests/{iid}"


def _note_url(target: pr_common.Target, iid: int, note_id: Any) -> str:
    return f"https://{target.host}/{target.path}/-/merge_requests/{iid}#note_{note_id}"


def _author(note: dict[str, Any]) -> str:
    return (note.get("author") or {}).get("username") or "unknown"


# ── comments ─────────────────────────────────────────────────────────────────
def _position(note: dict[str, Any]) -> dict[str, Any]:
    return note.get("position") or {}


def _split_discussions(
    target: pr_common.Target, iid: int, discussions: list[Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(threads, summary_comments) from GitLab's one discussions endpoint.

    GitLab returns inline threads and plain MR comments from the same call,
    distinguished only by whether a note carries a `position`. System notes
    ("added 3 commits", "changed the description") are dropped: they are activity
    records, never review feedback, and a caller that had to filter them would be
    filtering platform noise the shared format exists to hide.
    """
    threads: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for discussion in discussions:
        if not isinstance(discussion, dict):
            continue
        notes = [n for n in (discussion.get("notes") or []) if isinstance(n, dict)]
        real = [n for n in notes if not n.get("system")]
        if not real:
            continue
        positioned = [n for n in real if _position(n)]
        if not positioned:
            summary.extend(
                {
                    "author": _author(n),
                    "created_at": n.get("created_at", ""),
                    "updated_at": n.get("updated_at", ""),
                    "body": n.get("body", ""),
                }
                for n in real
                if (n.get("body") or "").strip()
            )
            continue
        head = positioned[0]
        position = _position(head)
        resolvable = [n for n in real if n.get("resolvable")]
        threads.append(
            pr_common.thread(
                thread_id=str(discussion.get("id", "")),
                path=position.get("new_path") or position.get("old_path") or "",
                line=position.get("new_line") or position.get("old_line"),
                is_resolved=bool(resolvable[0].get("resolved")) if resolvable else None,
                url=_note_url(target, iid, head.get("id", "")),
                comments=[
                    pr_common.comment(
                        id=n.get("id", ""),
                        author=_author(n),
                        body=n.get("body", ""),
                        created_at=n.get("created_at", ""),
                        url=_note_url(target, iid, n.get("id", "")),
                    )
                    for n in real
                ],
            )
        )
    return threads, summary


def fetch_comments(target: pr_common.Target, pr_number: int) -> dict[str, Any]:
    """GitLab's half of the shared comment contract.

    One endpoint answers both sections: a discussion whose notes carry a
    `position` is an inline thread, and one without is an MR-level comment.
    `review_bodies` is always empty here because GitLab has no review-body
    concept — reviewer prose arrives as an ordinary comment — and that emptiness
    is the contract rather than a failed fetch.
    """
    rest_list, _get_one, label = _transport(target)
    discussions = rest_list(f"{_mr_path(target, pr_number)}/discussions")
    threads, summary_comments = _split_discussions(target, pr_number, discussions)
    return pr_common.comments_envelope(
        target,
        pr_number,
        threads=threads,
        # Structurally empty — see the module docstring.
        review_bodies=[],
        summary_comments=summary_comments,
        transport=label,
    )


# ── status ───────────────────────────────────────────────────────────────────
def _checks(target: pr_common.Target, iid: int, rest_list: Callable[[str], list[Any]]):
    """Jobs of the MR's most recent pipeline.

    The MR pipelines endpoint returns newest first, so index 0 is the head
    pipeline. Reporting its *jobs* rather than the single pipeline status is what
    makes `checks_summary` comparable with GitHub's per-check-run counts.
    """
    pipelines = rest_list(f"{_mr_path(target, iid)}/pipelines")
    head = next((p for p in pipelines if isinstance(p, dict)), None)
    if not head:
        return []
    jobs = rest_list(f"projects/{target.encoded_path}/pipelines/{head.get('id')}/jobs")
    checks = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        status, conclusion = _JOB_STATES.get((job.get("status") or "").lower(), ("in_progress", ""))
        checks.append(
            pr_common.check(
                name=job.get("name", ""),
                status=status,
                conclusion=conclusion,
                url=job.get("web_url", ""),
            )
        )
    return checks


def _reviews(
    mr: dict[str, Any], target: pr_common.Target, iid: int, rest_get: Callable[[str], Any]
):
    """Approvals plus any reviewer who has requested changes.

    Two sources because GitLab splits them: approvals live on their own endpoint,
    while "requested changes" is a state on the MR's `reviewers`. A reviewer who
    did both is reported once, with the approval winning — it is the later act
    that GitLab lets stand.
    """
    reviews: dict[str, dict[str, Any]] = {}
    for reviewer in mr.get("reviewers") or []:
        if isinstance(reviewer, dict) and (reviewer.get("state") or "") == "requested_changes":
            username = reviewer.get("username") or "unknown"
            reviews[username] = pr_common.review(author=username, state="changes_requested")
    approvals = pr_common.best_effort(
        "approvals", lambda: rest_get(f"{_mr_path(target, iid)}/approvals"), {}
    )
    for entry in (approvals or {}).get("approved_by") or []:
        username = ((entry or {}).get("user") or {}).get("username") or "unknown"
        reviews[username] = pr_common.review(author=username, state="approved")
    return list(reviews.values())


def _mergeable(detailed: str) -> bool | None:
    """Tri-state from `detailed_merge_status`.

    `checking`/`unchecked` mean GitLab has not finished deciding, which is not the
    same as "cannot merge" — collapsing them to False reports a fine MR as blocked.
    """
    if detailed in ("checking", "unchecked", ""):
        return None
    return detailed == "mergeable"


def fetch_status(target: pr_common.Target, pr_number: int) -> dict[str, Any]:
    """GitLab's half of the shared status contract.

    GitLab's own vocabulary differs from the shared one at both ends — merge
    requests carry a `detailed_merge_status` with no GitHub counterpart, and
    pipeline jobs are not check runs — so the mapping into the common shape
    happens here rather than in the caller, which is what lets `cr` read the
    same field names whichever platform answered.
    """
    rest_list, rest_get, _label = _transport(target)
    mr = rest_get(_mr_path(target, pr_number))
    if not isinstance(mr, dict) or "iid" not in mr:
        raise pr_common.TransportError(f"MR !{pr_number} not found in {target.path}")

    detailed = mr.get("detailed_merge_status") or ""
    diffs = pr_common.best_effort(
        "changed files", lambda: rest_list(f"{_mr_path(target, pr_number)}/diffs"), []
    )
    return pr_common.status_envelope(
        target,
        pr_number,
        url=mr.get("web_url", ""),
        title=mr.get("title", ""),
        author=(mr.get("author") or {}).get("username", "unknown"),
        state=_MR_STATES.get(mr.get("state") or "", mr.get("state") or ""),
        is_draft=bool(mr.get("draft") or mr.get("work_in_progress")),
        source_branch=mr.get("source_branch", ""),
        target_branch=mr.get("target_branch", ""),
        head_sha=mr.get("sha", ""),
        created_at=mr.get("created_at", ""),
        updated_at=mr.get("updated_at", ""),
        mergeable=_mergeable(detailed),
        merge_state=detailed,
        checks=pr_common.best_effort("checks", lambda: _checks(target, pr_number, rest_list), []),
        reviews=pr_common.best_effort(
            "reviews", lambda: _reviews(mr, target, pr_number, rest_get), []
        ),
        changed_files=[
            d.get("new_path") or d.get("old_path") or "" for d in diffs if isinstance(d, dict)
        ],
    )
