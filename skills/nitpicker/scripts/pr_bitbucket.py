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
    raise pr_common.TransportError(
        "No auth available. Set BITBUCKET_TOKEN, or BITBUCKET_USERNAME with BITBUCKET_APP_PASSWORD."
    )


def _transport(target: pr_common.Target) -> tuple[Callable[[str], list[Any]], Callable[[str], Any]]:
    """Both accessors, closed over one set of credentials and one pinned host.

    Bound together so the header set and the host a redirect may keep it for
    cannot drift apart between a list call and a single-record call. Bitbucket
    has no CLI, so unlike the other providers there is only ever one transport
    and no fallback to label.
    """
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


def _pr_path(target: pr_common.Target, pr_number: int) -> str:
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
    a root — resolved by walking `parent` up to a root, rather than assuming a
    reply's parent is itself a root. Bitbucket allows replies to replies, so the
    one-level assumption silently splits a deep thread into several.

    The parent index is built in a **separate first pass** rather than inline.
    Arrival order is the server's choice — `_transport` asks for `sort=id`, but
    that is a request, not a guarantee — and a single forward pass drops any reply
    that precedes its parent into `summary_comments`, where it loses its `path`
    and `cr` then treats it as an out-of-band notice it must not act on. A
    reviewer's follow-up must not go silently unactionable because the API
    reordered a page.

    Deleted comments are dropped: Bitbucket keeps the record with a null body, and
    an empty comment in a thread reads as a reviewer saying nothing.
    """
    live = [r for r in raw if isinstance(r, dict) and not r.get("deleted")]
    by_id = {r.get("id"): r for r in live}
    parent_of = {r.get("id"): (r.get("parent") or {}).get("id") for r in live}
    anchored = {r.get("id"): (r.get("inline") or {}) for r in live if r.get("inline")}

    def root_of(cid: Any) -> Any:
        """The id at the top of `cid`'s parent chain, order-independent.

        Stops at a parent that is not in this payload: a reply whose parent was
        deleted, or paged out, roots at itself and keeps its own anchor rather
        than chasing an id that resolves to nothing. `seen` guards a cycle — the
        ids come from the API, and a self- or mutually-referencing `parent` would
        otherwise spin here forever.
        """
        seen = {cid}
        while True:
            parent = parent_of.get(cid)
            if parent is None or parent in seen or parent not in by_id:
                return cid
            cid = parent
            seen.add(cid)

    threads: dict[Any, dict[str, Any]] = {}
    summary: list[dict[str, Any]] = []

    for record in live:
        cid = record.get("id")
        root_id = root_of(cid)
        # A comment belongs to a thread when its chain's root is anchored to a
        # line — which is what makes a reply inherit its parent's anchor.
        inline = anchored.get(root_id) or {}
        if not inline:
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

        if root_id not in threads:
            # Metadata comes from the ROOT record, never from whichever record
            # happened to arrive first. Reading `resolution` and the permalink off
            # a reply would report the reply's state as the thread's.
            root = by_id.get(root_id, record)
            threads[root_id] = pr_common.thread(
                thread_id=str(root_id),
                path=inline.get("path", ""),
                # `to` is the line in the new file, `from` in the old one; an
                # anchor on a deleted line has only the latter.
                line=inline.get("to") if inline.get("to") is not None else inline.get("from"),
                # A non-null `resolution` is Bitbucket's resolved marker. The
                # field is absent on older payloads, where resolution is genuinely
                # unknown — null, not False.
                is_resolved=(root.get("resolution") is not None) if "resolution" in root else None,
                url=_html_url(root),
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


def fetch_comments(target: pr_common.Target, pr_number: int) -> dict[str, Any]:
    """Bitbucket's half of the shared comment contract.

    One endpoint answers both sections, split on whether a comment carries an
    `inline` anchor. `review_bodies` is always empty — Bitbucket has no review
    body — and `diff_hunk` is too, because comments anchor to a line rather
    than a hunk; `line` carries the anchor instead. Both emptinesses are the
    contract, not a failed fetch.
    """
    list_all, _get_one = _transport(target)
    # `sort=id` keeps parents ahead of their replies in the common case.
    # `_split_comments` does not rely on it — it resolves parent chains in a
    # separate pass — but asking costs nothing and keeps the data tidy.
    raw = list_all(f"{_pr_path(target, pr_number)}/comments?sort=id")
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
def _checks(target: pr_common.Target, sha: str, list_all: Callable[[str], list[Any]]):
    """Commit build statuses, mapped into the shared status/conclusion pair.

    Bitbucket reports one field where the shared shape carries two, so the
    split happens here. A state outside the mapping falls back to in-progress
    with no conclusion: never a pass, since reporting an unknown build as green
    is the one answer that misleads. The cost is that a state Bitbucket adds
    later reads as permanently running rather than as unrecognised — a caller
    waiting for checks to settle would wait forever, so a new state belongs in
    the mapping rather than left to the default.
    """
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


def fetch_status(target: pr_common.Target, pr_number: int) -> dict[str, Any]:
    """Bitbucket's half of the shared status contract.

    Checks come from the commit's build statuses rather than from the PR, since
    Bitbucket attaches them to the head commit. Only Bitbucket Cloud is
    covered — Data Center serves a different API, and platform detection
    refuses that host rather than sending a credential to an endpoint shaped
    unlike this one.
    """
    list_all, get_one = _transport(target)
    pr = get_one(_pr_path(target, pr_number))
    if not isinstance(pr, dict) or "id" not in pr:
        raise pr_common.TransportError(f"PR #{pr_number} not found in {target.path}")

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
