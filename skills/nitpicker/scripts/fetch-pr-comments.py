#!/usr/bin/env python3
"""Fetch a GitHub PR's review surface: inline threads AND out-of-thread notes.

Usage:
    fetch-pr-comments.py <owner> <repo> <pr_number>
    fetch-pr-comments.py <owner>/<repo> <pr_number>

Outputs a JSON object to stdout:
    {
      "threads": [
        {
          "thread_id": "...",
          "path": "src/foo.py",
          "diff_hunk": "@@ ... @@",
          "is_resolved": false | null,
          "comments": [{"id": "...", "author": "...", "body": "...",
                        "created_at": "...", "diff_hunk": "..."}]
        }
      ],
      "review_bodies": [
        {"author": "...", "state": "...", "commit_id": "...",
         "submitted_at": "...", "body": "..."}
      ],
      "summary_comments": [
        {"author": "...", "created_at": "...", "updated_at": "...", "body": "..."}
      ]
    }

`threads` are the inline review threads (the original output). `review_bodies` and
`summary_comments` carry notices that do NOT appear as inline threads and were
historically missed: a reviewer's outside-diff-range comments live in the review
BODY, and bots (CodeRabbit, Copilot) post summaries as issue comments. Both are
included so a single fetch surfaces every actionable notice. `review_bodies` holds
every non-empty PR review body (any author); `summary_comments` holds every
non-empty PR issue comment (also any author — bot summaries and human notes
alike; each record carries `author`, so the caller distinguishes them). Both are
best-effort: if that fetch fails the run still returns `threads` with the two
lists empty.

is_resolved is false when using GraphQL (preferred). null means REST was used and
resolved state is unknown — the caller must check whether the flagged code still exists.

Authentication priority:
    1. gh CLI + GraphQL (exposes isResolved — unresolved threads only returned)
    2. gh CLI + REST    (all threads; resolved state unknown)
    3. GITHUB_TOKEN env var + REST (all threads; resolved state unknown)

Exit codes: 0 = success, 1 = API/auth error, 2 = usage error.
"""

import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from typing import Any

_OWNER_REPO_RE = re.compile(r"[A-Za-z0-9._-]+")

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
          comments(first: 100) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              body
              createdAt
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
          author { login }
          diffHunk
        }
      }
    }
  }
}
"""


def _gh_available() -> bool:
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def _gh_graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    result = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=payload,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode().strip())
    return json.loads(result.stdout)


def _gh_rest_paginate(path: str) -> list[Any]:
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", path],
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode().strip())
    pages: list[list[Any]] = json.loads(result.stdout)
    return [item for page in pages for item in page]


class _TokenSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Strip the Authorization header on a redirect to any host other than the
    GitHub API. urllib follows 3xx transparently and, unlike requests, keeps the
    header across hosts — so without this a cross-host redirect from api.github.com
    would forward the token off-host, defeating the same-host guard below.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != "api.github.com":
            for key in [k for k in new.headers if k.lower() == "authorization"]:
                del new.headers[key]
        return new


# Install as the process default so plain urllib.request.urlopen (below) inherits
# the off-host Authorization stripping without a call-site change.
urllib.request.install_opener(urllib.request.build_opener(_TokenSafeRedirectHandler()))


def _token_rest_paginate(base_url: str, token: str) -> list[Any]:
    results: list[Any] = []
    url: str | None = f"{base_url}?per_page=100"
    while url:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "ivuorinen-skills/nitpicker-cr",
            },
        )
        # Scheme and host are both pinned: the first URL is built from a literal
        # https://api.github.com base, and every paginated URL is checked below
        # before it is assigned back to `url`.
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
            page = json.loads(resp.read())
            results.extend(page if isinstance(page, list) else [page])
            link = resp.headers.get("Link", "")
            url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    next_url = part.split(";")[0].strip().strip("<>")
                    # Never send the token to another host, and never over
                    # plaintext: the Link header is server-controlled, so a
                    # host-only check would still forward the Authorization
                    # header over http:// to a matching hostname.
                    split = urllib.parse.urlsplit(next_url)
                    if split.netloc != "api.github.com" or split.scheme != "https":
                        break
                    url = next_url
                    break
    return results


def _build_thread(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "thread_id": str(comment["id"]),
        "path": comment.get("path", ""),
        "is_resolved": None,
        "diff_hunk": comment.get("diff_hunk", ""),
        "comments": [],
    }


def _build_comment(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(comment["id"]),
        "author": (comment.get("user") or {}).get("login", "unknown"),
        "body": comment.get("body", ""),
        "created_at": comment.get("created_at", ""),
        "diff_hunk": comment.get("diff_hunk", ""),
    }


def _gql_comment(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": c["id"],
        "author": (c.get("author") or {}).get("login", "unknown"),
        "body": c["body"],
        "created_at": c["createdAt"],
        "diff_hunk": c.get("diffHunk", ""),
    }


def _all_thread_comments(node: dict[str, Any]) -> list[dict[str, Any]]:
    """All comments for one thread, following the inner `comments` cursor so a
    thread with >100 comments is not silently truncated to its first page."""
    conn = node["comments"]
    comments = [_gql_comment(c) for c in conn["nodes"]]
    info = conn.get("pageInfo") or {}
    cursor = info.get("endCursor")
    while info.get("hasNextPage") and cursor:
        sub = _gh_graphql(_THREAD_COMMENTS_QUERY, {"id": node["id"], "cursor": cursor})
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


def fetch_graphql(owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
    threads: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        resp = _gh_graphql(
            _GRAPHQL_QUERY,
            {"owner": owner, "repo": repo, "pr": pr_number, "cursor": cursor},
        )
        if "errors" in resp:
            raise RuntimeError(json.dumps(resp["errors"]))

        pr = resp["data"]["repository"]["pullRequest"]
        if pr is None:
            raise RuntimeError(f"PR #{pr_number} not found in {owner}/{repo}")
        page = pr["reviewThreads"]
        for node in page["nodes"]:
            if node["isResolved"]:
                continue
            comments = _all_thread_comments(node)
            threads.append(
                {
                    "thread_id": node["id"],
                    "path": node.get("path", ""),
                    "is_resolved": False,
                    "diff_hunk": comments[0]["diff_hunk"] if comments else "",
                    "comments": comments,
                }
            )

        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    return threads


def _group_rest_comments(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    threads: dict[int, dict[str, Any]] = {}
    for comment in raw:
        cid = comment["id"]
        parent = comment.get("in_reply_to_id")
        key = parent if parent else cid
        if key not in threads:
            threads[key] = _build_thread(comment)
        threads[key]["comments"].append(_build_comment(comment))
    return list(threads.values())


def fetch_rest_gh(owner: str, repo: str, pr_number: int) -> list[dict[str, Any]]:
    raw = _gh_rest_paginate(f"repos/{owner}/{repo}/pulls/{pr_number}/comments")
    return _group_rest_comments(raw)


def fetch_rest_token(owner: str, repo: str, pr_number: int, token: str) -> list[dict[str, Any]]:
    base = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"
    raw = _token_rest_paginate(base, token)
    return _group_rest_comments(raw)


def _token_transport(token: str) -> Any:
    """A rest_list callable(path) -> list bound to the GITHUB_TOKEN REST transport.
    main() hands the out-of-thread fetch whichever transport actually fetched the
    threads, so a gh path that failed into token REST does not silently re-select
    a broken gh for the notes."""
    return lambda path: _token_rest_paginate(f"https://api.github.com/{path}", token)


def _fetch_review_bodies(
    owner: str, repo: str, pr_number: int, rest_list: Any
) -> list[dict[str, Any]]:
    """Every non-empty PR review body (any author) — outside-diff-range comments live here."""
    reviews_raw = rest_list(f"repos/{owner}/{repo}/pulls/{pr_number}/reviews")
    return [
        {
            "author": (r.get("user") or {}).get("login", "unknown"),
            "state": r.get("state", ""),
            "commit_id": (r.get("commit_id") or "")[:12],
            "submitted_at": r.get("submitted_at", ""),
            "body": r.get("body", ""),
        }
        for r in reviews_raw
        if isinstance(r, dict) and (r.get("body") or "").strip()
    ]


def _fetch_summary_comments(
    owner: str, repo: str, pr_number: int, rest_list: Any
) -> list[dict[str, Any]]:
    """Every non-empty PR issue comment, any author — bot summaries AND human notes.

    Deliberately unfiltered by author, matching `_fetch_review_bodies`. Filtering
    to `[bot]` logins dropped a maintainer's plain PR comment ("also fix this in
    the sibling module") from the output entirely, so `cr` could neither act on
    it nor record a verdict — the silent miss the out-of-thread fetch exists to
    prevent. `author` is on every record, so a caller that wants only bot
    summaries can still select them.

    `updated_at` is included so the CodeRabbit loop can measure a rate-limit wait
    from the summary's last edit, not just its creation.
    """
    comments_raw = rest_list(f"repos/{owner}/{repo}/issues/{pr_number}/comments")
    return [
        {
            "author": (c.get("user") or {}).get("login", "unknown"),
            "created_at": c.get("created_at", ""),
            "updated_at": c.get("updated_at", ""),
            "body": c.get("body", ""),
        }
        for c in comments_raw
        if isinstance(c, dict) and (c.get("body") or "").strip()
    ]


def _fetch_out_of_thread_notes(
    owner: str, repo: str, pr_number: int, rest_list: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (review_bodies, summary_comments): the review surface that is NOT an
    inline thread. Each half is fetched independently and best-effort, so a failure
    of one (e.g. a rate-limited /issues/comments call) never discards the other —
    the outside-diff-range comments in review_bodies are exactly what this fix
    exists to surface, so they must survive a summary-comment fetch failure."""
    review_bodies: list[dict[str, Any]] = []
    summary_comments: list[dict[str, Any]] = []
    try:
        review_bodies = _fetch_review_bodies(owner, repo, pr_number, rest_list)
    except Exception as err:
        print(f"[warn] could not fetch review bodies ({err})", file=sys.stderr)
    try:
        summary_comments = _fetch_summary_comments(owner, repo, pr_number, rest_list)
    except Exception as err:
        print(f"[warn] could not fetch summary comments ({err})", file=sys.stderr)
    return review_bodies, summary_comments


def main() -> None:
    args = sys.argv[1:]

    try:
        if len(args) == 2 and "/" in args[0]:
            owner, repo = args[0].split("/", 1)
            pr_number = int(args[1])
        elif len(args) == 3:
            owner, repo, pr_number = args[0], args[1], int(args[2])
        else:
            raise ValueError("wrong argument count")
    except ValueError:
        print(
            "Usage: fetch-pr-comments.py <owner> <repo> <pr_number>\n"
            "       fetch-pr-comments.py <owner>/<repo> <pr_number>",
            file=sys.stderr,
        )
        sys.exit(2)

    # owner/repo are interpolated into REST URLs and the `gh api` path; reject
    # anything outside GitHub's allowed name charset (blocks /, ?, @, spaces).
    # The charset alone permits '.'/'..' (dots are legal in repo names), so the
    # bare traversal tokens are rejected explicitly — otherwise the comment above
    # would promise a guard the regex does not actually provide.
    for label, value in (("owner", owner), ("repo", repo)):
        if not _OWNER_REPO_RE.fullmatch(value) or value in (".", ".."):
            print(f"[error] invalid {label}: {value!r}", file=sys.stderr)
            sys.exit(2)

    token = os.environ.get("GITHUB_TOKEN", "")
    notes_rest: Any = None  # the transport that fetched threads, reused for the notes fetch

    if _gh_available():
        try:
            threads = fetch_graphql(owner, repo, pr_number)
            notes_rest = _gh_rest_paginate
        except (RuntimeError, subprocess.SubprocessError) as graphql_err:
            # Only transport/permanent-API failures reach the REST fallback:
            # _gh_graphql raises RuntimeError (gh stderr) on transport failure and
            # fetch_graphql raises RuntimeError on GraphQL `errors`/PR-not-found.
            # A response-shape bug (TypeError/KeyError/JSONDecodeError from an
            # unexpected 200 body, e.g. `repository: null`) is NOT caught here — it
            # propagates as a hard error rather than silently downgrading to
            # resolved-blind REST and re-surfacing resolved threads as unresolved.
            # GraphQL is the only source of `isResolved`; the REST fallback returns
            # every thread with is_resolved=None. A transient GraphQL error
            # (secondary rate limit, 5xx) must therefore NOT silently downgrade to
            # REST — that re-surfaces already-resolved threads as unresolved. Hard-
            # fail so the caller retries; only a permanent error falls back to REST.
            msg = str(graphql_err).lower()
            if any(
                s in msg
                for s in (
                    "rate limit",
                    "rate_limit",
                    "ratelimited",
                    "secondary",
                    "502",
                    "503",
                    "504",
                )
            ):
                print(
                    f"[error] GraphQL transiently unavailable ({graphql_err}); resolved "
                    "state unknown — retry rather than fall back to resolved-blind REST.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"[warn] GraphQL failed ({graphql_err}), falling back to REST", file=sys.stderr)
            try:
                threads = fetch_rest_gh(owner, repo, pr_number)
                notes_rest = _gh_rest_paginate
            except Exception as rest_err:
                if token:
                    print(
                        f"[warn] gh REST failed ({rest_err}), falling back to token REST",
                        file=sys.stderr,
                    )
                    try:
                        threads = fetch_rest_token(owner, repo, pr_number, token)
                        notes_rest = _token_transport(token)
                    except Exception as token_err:
                        print(f"[error] REST API failed: {token_err}", file=sys.stderr)
                        sys.exit(1)
                else:
                    print(f"[error] gh REST failed: {rest_err}", file=sys.stderr)
                    sys.exit(1)
    else:
        if not token:
            print(
                "[error] No auth available. Install gh CLI or set GITHUB_TOKEN.",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            threads = fetch_rest_token(owner, repo, pr_number, token)
            notes_rest = _token_transport(token)
        except Exception as err:
            print(f"[error] REST API failed: {err}", file=sys.stderr)
            sys.exit(1)

    # Out-of-thread notes (review bodies, bot summary comments) — best-effort: a
    # failure here must not lose the threads that are the primary result.
    review_bodies: list[dict[str, Any]] = []
    summary_comments: list[dict[str, Any]] = []
    if notes_rest is not None:
        try:
            review_bodies, summary_comments = _fetch_out_of_thread_notes(
                owner, repo, pr_number, notes_rest
            )
        except Exception as notes_err:
            print(
                f"[warn] could not fetch out-of-thread notes ({notes_err}); "
                "returning inline threads only",
                file=sys.stderr,
            )

    print(
        json.dumps(
            {
                "threads": threads,
                "review_bodies": review_bodies,
                "summary_comments": summary_comments,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
