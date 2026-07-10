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
2. Read `_audit-coverage.md` and copy every task in it into your
   task list (in Claude Code: one TaskCreate/TodoWrite entry per task; the
   equivalent task tracker in other agents). This is mandatory — the task
   list is the audit's coverage contract, and no task may be dropped.
3. If the extra instructions name a focus matching a specialist command,
   order that lens's task first and deep-run its command file
   (`<command>.md`) — its findings land under its own auditor key.
   A named focus deepens one lens; it never narrows the checklist — every
   other coverage task still runs.
4. Work the task list in order. For each task: apply the lens (using its
   specialist command as the authority; deep-run `<command>.md`
   when the lens is high-risk), and file findings via findings.py as they
   are confirmed — under the specialist's auditor key when you deep-run it,
   under `--auditor audit` when you apply the lens inline. Close each task in
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
