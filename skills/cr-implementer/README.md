# cr-implementer

Fetches unresolved GitHub PR review comments, evaluates each one, implements valid changes one at a time, verifies with tests and linting, and asks what to do before committing or posting replies.

## When to Use

- "Fix the CR comments" / "implement review feedback" / "address PR comments"
- A PR has unresolved reviewer comments that need acting on
- After receiving a code review and wanting to work through each comment systematically

**When NOT to use:**
- Generating a new review of code changes → use [pr-reviewer]
- Finding bugs proactively (not responding to existing comments) → use [adversarial-reviewer]

## What It Reads / Writes

| | |
|---|---|
| **Reads** | GitHub PR review comments (via `gh` CLI, REST API, or GraphQL); codebase files |
| **Writes** | Code changes in the working tree; GitHub PR thread replies (only after explicit user confirmation) |

## How to Invoke

```
/cr-implementer
/cr-implementer <PR number>
```

If no PR number is given, the skill detects the current branch's open PR automatically.

## GitHub API Access

The skill tries three access methods in order and stops at the first that works:

1. **`gh` CLI** — `which gh && gh auth status`
2. **`GITHUB_TOKEN` + HTTP client** — uses `curl`, `ctx_execute` fetch, or any available HTTP client
3. **GraphQL** — `https://api.github.com/graphql` with `Authorization: Bearer $GITHUB_TOKEN`

If none yield an authenticated connection, the skill stops and reports what is needed.

GraphQL access via method 3 provides `isResolved` on review threads; REST (methods 1–2) does not — all comments are processed and the skill assigns a Skipped verdict when the flagged code no longer exists.

## Process

### Step 1 — Setup
- Detect GitHub API access method
- Resolve owner, repo, and PR number
- Identify the project's canonical check command (`make check`, `npm test`, `pytest`, etc.)
- Confirm commit message convention from `git log --oneline -10`

### Step 2 — Fetch All Review Comments
Retrieve all inline review comments. With GraphQL, skip already-resolved threads. With REST, process all and assign Skipped where the flagged code no longer exists.

### Step 3 — Evaluate Each Comment
Assign one verdict per comment:

| Verdict | Meaning |
|---------|---------|
| **Implement** | Comment is valid, actionable, and within scope |
| **Push Back** | Comment is wrong, out of scope, or conflicts with existing behavior |
| **Skip** | Thread already resolved; flagged code no longer exists |

### Step 4 — Implement One at a Time
For each Implement verdict (in order):
1. Apply the minimal change required
2. Run the project's check command
3. If checks fail, fix the failure before moving to the next comment

### Step 5 — Draft Replies
Write a reply for every comment (Implemented, Pushed Back, or Skipped). Do **not** post to GitHub yet.

### Step 6 — Present Results and Ask for Next Action
Show a summary:

```
Implemented:   N
Pushed Back:   N
Skipped:       N

Drafted replies:
  <comment_id> — <one-line preview>
  ...
```

If code was changed, ask:
```
What next?
  1. Leave it (no commit, no replies)
  2. Commit only
  3. Commit and push
```

Replies are posted to GitHub only after a push succeeds and the user confirms. If only Push Back / Skip verdicts exist (no code changed), the skill asks "Post replies now? (y/n)" directly.

## Fix Strategy

- Apply the minimal change that satisfies the comment — do not refactor surrounding code
- If the comment is ambiguous, ask for clarification before implementing
- Use the commit message convention identified in Step 1
- Never use `--no-verify`
- Stage only the files changed by the review fixes

## Output Format

Results are presented inline. No findings file is written. Replies are drafted locally and posted to GitHub PR threads only after the user confirms in Step 6.

## Related Skills

- [pr-reviewer] — generates the type of review comments this skill implements
- [adversarial-reviewer] — proactive hostile code review not tied to existing PR comments

---

[skill-source]: SKILL.md
[pr-reviewer]: ../pr-reviewer/README.md
[adversarial-reviewer]: ../adversarial-reviewer/README.md
