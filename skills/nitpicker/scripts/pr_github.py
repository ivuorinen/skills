#!/usr/bin/env python3
"""GitHub provider: PR review comments and PR status, in the shared envelope.

Library, not a CLI — `fetch-pr-comments.py` and `fetch-pr-status.py` dispatch
here. Every function returns `pr_common` shapes so a caller never learns which
platform answered.

Transport priority for comments:
    1. gh CLI + GraphQL (the only source of `isResolved`; returns unresolved only)
    2. gh CLI + REST    (all threads; resolved state unknown -> is_resolved null)
    3. GITHUB_TOKEN + REST (same, over urllib)

The GraphQL-first order is not a preference, it is the whole point: REST cannot
report thread resolution, so a silent downgrade re-surfaces resolved threads as
unresolved. `fetch_comments` therefore hard-fails on a *transient* GraphQL error
and falls back only on a permanent one.
"""

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr_common
from pr_common import Target, TransportError

_GRAPHQL_QUERY = """
query($owner: String!, $repo: String!, $pr: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          path
          line
          comments(first: 100) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              body
              createdAt
              url
              author { login }
              diffHunk
            }
          }
        }
      }
    }
  }
}
"""

# Follow-up query paging the remaining comments of a single thread whose first
# page reported hasNextPage — keyed by the thread's node id.
_THREAD_COMMENTS_QUERY = """
query($id: ID!, $cursor: String) {
  node(id: $id) {
    ... on PullRequestReviewThread {
      comments(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          body
          createdAt
          url
          author { login }
          diffHunk
        }
      }
    }
  }
}
"""

# Markers that make a GraphQL failure transient rather than permanent. Scanned
# ONLY on GhTransportError, which carries gh's own stderr — the permanent raises
# below interpolate the PR number and owner/repo ("PR #502 not found in
# acme/secondary-index"), so an unguarded substring test would report those as
# transient and send the caller into a retry loop for a condition that never clears.
_TRANSIENT_MARKERS = ("rate limit", "rate_limit", "ratelimited", "secondary", "502", "503", "504")


class GhTransportError(TransportError):
    """gh itself failed — the only GraphQL failure class that can be transient.

    `fetch_comments` decides whether to abort or fall back to REST by scanning
    this error's text for `_TRANSIENT_MARKERS`. Confining that scan to this type
    is what keeps a permanent "not found" from being read as a rate limit.
    """


# ── transports ───────────────────────────────────────────────────────────────
def _gh_available() -> bool:
    return pr_common.cli_available("gh")


def _gh_graphql(query: str, variables: dict[str, Any], hostname: str = "") -> dict[str, Any]:
    argv = ["gh", "api", "graphql"]
    if hostname:
        argv += ["--hostname", hostname]
    argv += ["--input", "-"]

    payload = json.dumps({"query": query, "variables": variables}).encode()
    result = subprocess.run(argv, input=payload, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise GhTransportError(result.stderr.decode().strip())
    return json.loads(result.stdout)


def _gh_rest_paginate(path: str, hostname: str = "") -> list[Any]:

    argv = ["gh", "api", "--paginate", "--slurp"]
    if hostname:
        argv += ["--hostname", hostname]
    argv += [path]
    result = subprocess.run(argv, capture_output=True, timeout=60)
    if result.returncode != 0:
        raise GhTransportError(result.stderr.decode().strip())
    pages: list[Any] = json.loads(result.stdout)
    # `--slurp` yields one entry per page, and the entry's shape follows the
    # endpoint. An array-valued endpoint (`/comments`, `/reviews`, `/files`)
    # gives a list per page, which is flattened. An object-valued one
    # (`/commits/{sha}/check-runs`, `/commits/{sha}/status`) gives a dict — and
    # flattening a dict iterates its KEYS, so five real check runs arrived as
    # the strings "total_count" and "check_runs" and `_checks` reported zero CI
    # checks. Appending the object instead mirrors `paginate_link`, so the gh
    # and token transports answer identically for the same endpoint.
    out: list[Any] = []
    for page in pages:
        if isinstance(page, list):
            out.extend(page)
        else:
            out.append(page)
    return out


def _token_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}


def _token_for(target: Target) -> str:
    """GITHUB_TOKEN, but only when it belongs to the host being addressed.

    A github.com token must never be forwarded to whatever GitHub Enterprise host
    the git remote happened to name — that is a credential handed to a third
    party, not a failed request. GH_HOST is how a user names the instance their
    token is for, mirroring the gh CLI's own variable, so an Enterprise token is
    used exactly when it is declared for that Enterprise host.
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token or target.host == "github.com":
        return token
    if os.environ.get("GH_HOST", "").strip().lower() == target.host.lower():
        return token
    pr_common.warn(
        f"GITHUB_TOKEN is not declared for {target.host}; not sending it. "
        f"Set GH_HOST={target.host} if the token belongs to that instance."
    )
    return ""


def _gh_transport(target: Target) -> Callable[[str], list[Any]]:
    """A rest_list callable(path) -> list bound to the gh CLI."""
    hostname = "" if target.host == "github.com" else target.host
    return lambda path: _gh_rest_paginate(path, hostname)


def _token_transport(target: Target, token: str) -> Callable[[str], list[Any]]:
    """A rest_list callable(path) -> list bound to the GITHUB_TOKEN REST transport.

    `fetch_comments` hands the out-of-thread fetch whichever transport actually
    fetched the threads, so a gh path that failed into token REST does not
    silently re-select a broken gh for the notes.
    """

    def fetch(path: str) -> list[Any]:
        return pr_common.paginate_link(
            f"{target.api_base}/{path}?per_page=100", _token_headers(token), target.api_netloc
        )

    return fetch


def _token_get(target: Target, token: str, path: str) -> Any:
    body, _ = pr_common.http_json(
        f"{target.api_base}/{path}", _token_headers(token), target.api_netloc
    )
    return body


def _transport(target: Target) -> tuple[Callable[[str], list[Any]], Callable[[str], Any], str]:
    """(paginating list transport, single-object transport, label) — or raise.

    Both transports come from the same source so a caller cannot mix a gh list
    with a token GET and hit two different credentials mid-fetch.
    """
    token = _token_for(target)
    if _gh_available():
        hostname = "" if target.host == "github.com" else target.host

        def gh_get(path: str) -> Any:
            argv = ["gh", "api"] + (["--hostname", hostname] if hostname else []) + [path]
            return pr_common.cli_json(argv)

        return _gh_transport(target), gh_get, "gh"
    if token:
        return (
            _token_transport(target, token),
            lambda path: _token_get(target, token, path),
            "token",
        )
    raise TransportError("No auth available. Install the gh CLI or set GITHUB_TOKEN.")


# ── comments ─────────────────────────────────────────────────────────────────
def _gql_comment(c: dict[str, Any]) -> dict[str, Any]:
    return pr_common.comment(
        id=c["id"],
        author=(c.get("author") or {}).get("login", "unknown"),
        body=c["body"],
        created_at=c["createdAt"],
        diff_hunk=c.get("diffHunk", ""),
        url=c.get("url", ""),
    )


def _all_thread_comments(node: dict[str, Any], hostname: str) -> list[dict[str, Any]]:
    """All comments for one thread, following the inner `comments` cursor so a
    thread with >100 comments is not silently truncated to its first page."""

    conn = node["comments"]
    comments = [_gql_comment(c) for c in conn["nodes"]]
    info = conn.get("pageInfo") or {}
    cursor = info.get("endCursor")
    while info.get("hasNextPage") and cursor:
        sub = _gh_graphql(_THREAD_COMMENTS_QUERY, {"id": node["id"], "cursor": cursor}, hostname)
        if "errors" in sub:
            raise RuntimeError(json.dumps(sub["errors"]))
        node_data = (sub.get("data") or {}).get("node")
        if not node_data:
            break  # thread deleted or hidden mid-pagination — keep what we have
        conn = node_data["comments"]
        comments.extend(_gql_comment(c) for c in conn["nodes"])
        info = conn.get("pageInfo") or {}
        cursor = info.get("endCursor")
    return comments


def fetch_graphql(target: Target, pr_number: int) -> list[dict[str, Any]]:

    owner, repo = target.segments
    hostname = "" if target.host == "github.com" else target.host
    threads: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        resp = _gh_graphql(
            _GRAPHQL_QUERY,
            {"owner": owner, "repo": repo, "pr": pr_number, "cursor": cursor},
            hostname,
        )
        if "errors" in resp:
            # GitHub types its rate-limit errors, so match the field rather than
            # the rendered text — the payload echoes the repository name, and a
            # repo called `api-502` would otherwise read as a 502.
            errs = resp["errors"] if isinstance(resp["errors"], list) else []
            if any(isinstance(e, dict) and e.get("type") == "RATE_LIMITED" for e in errs):
                raise GhTransportError(json.dumps(resp["errors"]))
            raise RuntimeError(json.dumps(resp["errors"]))

        pr = resp["data"]["repository"]["pullRequest"]
        if pr is None:
            raise RuntimeError(f"PR #{pr_number} not found in {target.path}")
        page = pr["reviewThreads"]
        for node in page["nodes"]:
            if node["isResolved"]:
                continue
            comments = _all_thread_comments(node, hostname)
            threads.append(
                pr_common.thread(
                    thread_id=node["id"],
                    path=node.get("path", ""),
                    line=node.get("line"),
                    diff_hunk=comments[0]["diff_hunk"] if comments else "",
                    is_resolved=False,
                    url=comments[0]["url"] if comments else "",
                    comments=comments,
                )
            )

        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    return threads


def _rest_comment(c: dict[str, Any]) -> dict[str, Any]:
    return pr_common.comment(
        id=c["id"],
        author=(c.get("user") or {}).get("login", "unknown"),
        body=c.get("body", ""),
        created_at=c.get("created_at", ""),
        diff_hunk=c.get("diff_hunk", ""),
        url=c.get("html_url", ""),
    )


def _group_rest_comments(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    threads: dict[Any, dict[str, Any]] = {}
    for c in raw:
        cid = c["id"]
        parent = c.get("in_reply_to_id")
        key = parent if parent else cid
        if key not in threads:
            threads[key] = pr_common.thread(
                thread_id=str(cid),
                path=c.get("path", ""),
                line=c.get("line"),
                diff_hunk=c.get("diff_hunk", ""),
                is_resolved=None,
                url=c.get("html_url", ""),
            )
        threads[key]["comments"].append(_rest_comment(c))
    return list(threads.values())


def fetch_rest(target: Target, pr_number: int, rest_list: Callable[[str], list[Any]]):
    return _group_rest_comments(rest_list(f"repos/{target.path}/pulls/{pr_number}/comments"))


def _fetch_review_bodies(
    target: Target, pr_number: int, rest_list: Callable[[str], list[Any]]
) -> list[dict[str, Any]]:
    """Every non-empty PR review body (any author) — outside-diff-range comments live here."""
    raw = rest_list(f"repos/{target.path}/pulls/{pr_number}/reviews")
    return [
        {
            "author": (r.get("user") or {}).get("login", "unknown"),
            "state": r.get("state", ""),
            "commit_id": (r.get("commit_id") or "")[:12],
            "submitted_at": r.get("submitted_at", ""),
            "body": r.get("body", ""),
        }
        for r in raw
        if isinstance(r, dict) and (r.get("body") or "").strip()
    ]


def _fetch_summary_comments(
    target: Target, pr_number: int, rest_list: Callable[[str], list[Any]]
) -> list[dict[str, Any]]:
    """Every non-empty PR issue comment, any author — bot summaries AND human notes.

    Deliberately unfiltered by author. Filtering to `[bot]` logins dropped a
    maintainer's plain PR comment ("also fix this in the sibling module") from
    the output entirely, so `cr` could neither act on it nor record a verdict —
    the silent miss the out-of-thread fetch exists to prevent. `author` is on
    every record, so a caller wanting only bot summaries can still select them.

    `updated_at` is included so the CodeRabbit loop can measure a rate-limit wait
    from the summary's last edit, not just its creation.
    """
    raw = rest_list(f"repos/{target.path}/issues/{pr_number}/comments")
    return [
        {
            "author": (c.get("user") or {}).get("login", "unknown"),
            "created_at": c.get("created_at", ""),
            "updated_at": c.get("updated_at", ""),
            "body": c.get("body", ""),
        }
        for c in raw
        if isinstance(c, dict) and (c.get("body") or "").strip()
    ]


def _out_of_thread_notes(
    target: Target, pr_number: int, rest_list: Callable[[str], list[Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(review_bodies, summary_comments): the review surface that is NOT an inline
    thread. Each half is fetched independently and best-effort, so a failure of one
    (e.g. a rate-limited /issues/comments call) never discards the other — the
    outside-diff-range comments in review_bodies are exactly what this exists to
    surface, so they must survive a summary-comment fetch failure."""
    return (
        pr_common.best_effort(
            "review bodies", lambda: _fetch_review_bodies(target, pr_number, rest_list), []
        ),
        pr_common.best_effort(
            "summary comments", lambda: _fetch_summary_comments(target, pr_number, rest_list), []
        ),
    )


def _is_transient(err: Exception) -> bool:
    return isinstance(err, GhTransportError) and any(
        marker in str(err).lower() for marker in _TRANSIENT_MARKERS
    )


def fetch_comments(target: Target, pr_number: int) -> dict[str, Any]:
    token = _token_for(target)
    threads: list[dict[str, Any]]
    transport_label: str

    if _gh_available():
        try:
            threads = fetch_graphql(target, pr_number)
            rest_list = _gh_transport(target)
            transport_label = "gh-graphql"
        except subprocess.TimeoutExpired as timeout_err:
            # A timeout is the transient case by definition — the ordinary
            # symptom of the rate limiting and 5xx the marker scan below already
            # classifies. It needs its own clause because TimeoutExpired
            # subclasses SubprocessError, not RuntimeError or OSError, so it
            # matches neither the `except` below nor `_is_transient`, and would
            # otherwise surface as a bare "timed out after 30 seconds" that tells
            # the caller nothing about retrying.
            raise TransportError(
                f"GraphQL timed out ({timeout_err}); resolved state unknown — "
                "retry rather than fall back to resolved-blind REST."
            ) from timeout_err
        except (RuntimeError, OSError) as graphql_err:
            # Only transport/permanent-API failures reach the REST fallback:
            # _gh_graphql raises GhTransportError on transport failure and
            # fetch_graphql raises RuntimeError on GraphQL `errors`/PR-not-found.
            # A response-shape bug (TypeError/KeyError/JSONDecodeError from an
            # unexpected 200 body, e.g. `repository: null`) is NOT caught here — it
            # propagates rather than silently downgrading to resolved-blind REST.
            if _is_transient(graphql_err):
                raise TransportError(
                    f"GraphQL transiently unavailable ({graphql_err}); resolved state unknown — "
                    "retry rather than fall back to resolved-blind REST."
                ) from graphql_err
            pr_common.warn(f"GraphQL failed ({graphql_err}), falling back to REST")
            rest_list = _gh_transport(target)
            try:
                threads = fetch_rest(target, pr_number, rest_list)
                transport_label = "gh-rest"
            except Exception as rest_err:
                if not token:
                    raise TransportError(f"gh REST failed: {rest_err}") from rest_err
                pr_common.warn(f"gh REST failed ({rest_err}), falling back to token REST")
                rest_list = _token_transport(target, token)
                threads = fetch_rest(target, pr_number, rest_list)
                transport_label = "token-rest"
    else:
        if not token:
            raise TransportError("No auth available. Install the gh CLI or set GITHUB_TOKEN.")
        rest_list = _token_transport(target, token)
        threads = fetch_rest(target, pr_number, rest_list)
        transport_label = "token-rest"

    review_bodies, summary_comments = _out_of_thread_notes(target, pr_number, rest_list)
    return pr_common.comments_envelope(
        target,
        pr_number,
        threads=threads,
        review_bodies=review_bodies,
        summary_comments=summary_comments,
        transport=transport_label,
    )


# ── status ───────────────────────────────────────────────────────────────────
_REVIEW_STATES = {
    "APPROVED": "approved",
    "CHANGES_REQUESTED": "changes_requested",
    "COMMENTED": "commented",
}


def _checks(
    target: Target, sha: str, rest_list: Callable[[str], list[Any]]
) -> list[dict[str, Any]]:
    """Check runs plus legacy commit statuses — a repo can use either or both.

    Older integrations (and every `POST /statuses` caller) never create a check
    run, so reading only `/check-runs` reports a green PR as having no CI at all.
    """
    runs = rest_list(f"repos/{target.path}/commits/{sha}/check-runs")
    checks = [
        pr_common.check(
            name=r.get("name", ""),
            status=r.get("status", ""),
            conclusion=r.get("conclusion") or "",
            url=r.get("html_url", ""),
        )
        for page in runs
        if isinstance(page, dict)
        for r in (page.get("check_runs") or [])
    ]
    statuses = rest_list(f"repos/{target.path}/commits/{sha}/status")
    for page in statuses:
        if not isinstance(page, dict):
            continue
        for s in page.get("statuses") or []:
            state = (s.get("state") or "").lower()
            checks.append(
                pr_common.check(
                    name=s.get("context", ""),
                    status="completed"
                    if state in ("success", "failure", "error")
                    else "in_progress",
                    conclusion={"success": "success", "failure": "failure", "error": "failure"}.get(
                        state, ""
                    ),
                    url=s.get("target_url") or "",
                )
            )
    return checks


def _reviews(target: Target, pr_number: int, rest_list: Callable[[str], list[Any]]):
    """Latest verdict per reviewer.

    GitHub returns every review ever submitted, so a reviewer who requested
    changes and then approved appears twice; counting raw rows reports the PR as
    still blocked. `COMMENTED` never supersedes a verdict, so it is only kept
    when the reviewer has cast no other.
    """
    raw = rest_list(f"repos/{target.path}/pulls/{pr_number}/reviews")
    latest: dict[str, dict[str, Any]] = {}
    for r in raw:
        if not isinstance(r, dict):
            continue
        state = _REVIEW_STATES.get(r.get("state") or "")
        if state is None:
            continue  # PENDING / DISMISSED carry no verdict
        author = (r.get("user") or {}).get("login", "unknown")
        if state == "commented" and author in latest:
            continue
        latest[author] = pr_common.review(
            author=author, state=state, submitted_at=r.get("submitted_at", "")
        )
    return list(latest.values())


def fetch_status(target: Target, pr_number: int) -> dict[str, Any]:
    rest_list, get_one, _ = _transport(target)
    pr = get_one(f"repos/{target.path}/pulls/{pr_number}")
    if not isinstance(pr, dict) or "number" not in pr:
        raise TransportError(f"PR #{pr_number} not found in {target.path}")

    head_sha = ((pr.get("head") or {}).get("sha")) or ""
    state = "merged" if pr.get("merged") else (pr.get("state") or "")
    files = pr_common.best_effort(
        "changed files", lambda: rest_list(f"repos/{target.path}/pulls/{pr_number}/files"), []
    )
    return pr_common.status_envelope(
        target,
        pr_number,
        url=pr.get("html_url", ""),
        title=pr.get("title", ""),
        author=(pr.get("user") or {}).get("login", "unknown"),
        state=state,
        is_draft=bool(pr.get("draft")),
        source_branch=(pr.get("head") or {}).get("ref", ""),
        target_branch=(pr.get("base") or {}).get("ref", ""),
        head_sha=head_sha,
        created_at=pr.get("created_at", ""),
        updated_at=pr.get("updated_at", ""),
        mergeable=pr.get("mergeable"),
        merge_state=pr.get("mergeable_state", ""),
        checks=(
            pr_common.best_effort("checks", lambda: _checks(target, head_sha, rest_list), [])
            if head_sha
            else []
        ),
        reviews=pr_common.best_effort(
            "reviews", lambda: _reviews(target, pr_number, rest_list), []
        ),
        changed_files=[f.get("filename", "") for f in files if isinstance(f, dict)],
    )
