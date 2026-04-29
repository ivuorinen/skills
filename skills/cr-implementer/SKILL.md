---
name: cr-implementer
description: Use when implementing unresolved GitHub PR review comments. Invoke when told "fix the cr comments", "implement review feedback", "address pr comments", or when a PR has unresolved reviewer comments that need addressing.
---

# CR Implementer

## Overview

Tool-driven implementation of unresolved GitHub PR review comments. Fetches every comment thread using whatever GitHub API access is available, evaluates each for technical validity and current applicability, implements valid ones one at a time with a full validation pass after each, and scans for structurally identical issues elsewhere in the codebase. Every comment receives an explicit verdict: Implemented, Pushed Back, or Skipped. Nothing is silently ignored. Replies are drafted locally and posted only after the fixes are pushed and the user confirms — so the reviewer can see the change before reading "Fixed in …".

## When to Use

- A GitHub PR has review comments that need implementing
- After receiving CR feedback from humans or automated reviewers (CodeRabbit, Copilot, etc.)
- When told "fix the cr comments", "implement review feedback", "address pr comments", "cr review comment, fix it", or similar
- When preparing a branch for merge and unresolved comments remain

## Process

### Step 1 — Setup

Run these before touching any code:

**1. Detect GitHub API access method.** Try each in order and stop at the first that works:

- **Method A — `gh` CLI:**
  ```bash
  which gh && gh auth status
  ```
  If this succeeds, use `gh api` for all GitHub API calls and `gh pr view` for PR detection.

- **Method B — `GITHUB_TOKEN` + available HTTP client:**
  ```bash
  echo $GITHUB_TOKEN
  ```
  If the token is set, verify it with a test request:
  ```
  GET https://api.github.com/user
  Authorization: Bearer $GITHUB_TOKEN
  ```
  If the test request returns a non-200 status, the token is invalid — do not proceed with Method B; fall through to Method C. If it returns 200, use `curl`, context-mode `ctx_execute` JavaScript `fetch`, or any other HTTP tool in the environment for all subsequent API calls.

- **Method C — GraphQL via any HTTP client:**
  All operations in this skill have GraphQL equivalents (see steps below). Use `https://api.github.com/graphql` with `Authorization: Bearer $GITHUB_TOKEN`.

If none yield an authenticated GitHub API connection, stop and report: "GitHub API access requires one of: `gh` CLI, `GITHUB_TOKEN` + an HTTP client, or context-mode MCP with `GITHUB_TOKEN`."

Note the method chosen. Use the **same method for fetching and replying** — do not mix methods between steps.

**2. Resolve owner, repo, and PR number.**

Get owner and repo from the git remote:
```bash
git remote get-url origin
# parse: git@github.com:owner/repo.git  OR  https://github.com/owner/repo
```

If the PR number is not supplied by the user, detect it:
- **Method A:** `gh pr view --json number,url,headRefName`
- **Method B/C:** Get the current branch with `git branch --show-current`, then call:
  `GET /repos/{owner}/{repo}/pulls?head={owner}:{branch}&state=open`

Confirm the PR is correct before proceeding. If ambiguous, ask the user.

**3. Identify the project's canonical check command** by inspecting in order:
   - `Makefile` — look for a `check`, `test`, or `lint` target
   - `package.json` `scripts` field
   - `pyproject.toml` — identify configured tools (`ruff`, `pytest`, `mypy`, etc.) and construct their default invocations
   - `README` or `CONTRIBUTING` for documented test commands

   If the check command cannot be determined, ask the user before continuing.

**4. Confirm the commit message convention:**
```bash
git log --oneline -10
```
Note the prefix convention in use (e.g. `fix:`, `feat:`, `chore:`).

### Step 2 — Fetch All Review Comments

Fetch all inline review comments from the PR using the method chosen in Step 1:

- **Method A:** `gh api repos/{owner}/{repo}/pulls/{pr_number}/comments`
- **Method B:** `GET https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments`
- **Method C (GraphQL):**
  ```graphql
  query {
    repository(owner: "{owner}", name: "{repo}") {
      pullRequest(number: {pr_number}) {
        reviewThreads(first: 100) {
          nodes {
            id
            isResolved
            comments(first: 50) {
              nodes { id body path diffHunk createdAt author { login } }
            }
          }
        }
      }
    }
  }
  ```
  GraphQL `reviewThreads` exposes `isResolved` — use it to skip already-resolved threads.

The GitHub REST API (Methods A and B) does not expose a resolved/unresolved state on individual comments. When using Method A or B, process every comment — Step 3 assigns the Skipped verdict when the flagged code no longer exists.

### Step 3 — Evaluate Each Comment

For every comment, before touching any code:

1. Read the `diff_hunk` (REST) or `diffHunk` (GraphQL) to understand what file and line are flagged.
2. Open the current state of that file and verify whether the flagged code still exists.
3. Assess technical validity:
   - Is the suggestion correct for this codebase's conventions and constraints?
   - Does it conflict with a prior architectural or style decision?
   - Is the flagged issue a real defect or a false positive?
4. Assign a verdict:
   - **Implement** — issue is valid and the flagged code still exists
   - **Pushed Back** — suggestion is technically incorrect or conflicts with established decisions; state the concrete reason
   - **Skipped** — flagged code no longer exists in its original form (already changed or removed)

Do not implement without evaluating first. Do not assign Pushed Back without technical reasoning. Do not assign Skipped without confirming the code is actually gone.

### Step 4 — Implement One Comment at a Time

For each **Implement** verdict, in order:

1. Make the minimal change that directly addresses the comment. No unrelated cleanup.
2. Run the check command identified in Step 1.
3. Confirm the fix fully and directly resolves the flagged issue — not merely nearby code.
4. If the check fails:
   - Diagnose and fix the failure before moving to the next comment.
   - Re-run until clean.
5. Search the codebase for identical or structurally similar instances of the same defect:
   ```bash
   rg '<pattern>'
   ```
   Fix every instance found. Run the check again — must be clean before moving on.

### Step 5 — Draft Replies (Do Not Post Yet)

After each verdict, draft the reply text locally. Do not post to GitHub.

Reply content by verdict:
- **Implemented**: one sentence describing what changed and where, including any similar instances fixed in the codebase scan.
- **Pushed Back**: the concrete technical reason the suggestion was not applied, and what the existing approach does instead.
- **Skipped**: confirm the flagged code no longer exists and note where/when it was removed if known.

Hold all drafts until Step 6.

### Step 6 — Present Results and Ask for Next Action

After all comments are processed, emit a summary including the drafted reply for each comment:

```
Implemented:   N
Pushed back:   N
Skipped:       N

Drafted replies:
  #<comment_id> — <one-line preview of reply>
  ...
```

**If there are Implemented verdicts** (code was changed):

```
What next?
  1. Leave it (no commit, no replies posted)
  2. Commit only (no push, no replies posted)
  3. Commit and push
```

- **Leave it** or **Commit only**: apply the commit if chosen; do not push; do not post replies. Inform the user: "Replies not posted — push the branch first so the reviewer can see the changes."
- **Commit and push**: stage only the files changed by the review fixes; write the commit message using the convention confirmed in Step 1; never use `--no-verify`; push to the current branch's remote tracking branch (never directly to `main` or `master`). If the push fails, stop, report the error, and do not post any replies — ask the user to resolve the push failure and re-run this step. After the push succeeds, ask: **"Post replies to GitHub now? (y/n)"** If yes, post all drafted replies. If no, inform the user.

**If there are no Implemented verdicts** (only Pushed Back and Skipped — no code was changed):

```
Post replies now? (y/n)
```

Post replies immediately on confirmation — no push is needed because no code changed.

**Posting replies** (using the method chosen in Step 1):
- **Method A:** `gh api repos/{owner}/{repo}/pulls/{pr_number}/comments/{comment_id}/replies -f body="<reply>"`
- **Method B:** `POST https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments/{comment_id}/replies` with body `{"body": "<reply>"}`
- **Method C (GraphQL):** use the thread `id` from the Step 2 query:
  ```graphql
  mutation {
    addPullRequestReviewThreadReply(input: {
      pullRequestReviewThreadId: "{thread_id}",
      body: "<reply>"
    }) { comment { id } }
  }
  ```

## Output Format

Results are presented inline to the user. No findings file is written. Replies are drafted locally and posted to GitHub PR threads only after the user confirms in Step 6.

## Fix Strategy

- **One comment → one fix → one validation cycle.** Never batch multiple comments before running the check.
- If the check fails after a fix, resolve that failure before moving to the next comment. Carry-forward failures invalidate subsequent verdicts.
- Structurally identical instances of the same defect found during the codebase scan are fixed in the same change as the originating comment — this is not scope creep, it is completeness.
- Use the **same GitHub API method** for fetching (Step 2) and replying (Step 6). Never mix methods.
- Commit messages follow the repository's existing conventional commit format confirmed in Step 1.
- Never commit with `--no-verify`.
- Never push without explicit user authorisation granted in Step 6.
- Never post replies without explicit user authorisation granted in Step 6.

## Common Mistakes

- **Assuming `gh` is available**: detect the GitHub API method in Step 1 and use it consistently. Never call `gh` without confirming it exists.
- **Mixing fetch and reply methods**: the method chosen in Step 1 for fetching must be used for replying. GraphQL replies require a `thread_id` that is only available if GraphQL was used to fetch.
- **Batching comments**: implementing more than one comment before running the check. Each comment requires its own fix-and-verify cycle.
- **Skipping the codebase scan**: fixing only the flagged line and not scanning for structurally identical instances of the same defect elsewhere. A partial fix is an incomplete fix.
- **Posting replies before push** (when code changed): for Implemented verdicts, replies are posted only after the branch is pushed and the user confirms. Never post a reply before the reviewer can see the fix.
- **Blocking replies when nothing was pushed** (when no code changed): for runs with only Pushed Back and Skipped verdicts, no push is needed — ask directly whether to post replies.
- **Posting replies after a failed push**: if push fails, stop. Do not post replies pointing reviewers at code they cannot see.
- **Treating bot comments as lower priority**: CodeRabbit, Copilot, and other automated reviewers are evaluated on technical merit, not commenter type.
- **Silent skipping**: assigning no verdict to a comment, or deferring without stating why. Every comment receives an explicit verdict and a drafted reply.
- **Committing without authorisation**: present the summary, wait for the user's explicit choice.
- **Scope creep**: making changes unrelated to the flagged defect category alongside a comment fix. Fixing identical instances of the same defect (codebase scan) is in scope. Fixing different defects noticed nearby is not.
- **Marking already-resolved code as Implemented**: if the flagged code was changed in a prior commit and no longer has the issue, the verdict is Skipped, not Implemented.
