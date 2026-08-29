# /nitpicker audit — Exhaustive Whole-Repository Review

Adversarial, exhaustive review of the entire repository across code, tests,
documentation, and configuration, with optional fixing in the same run.
Assumes the code is incorrect until proven otherwise. This is the default
command when the invocation names no other.

## When to use

Full repository audit before a release; PR review when every defect must be
found, not just obvious ones; "review the whole codebase", "audit this",
"find all problems", "tear this apart", "exhaustive review". For a single
quality dimension, the matching specialist command is cheaper and deeper —
see the command table in SKILL.md.

## Review scope

Analyze all of:

- Code correctness and logic
- Security and trust boundaries
- Reliability and operational safety
- Maintainability and architecture
- Performance characteristics
- Test coverage and effectiveness
- Documentation accuracy and completeness
- Convention adherence (repo, language, framework)

## Behavior

```text
1. Re-validate open findings per `_conventions.md` (`--auditor audit`).
2. Load `_audit-coverage.md` (`np_read_reference` with
   `name: "audit-coverage"`, else read the file) and copy every task in it into
   your task list, per the task-list rule in `_conventions.md` — which also
   gives the form to use when the session exposes no tracker. This is
   mandatory: the list is the audit's coverage contract, and no task may be
   dropped **silently**. Dropping one on request is step 3's business.
3. Read the extra instructions as one of two things, and say which before
   starting:
   - A **focus** names a lens (a specialist command). Order that lens's task
     first and deep-run its command file (`np_read_command` with
     `command: <command>`, else read `<command>.md`) — its findings land under
     its own auditor key. A focus deepens one lens and never narrows the
     checklist; every other coverage task still runs.
   - A **scope** bounds the subject matter or the file set ("only the MCP
     tools", "just the docs", `changed-files`). A scope narrows the checklist,
     and that is legitimate — an audit the user scoped is the audit they asked
     for. What is not legitimate is narrowing invisibly: every task the scope
     excludes is closed **out of scope** (`_audit-coverage.md` state 4) naming
     what the scope excluded, and each one appears in the run summary. The user
     then sees what was not looked at, rather than reading a narrowed run as an
     exhaustive one.
   When the instructions read as either, ask instead of guessing — the two
   produce very different runs, and the wrong pick is only visible afterwards.
4. Work the task list in order. For each task: apply the lens (using its
   specialist command as the authority; deep-run it via `np_read_command`,
   else `<command>.md`, when the lens is high-risk), and file findings as
   they are confirmed —
   under the specialist's auditor key when you deep-run it, under the `audit`
   auditor key when you apply the lens inline. Close each task in
   exactly one of the states `_audit-coverage.md` defines (findings filed,
   clean, or N/A with a reason). Do not close the audit while any task is open.
5. Run the findings-store protocol in `_conventions.md` (index refresh,
   summary, apply-fixes and commit prompts). The run summary lists every
   coverage task's outcome. If fixing: severity order (Critical first), then
   re-review the changed files to confirm the open count decreases, and
   resolve fixed findings in the store.
```

## Fix strategy

- Prefer minimal diffs and idiomatic language/framework patterns.
- Replace broken logic with correct implementations; never paper over it.
- Add or update tests for each fix; update docs when behavior changes.
- Remove dead or harmful code when necessary.
- Every skipped finding stays open in the store with the reason in its file.
- Fail loudly if a Critical issue cannot be safely resolved.
