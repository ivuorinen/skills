#!/usr/bin/env python3
"""Bitbucket Cloud provider: PR comments and status, in the shared envelope.

Library, not a CLI — `fetch-pr-comments.py` and `fetch-pr-status.py` dispatch
here. Bitbucket **Cloud** only (`api.bitbucket.org/2.0`): Bitbucket Data Center
serves a different, incompatible API (`/rest/api/1.0`) and is out of scope, so a
Data Center host is refused by platform detection rather than half-supported.

Auth, in order:
    1. BITBUCKET_TOKEN — workspace/repo access token, sent as `Bearer`.
    2. BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD — HTTP Basic.

There is no first-party CLI to fall back to, which is why this provider has one
transport where the other two have two.

Three fields the shared envelope carries are structurally empty or null here:
  * `review_bodies` — Bitbucket has no review-body concept; an approval carries
    no text and prose is an ordinary PR comment, which lands in `summary_comments`.
  * `diff_hunk` — Bitbucket reports an inline anchor (path + line), not a hunk;
    `line` carries it.
  * `mergeable` — the PR resource exposes no merge-check verdict, so it stays
    null (unknown) rather than being guessed from `state`.
"""

import base64
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr_common
from pr_common import Target, TransportError

# Bitbucket PR state -> the shared open|closed|merged vocabulary. SUPERSEDED is
# what Bitbucket calls a PR replaced by another; it is closed from a reviewer's
# point of view, which is the distinction the shared vocabulary makes.
_PR_STATES = {"OPEN": "open", "MERGED": "merged", "DECLINED": "closed", "SUPERSEDED": "closed"}

# Bitbucket build status -> (shared `status`, shared `conclusion`).
_BUILD_STATES = {
    "SUCCESSFUL": ("completed", "success"),
    "FAILED": ("completed", "failure"),
    "ERROR": ("completed", "failure"),
    "STOPPED": ("completed", "cancelled"),
    "INPROGRESS": ("in_progress", ""),
}


def _headers() -> dict[str, str]:
    """Auth headers, or raise. Both credential shapes only ever reach
    api.bitbucket.org — the host is a constant here, not derived from a remote."""
    token = os.environ.get("BITBUCKET_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    user = os.environ.get("BITBUCKET_USERNAME", "")
    app_password = os.environ.get("BITBUCKET_APP_PASSWORD", "")
    if user and app_password:
        basic = base64.b64encode(f"{user}:{app_password}".encode()).decode()
        return {"Authorization": f"Basic {basic}", "Accept": "application/json"}
    raise TransportError(
        "No auth available. Set BITBUCKET_TOKEN, or BITBUCKET_USERNAME with BITBUCKET_APP_PASSWORD."
    )


def _transport(target: Target) -> tuple[Callable[[str], list[Any]], Callable[[str], Any]]:
    headers = _headers()

    def list_all(path: str) -> list[Any]:
        joiner = "&" if "?" in path else "?"
        return pr_common.paginate_body_next(
            f"{target.api_base}/{path}{joiner}pagelen=100", headers, target.api_netloc
        )

    def get_one(path: str) -> Any:
        body, _ = pr_common.http_json(f"{target.api_base}/{path}", headers, target.api_netloc)
        return body

    return list_all, get_one


def _pr_path(target: Target, pr_number: int) -> str:
    return f"repositories/{target.path}/pullrequests/{pr_number}"


def _author(record: dict[str, Any]) -> str:
    user = record.get("user") or record.get("author") or {}
    return user.get("nickname") or user.get("display_name") or "unknown"


def _body(record: dict[str, Any]) -> str:
    return ((record.get("content") or {}).get("raw")) or ""


def _html_url(record: dict[str, Any]) -> str:
    return ((record.get("links") or {}).get("html") or {}).get("href") or ""


# ── comments ─────────────────────────────────────────────────────────────────
def _split_comments(raw: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(threads, summary_comments) from Bitbucket's one comments endpoint.

    Inline comments carry an `inline` anchor; the rest are PR-level comments.
    Replies point at their parent by id, so a thread is the transitive closure of
    a root — resolved by walking `parent` up to a root that is already known,
    rather than assuming a reply's parent is itself a root. Bitbucket allows
    replies to replies, so the one-level assumption silently splits a deep thread
    into several.

    Deleted comments are dropped: Bitbucket keeps the record with a null body, and
    an empty comment in a thread reads as a reviewer saying nothing.
    """
    roots: dict[Any, Any] = {}  # comment id -> its thread's root id
    threads: dict[Any, dict[str, Any]] = {}
    summary: list[dict[str, Any]] = []

    # Parents always precede replies in Bitbucket's default (id-ascending) order,
    # so one pass suffices; a reply whose parent is missing starts its own thread
    # rather than being dropped.
    for record in raw:
        if not isinstance(record, dict) or record.get("deleted"):
            continue
        cid = record.get("id")
        inline = record.get("inline") or {}
        parent_id = (record.get("parent") or {}).get("id")
        root_id = roots.get(parent_id, parent_id if parent_id in threads else cid)

        if not inline and root_id not in threads:
            if _body(record).strip():
                summary.append(
                    {
                        "author": _author(record),
                        "created_at": record.get("created_on", ""),
                        "updated_at": record.get("updated_on", ""),
                        "body": _body(record),
                    }
                )
            continue

        roots[cid] = root_id
        if root_id not in threads:
            threads[root_id] = pr_common.thread(
                thread_id=str(root_id),
                path=inline.get("path", ""),
                # `to` is the line in the new file, `from` in the old one; an
                # anchor on a deleted line has only the latter.
                line=inline.get("to") if inline.get("to") is not None else inline.get("from"),
                # A non-null `resolution` is Bitbucket's resolved marker. The
                # field is absent on older payloads, where resolution is genuinely
                # unknown — null, not False.
                is_resolved=(record.get("resolution") is not None)
                if "resolution" in record
                else None,
                url=_html_url(record),
            )
        threads[root_id]["comments"].append(
            pr_common.comment(
                id=cid,
                author=_author(record),
                body=_body(record),
                created_at=record.get("created_on", ""),
                url=_html_url(record),
            )
        )
    return list(threads.values()), summary


def fetch_comments(target: Target, pr_number: int) -> dict[str, Any]:
    list_all, _get_one = _transport(target)
    raw = list_all(f"{_pr_path(target, pr_number)}/comments")
    threads, summary_comments = _split_comments(raw)
    return pr_common.comments_envelope(
        target,
        pr_number,
        threads=threads,
        # Structurally empty — see the module docstring.
        review_bodies=[],
        summary_comments=summary_comments,
        transport="bitbucket-rest",
    )


# ── status ───────────────────────────────────────────────────────────────────
def _checks(target: Target, sha: str, list_all: Callable[[str], list[Any]]):
    raw = list_all(f"repositories/{target.path}/commit/{sha}/statuses")
    checks = []
    for record in raw:
        if not isinstance(record, dict):
            continue
        status, conclusion = _BUILD_STATES.get(
            (record.get("state") or "").upper(), ("in_progress", "")
        )
        checks.append(
            pr_common.check(
                name=record.get("name") or record.get("key", ""),
                status=status,
                conclusion=conclusion,
                url=record.get("url", ""),
            )
        )
    return checks


def _reviews(pr: dict[str, Any]):
    """Verdicts from `participants`.

    `approved` is a boolean flag separate from `state`, and the two disagree on
    older payloads, so approval is read from the flag and only a reviewer who has
    neither approved nor requested changes falls through to `commented`.
    """
    reviews = []
    for participant in pr.get("participants") or []:
        if not isinstance(participant, dict):
            continue
        state = (participant.get("state") or "").lower()
        if participant.get("approved"):
            verdict = "approved"
        elif state == "changes_requested":
            verdict = "changes_requested"
        else:
            continue
        reviews.append(
            pr_common.review(
                author=_author(participant),
                state=verdict,
                submitted_at=participant.get("participated_on", ""),
            )
        )
    return reviews


def fetch_status(target: Target, pr_number: int) -> dict[str, Any]:
    list_all, get_one = _transport(target)
    pr = get_one(_pr_path(target, pr_number))
    if not isinstance(pr, dict) or "id" not in pr:
        raise TransportError(f"PR #{pr_number} not found in {target.path}")

    source = pr.get("source") or {}
    head_sha = (source.get("commit") or {}).get("hash", "")
    diffstat = pr_common.best_effort(
        "changed files", lambda: list_all(f"{_pr_path(target, pr_number)}/diffstat"), []
    )
    return pr_common.status_envelope(
        target,
        pr_number,
        url=_html_url(pr),
        title=pr.get("title", ""),
        author=_author(pr),
        state=_PR_STATES.get(pr.get("state") or "", (pr.get("state") or "").lower()),
        is_draft=bool(pr.get("draft")),
        source_branch=(source.get("branch") or {}).get("name", ""),
        target_branch=((pr.get("destination") or {}).get("branch") or {}).get("name", ""),
        head_sha=head_sha,
        created_at=pr.get("created_on", ""),
        updated_at=pr.get("updated_on", ""),
        # No merge-check verdict on the PR resource — see the module docstring.
        mergeable=None,
        merge_state="",
        checks=(
            pr_common.best_effort("checks", lambda: _checks(target, head_sha, list_all), [])
            if head_sha
            else []
        ),
        reviews=_reviews(pr),
        changed_files=[
            ((d.get("new") or d.get("old") or {}) or {}).get("path", "")
            for d in diffstat
            if isinstance(d, dict)
        ],
    )
