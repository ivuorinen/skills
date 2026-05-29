#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Fetch unresolved review threads from a GitHub PR.

Usage:
    fetch-pr-comments.py <owner> <repo> <pr_number>
    fetch-pr-comments.py <owner>/<repo> <pr_number>

Outputs a JSON array to stdout. Each element:
    {
        "thread_id": "...",
        "path": "src/foo.py",
        "diff_hunk": "@@ ... @@",
        "is_resolved": false | null,
        "comments": [{"id": "...", "author": "...", "body": "...",
                      "created_at": "...", "diff_hunk": "..."}]
    }

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
import subprocess
import sys
import urllib.request
from typing import Any

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
          comments(first: 50) {
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
        ["gh", "api", "--paginate", path],
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode().strip())
    return json.loads(result.stdout)


def _token_rest_paginate(base_url: str, token: str) -> list[Any]:
    results: list[Any] = []
    url: str | None = f"{base_url}?per_page=100"
    while url:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "ivuorinen-skills/cr-implementer",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            page = json.loads(resp.read())
            results.extend(page if isinstance(page, list) else [page])
            link = resp.headers.get("Link", "")
            url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
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

        page = resp["data"]["repository"]["pullRequest"]["reviewThreads"]
        for node in page["nodes"]:
            if node["isResolved"]:
                continue
            comments = [
                {
                    "id": c["id"],
                    "author": (c.get("author") or {}).get("login", "unknown"),
                    "body": c["body"],
                    "created_at": c["createdAt"],
                    "diff_hunk": c.get("diffHunk", ""),
                }
                for c in node["comments"]["nodes"]
            ]
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

    if _gh_available():
        try:
            threads = fetch_graphql(owner, repo, pr_number)
        except Exception as graphql_err:
            print(f"[warn] GraphQL failed ({graphql_err}), falling back to REST", file=sys.stderr)
            try:
                threads = fetch_rest_gh(owner, repo, pr_number)
            except Exception as rest_err:
                token = os.environ.get("GITHUB_TOKEN", "")
                if token:
                    print(
                        f"[warn] gh REST failed ({rest_err}), falling back to token REST",
                        file=sys.stderr,
                    )
                    try:
                        threads = fetch_rest_token(owner, repo, pr_number, token)
                    except Exception as token_err:
                        print(f"[error] REST API failed: {token_err}", file=sys.stderr)
                        sys.exit(1)
                else:
                    print(f"[error] gh REST failed: {rest_err}", file=sys.stderr)
                    sys.exit(1)
    else:
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            print(
                "[error] No auth available. Install gh CLI or set GITHUB_TOKEN.",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            threads = fetch_rest_token(owner, repo, pr_number, token)
        except Exception as err:
            print(f"[error] REST API failed: {err}", file=sys.stderr)
            sys.exit(1)

    print(json.dumps(threads, indent=2))


if __name__ == "__main__":
    main()
