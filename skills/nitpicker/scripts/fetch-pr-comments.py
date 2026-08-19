#!/usr/bin/env python3
"""Fetch a PR/MR review surface — inline threads AND out-of-thread notes.

Covers GitHub, GitLab and Bitbucket Cloud behind one output format, so `cr` reads
the same JSON whichever platform hosts the review.

Usage:
    fetch-pr-comments.py <pr-url>
    fetch-pr-comments.py <pr_number>                    # repo from the git remote
    fetch-pr-comments.py <owner>/<repo> <pr_number>
    fetch-pr-comments.py <host>/<group>/<project> <pr_number>
    fetch-pr-comments.py <owner> <repo> <pr_number>

A leading segment counts as a host only when a platform claims it (`github.*`,
`gitlab.*`, `bitbucket.org`); anything else is part of the project path, so a
GitLab group whose name contains a dot is not mistaken for a hostname. Name a
custom self-hosted host with the PR URL, or omit the repo and let it come from
the git remote.

Options:
    --platform github|gitlab|bitbucket   Override platform detection. Required
                                         for a self-hosted host whose name does
                                         not start with `gitlab.`/`github.`.
    --remote <name>                      Git remote to read (default: origin).
    --help, -h                           This text.

Outputs a JSON object to stdout:
    {
      "platform": "github" | "gitlab" | "bitbucket",
      "host": "github.com",
      "repo": "owner/repo",
      "pr_number": 42,
      "transport": "gh-graphql" | "gh-rest" | "token-rest" | "glab" | ...,
      "threads": [
        {
          "thread_id": "...",
          "path": "src/foo.py",
          "line": 12 | null,
          "diff_hunk": "@@ ... @@",
          "is_resolved": false | true | null,
          "url": "...",
          "comments": [{"id", "author", "body", "created_at", "diff_hunk", "url"}]
        }
      ],
      "review_bodies": [{"author", "state", "commit_id", "submitted_at", "body"}],
      "summary_comments": [{"author", "created_at", "updated_at", "body"}]
    }

`threads` are the inline review threads. `review_bodies` and `summary_comments`
carry notices that do NOT appear as inline threads and are historically missed: a
reviewer's outside-diff-range comments live in the review BODY, and bots
(CodeRabbit, Copilot) post summaries as issue comments. Evaluate all three.

Platform differences are expressed as empty values, never as missing keys:
  * `review_bodies` is always empty on GitLab and Bitbucket — neither has a
    review-body concept; a reviewer's prose is an ordinary comment and lands in
    `summary_comments`.
  * `diff_hunk` is empty on GitLab and Bitbucket, which report a line anchor
    rather than a hunk; `line` carries it there.

`is_resolved` is tri-state. `null` means the transport in use could not report
resolution (GitHub's REST fallback) — the caller must then check whether the
flagged code still exists rather than assuming the thread is live.

Auth, per platform:
    GitHub    gh CLI (GraphQL, the only source of `is_resolved`) -> gh REST ->
              GITHUB_TOKEN. A token is sent to a non-github.com host only when
              GH_HOST names that host.
    GitLab    GITLAB_TOKEN -> glab CLI. The instance comes from the git remote,
              so self-hosted needs no extra setting. GITLAB_HOST only pins which
              instance the token belongs to; naming a different host withholds it.
    Bitbucket BITBUCKET_TOKEN, or BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD.

Exit codes: 0 = success, 1 = API/auth error, 2 = usage error.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr_common

if __name__ == "__main__":
    sys.exit(pr_common.run_cli(__doc__ or "", "fetch_comments", sys.argv[1:]))
