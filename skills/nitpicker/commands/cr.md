# /nitpicker cr — CR Implementer

Tool-driven implementation of unresolved GitHub PR review comments: fetch every comment thread, evaluate each for technical validity, implement valid ones one at a time with a full validation pass after each, and scan the codebase for structurally identical issues. Every comment receives an explicit verdict — Implemented, Pushed Back, or Skipped — nothing is silently ignored. Replies are drafted locally and posted only after the fixes are pushed and the user confirms.

This command writes no findings file — results are presented inline, and the interactive leave/commit/push flow below overrides the findings-store protocol in `_conventions.md`.

## When to use

- A GitHub PR has review comments that need implementing
- After receiving CR feedback from humans or automated reviewers (CodeRabbit, Copilot, etc.)
- When told "fix the cr comments", "implement review feedback", "address pr comments", or similar
- When preparing a branch for merge and unresolved comments remain

For producing a review of your own, use `/nitpicker pr`.

## Process

### Step 1 — Setup

Run these before touching any code:

**1. Detect GitHub API access method.** Try each in order and stop at the first that works:

- **Method A — `gh` CLI:** `which gh && gh auth status`. If this succeeds, use `gh api` for all GitHub API calls and `gh pr view` for PR detection.
- **Method B — `GITHUB_TOKEN` + available HTTP client:** `[ -n "$GITHUB_TOKEN" ]`. If the token is present, use `curl`, context-mode `ctx_execute` JavaScript `fetch`, or any other HTTP tool. Do not validate with `GET /user` — GitHub Actions and App installation tokens return 403 there even when valid; the Step 2 call surfaces any auth failure.
- **Method C — GraphQL via any HTTP client:** all operations here have GraphQL equivalents. Use `https://api.github.com/graphql` with `Authorization: Bearer $GITHUB_TOKEN`. Requires `GITHUB_TOKEN` — not an independent fallback without one.

If none yield an authenticated connection, stop and report: "GitHub API access requires one of: `gh` CLI, `GITHUB_TOKEN` + an HTTP client, or context-mode MCP with `GITHUB_TOKEN`."

Note the method chosen. Use the **same method for fetching and replying** — never mix methods between steps.

**2. Resolve owner, repo, and PR number.** Parse `git remote get-url origin` (`git@github.com:owner/repo.git` or `https://github.com/owner/repo`). If the PR number is not supplied:

- **Method A:** `gh pr view --json number,url,headRefName`
- **Method B/C:** `git branch --show-current`, then `GET /repos/{owner}/{repo}/pulls?head={owner}:{branch}&state=open`

Confirm the PR is correct before proceeding. If ambiguous, ask the user.

**3. Identify the project's canonical check command** by inspecting in order: `Makefile` (`check`/`test`/`lint` targets), `package.json` `scripts`, `pyproject.toml` (configured tools and their default invocations), then `README`/`CONTRIBUTING`. If it cannot be determined, ask the user before continuing.

**4. Confirm the commit message convention:** `git log --oneline -10`; note the prefix convention in use (e.g. `fix:`, `feat:`, `chore:`).

### Step 2 — Fetch all review comments

Prefer the bundled fetcher — it attempts GraphQL first (gives `isResolved`) and falls back to REST via `gh` CLI or `GITHUB_TOKEN`:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/fetch-pr-comments.py" <owner>/<repo> <pr_number>
```

Non-Claude agents resolve the path relative to the nitpicker skill directory. It outputs a JSON array of thread objects.

If running the API calls manually instead, use the method chosen in Step 1:

- **Method A:** `gh api --paginate repos/{owner}/{repo}/pulls/{pr_number}/comments`
- **Method B:** `GET https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments?per_page=100` — follow `Link: <url>; rel="next"` headers until no `next` remains.
- **Method C (GraphQL):**

  ```graphql
  query {
    repository(owner: "{owner}", name: "{repo}") {
      pullRequest(number: {pr_number}) {
        reviewThreads(first: 100) {
          pageInfo { hasNextPage endCursor }
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

  If `pageInfo.hasNextPage` is true, re-query with `reviewThreads(first: 100, after: "{endCursor}")` until false. `comments(first: 50)` is not paginated — threads with more than 50 comments are truncated; an accepted limitation. GraphQL `reviewThreads` exposes `isResolved` — use it to skip already-resolved threads.

The REST API (Methods A and B) does not expose resolved state on individual comments — process every comment; Step 3 assigns Skipped when the flagged code no longer exists.

### Step 3 — Evaluate each comment

For every comment, before touching any code:

1. Read the `diff_hunk` (REST) or `diffHunk` (GraphQL) to understand what file and line are flagged.
2. Open the current state of that file and verify whether the flagged code still exists.
3. Assess technical validity: is the suggestion correct for this codebase's conventions and constraints? Does it conflict with a prior architectural or style decision? Is it a real defect or a false positive?
4. Assign a verdict:
   - **Implement** — issue is valid and the flagged code still exists
   - **Pushed Back** — suggestion is technically incorrect or conflicts with established decisions; state the concrete reason
   - **Skipped** — flagged code no longer exists in its original form

Do not implement without evaluating first. Do not assign Pushed Back without technical reasoning. Do not assign Skipped without confirming the code is actually gone.

### Step 4 — Implement one comment at a time

For each **Implement** verdict, in order:

1. Make the minimal change that directly addresses the comment. No unrelated cleanup.
2. Run the check command identified in Step 1.
3. Confirm the fix fully and directly resolves the flagged issue — not merely nearby code.
4. If the check fails: diagnose and fix before moving to the next comment; re-run until clean.
5. Search the codebase (`rg '<pattern>'`) for identical or structurally similar instances of the same defect. Fix every instance found. Run the check again — must be clean before moving on.

### Step 5 — Draft replies (do not post yet)

After each verdict, draft the reply text locally:

- **Implemented**: one sentence describing what changed and where, including any similar instances fixed in the codebase scan.
- **Pushed Back**: the concrete technical reason the suggestion was not applied, and what the existing approach does instead.
- **Skipped**: confirm the flagged code no longer exists and note where/when it was removed if known.

Hold all drafts until Step 6.

### Step 6 — Present results and ask for next action

After all comments are processed, emit a summary including the drafted reply for each comment:

```text
Implemented:   N
Pushed Back:   N
Skipped:       N

Drafted replies:
  <comment_id or thread_id> — <one-line preview of reply>
  ...
```

**If there are Implemented verdicts** (code was changed):

```text
What next?
  1. Leave it (no commit, no replies posted)
  2. Commit only (no push, no replies posted)
  3. Commit and push
```

This menu overrides autonomous/goal mode — never commit, push, or post without an explicit choice made here. With no interactive user, default to option 1 (Leave it) — no commit, no push, no replies — and record that in the summary.

- **Leave it** or **Commit only**: apply the commit if chosen; do not push; do not post replies. Inform the user: "Replies not posted — push the branch first so the reviewer can see the changes."
- **Commit and push**: stage only the files changed by the review fixes; write the commit message using the convention confirmed in Step 1; never use `--no-verify`; push to the current branch's remote tracking branch (never directly to `main` or `master`). If the push fails, stop, report the error, and do not post any replies — ask the user to resolve the failure and re-run this step. After the push succeeds, ask: **"Post replies to GitHub now? (y/n)"**

**If there are no Implemented verdicts** (only Pushed Back and Skipped — no code changed): ask `Post replies now? (y/n)` and post immediately on confirmation — no push is needed.

**Posting replies** (using the method chosen in Step 1):

- **Method A:** `gh api repos/{owner}/{repo}/pulls/{pr_number}/comments/{comment_id}/replies -f body="<reply>"`
- **Method B:** `POST https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments/{comment_id}/replies` with body `{"body": "<reply>"}`
- **Method C (GraphQL):** use the thread `id` from the Step 2 query:

  ```graphql
  mutation {
    addPullRequestReviewThreadReply(input: { pullRequestReviewThreadId: "{thread_id}", body: "<reply>" }) {
      comment {
        id
      }
    }
  }
  ```

## Fix strategy

- **One comment → one fix → one validation cycle.** Never batch multiple comments before running the check.
- If the check fails after a fix, resolve that failure before the next comment. Carry-forward failures invalidate subsequent verdicts.
- Structurally identical instances found during the codebase scan are fixed in the same change as the originating comment — completeness, not scope creep.
- Use the **same GitHub API method** for fetching and replying. Never mix methods.
- Commit messages follow the convention confirmed in Step 1. Never commit with `--no-verify`.
- Never commit, push, or post replies without explicit user authorisation granted in Step 6.

## Common mistakes

- **Assuming `gh` is available**: detect the API method in Step 1 and use it consistently.
- **Mixing fetch and reply methods**: GraphQL replies require a `thread_id` only available if GraphQL was used to fetch.
- **Batching comments**: each comment requires its own fix-and-verify cycle.
- **Skipping the codebase scan**: fixing only the flagged line and not the structurally identical instances elsewhere is an incomplete fix.
- **Posting replies before push** (when code changed): the reviewer must be able to see the fix first.
- **Blocking replies when nothing was pushed** (when no code changed): no push is needed — ask directly whether to post replies.
- **Posting replies after a failed push**: stop; never point reviewers at code they cannot see.
- **Treating bot comments as lower priority**: CodeRabbit, Copilot, and other automated reviewers are evaluated on technical merit, not commenter type.
- **Silent skipping**: every comment receives an explicit verdict and a drafted reply.
- **Scope creep**: fixing identical instances of the same defect is in scope; fixing different defects noticed nearby is not.
- **Marking already-resolved code as Implemented**: if the flagged code was fixed in a prior commit, the verdict is Skipped.
