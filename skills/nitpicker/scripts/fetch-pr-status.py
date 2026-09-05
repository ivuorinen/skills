#!/usr/bin/env python3
"""Fetch a PR/MR's status: state, branches, CI checks, review verdicts, files.

Covers GitHub, GitLab and Bitbucket Cloud behind one output format, so `cr` reads
the same JSON whichever platform hosts the PR. Companion to
`fetch-pr-comments.py`; this one answers "is the PR still open, did CI pass on
the head commit, has anyone approved", the questions `cr` asks in Step 1 and
again after every push.

Usage:
    fetch-pr-status.py <pr-url>
    fetch-pr-status.py <pr_number>                    # repo from the git remote
    fetch-pr-status.py <owner>/<repo> <pr_number>
    fetch-pr-status.py <host>/<group>/<project> <pr_number>
    fetch-pr-status.py <owner> <repo> <pr_number>

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
      "url": "...",
      "title": "...",
      "author": "...",
      "state": "open" | "closed" | "merged",
      "is_draft": false,
      "source_branch": "feat/x",
      "target_branch": "main",
      "head_sha": "...",
      "created_at": "...", "updated_at": "...",
      "mergeable": true | false | null,
      "merge_state": "clean" | "mergeable" | "" ,
      "checks": [{"name", "status", "conclusion", "url"}],
      "checks_summary": {"total", "success", "failure", "neutral", "pending"},
      "reviews": [{"author", "state", "submitted_at"}],
      "review_summary": {"approved", "changes_requested", "commented"},
      "changed_files": ["src/foo.py", ...]
    }

`state` is normalised to open/closed/merged across platforms — GitLab spells open
`opened` and Bitbucket spells it `OPEN`, and `is_draft` is carried separately, so
a caller never string-matches platform vocabulary. `check.status` is
queued|in_progress|completed and `check.conclusion` is
success|failure|neutral|cancelled|skipped, empty while a check is still running;
`checks_summary` totals them, so `total == success + failure + neutral + pending`
on every platform.

`mergeable` is tri-state: `null` means the platform had not finished computing it
(or, on Bitbucket, does not expose one at all) — which is not the same as "no".

`head_sha` is what makes a bot review's freshness checkable: a review whose
commit range predates this SHA has not seen the latest push.

Secondary data (checks, reviews, changed files) is best-effort — a failure there
degrades the result with a `[warn]` on stderr rather than losing the PR record.

Auth, per platform:
    GitHub    gh CLI -> GITHUB_TOKEN. A token is sent to a non-github.com host
              only when GH_HOST names that host.
    GitLab    GITLAB_TOKEN -> glab CLI. A token is sent to a non-gitlab.com host
              only when GITLAB_HOST names that host.
    Bitbucket BITBUCKET_TOKEN, or BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD.

Exit codes: 0 = success, 1 = API/auth error, 2 = usage error.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr_common

if __name__ == "__main__":
    sys.exit(pr_common.run_cli(__doc__ or "", "fetch_status", sys.argv[1:]))
