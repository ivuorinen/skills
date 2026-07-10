---
name: nitpicker
description: 'Hostile audit toolkit: one entry point dispatching specialist commands — adversarial review, security, tests, docs, architecture, performance, dependencies, error handling, CI, commits, migrations, observability, API contracts, a11y, privacy, config, resource leaks, i18n, concurrency, unwired code, PR review and review-comment implementation. Use when auditing or reviewing a repository, PR, or any quality dimension of a codebase — "audit this", "review the whole codebase", "find all problems", "exhaustive review", "/nitpicker <command>", a release gate check, or any specific audit ask (security scan, find race conditions, audit the tests, review the PR, fix the CR comments).'
license: MIT
---

# Nitpicker

Adversarial, exhaustive code review and auditing. Assumes the code is
incorrect until proven otherwise. One skill, many commands.

## Dispatch

The text following the invocation is parsed as:

```text
/nitpicker [command] [extra instructions]
```

- The **first word** names the command. Match it against the tables below —
  canonical names and aliases both resolve. Unknown first word or no text at
  all → run the default `audit` command and treat all text as extra
  instructions.
- **Everything after the command** is extra instructions constraining that
  run (scope, focus, thresholds). The modifiers `inline` and `changed-files`
  may appear anywhere in it (see `commands/_conventions.md`).
- Agents without argument substitution (Copilot, pi) pass the same text
  after the skill invocation; parse it identically.

Execution order, always:

1. Read [commands/_conventions.md](commands/_conventions.md) — it binds
   every command (severity levels, findings store protocol, rules).
2. Read `commands/<command>.md` for the resolved command.
3. Execute it with the extra instructions applied.

Never chain commands on your own; run exactly the one resolved command
(commands may themselves direct you to run another first — follow that).

## Commands

Grouped by category. Aliases in the purpose text (mostly the 1.x skill
names) remain legitimate invocations; the dispatcher resolves them to the
same command file (e.g. `test-auditor` → `commands/tests.md`, `loopholes` →
`commands/agent-loopholes.md`).

### Review and fixing

| Command      | Purpose                                                                                                                 |
| ------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `audit`      | Default. Exhaustive whole-repository review across code, tests, docs, config; optional fixes (alias: `full`)            |
| `review`     | Hostile code review of a diff or file set; assumes bugs exist and hunts them (alias: `adversarial-reviewer`)            |
| `pr`         | Copy-paste-ready markdown review for a GitHub PR (alias: `pr-reviewer`)                                                 |
| `cr`         | Fetch unresolved PR review comments, evaluate, implement valid ones one at a time (alias: `cr-implementer`)             |
| `complexity` | Force the laziest working solution; audit for over-engineering (alias: `complexity-hunter`)                             |
| `unwired`    | Find unwired and incomplete implementations; wire, merge into a wired twin, or remove — each per-finding user-confirmed |

### Planning

| Command | Purpose                                                                                                                                            |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `plan`  | Turn a change request into an implementation plan hardened by the audit lenses; writes a plan doc and stops until the user approves implementation |

### Security and data

| Command    | Purpose                                                                                                 |
| ---------- | ------------------------------------------------------------------------------------------------------- |
| `security` | Run available security scanners, consolidate results into findings (alias: `security-auditor`)          |
| `privacy`  | Personal data stored/transmitted without the control its class requires (alias: `data-privacy-auditor`) |
| `config`   | Undocumented env vars, unsafe prod defaults, config drift, committed secrets (alias: `config-auditor`)  |

### Runtime behavior

| Command       | Purpose                                                                                               |
| ------------- | ----------------------------------------------------------------------------------------------------- |
| `perf`        | Hunt N+1 queries, O(n²)+ hotspots, sync-blocking-in-async, unbounded growth (alias: `perf-auditor`)   |
| `concurrency` | Data races, TOCTOU, deadlock ordering, unsafe publication (alias: `concurrency-auditor`)              |
| `errors`      | Find swallowed exceptions, fail-open defaults, masking fallbacks (alias: `silent-failure-hunter`)     |
| `leaks`       | Acquire-without-guaranteed-release: handles, pools, listeners, tasks (alias: `resource-leak-auditor`) |

### Structure and contracts

| Command        | Purpose                                                                                        |
| -------------- | ---------------------------------------------------------------------------------------------- |
| `arch`         | Audit architectural violations against detected or declared patterns (alias: `arch-auditor`)   |
| `arch-profile` | Detect architectural patterns; writes `docs/audit/arch-profile.md` (alias: `arch-detector`)    |
| `contract`     | Declared API surface vs implementation vs declared semver bump (alias: `api-contract-auditor`) |
| `deps`         | Dependency health beyond CVEs: unused, phantom, duplicate, unmaintained (alias: `dep-auditor`) |
| `migrations`   | Audit DB schema/data migrations for production safety (alias: `migration-auditor`)             |

### Quality surfaces

| Command         | Purpose                                                                                                  |
| --------------- | -------------------------------------------------------------------------------------------------------- |
| `tests`         | Audit the test suite itself: tautological tests, over-mocking, coverage holes (alias: `test-auditor`)    |
| `docs`          | Verify documentation accuracy against the codebase (alias: `doc-auditor`)                                |
| `ci`            | Audit CI/CD pipeline definitions: unpinned actions, injection, token scope (alias: `ci-auditor`)         |
| `commits`       | Audit commit-message discipline against the actual diffs (alias: `commit-auditor`)                       |
| `observability` | Audit logs, metrics, traces, alerts: dark paths, PII, unfireable alerts (alias: `observability-auditor`) |
| `a11y`          | Accessibility audit of the UI layer against WCAG 2.2 AA (alias: `a11y-auditor`)                          |
| `i18n`          | Localization audit against the declared locale scope (alias: `i18n-auditor`)                             |

### Coding-agent enforcement

| Command           | Purpose                                                                                                             |
| ----------------- | ------------------------------------------------------------------------------------------------------------------- |
| `agent-loopholes` | Audit the agent enforcement surface (rules, hooks, settings) for bypasses (aliases: `loopholes`, `loophole-hunter`) |
| `agent-hooks`     | Audit hook coverage against the project's evidence base (aliases: `hooks`, `hooks-enforcer`)                        |
| `agent-rules`     | Audit `.claude/rules/` quality; suggest new rules from conventions (aliases: `rules`, `claude-rules-auditor`)       |

### Meta

| Command        | Purpose                                                             |
| -------------- | ------------------------------------------------------------------- |
| `release-gate` | Fail if open findings at or above a threshold exist (default: High) |
| `help`         | Print this command listing (alias: `list`)                          |

## Internal commands

Dispatched like any command but not part of the public listing — `help`
prints only the `## Commands` section above.

| Command               | Purpose                                                                                                                                           |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `x-findings-migrator` | Migrate legacy 1.x `docs/audit/*-findings.md` files into the findings store; requires explicit per-run user consent, even in autonomous/goal mode |

## The default `audit` command

`commands/audit.md` holds the full flow. In outline: re-validate open
findings, then copy every task from
[commands/_audit-coverage.md](commands/_audit-coverage.md) into the agent's
task list and work through it — one task per quality lens the skill offers
(the specialist commands) plus the base correctness, reliability,
maintainability, and conventions read. Each task ends applied (findings filed
via `findings.py`) or explicitly N/A with a reason; a skipped task is an
accepted blind spot. Offer fixes in severity order, never commit silently.
Naming a focus area deepens that lens but never narrows the checklist.

## release-gate

Read the open findings (`findings.py list --status open`). If any finding at
or above the threshold exists (default High; the extra instructions may name
another), report them and fail the gate. Otherwise report pass. Writes
nothing.

## Bundled tools

| Tool                             | Used by                                         |
| -------------------------------- | ----------------------------------------------- |
| `scripts/findings.py`            | every file-writing command (findings store CLI) |
| `scripts/fetch-pr-comments.py`   | `cr`                                            |
| `scripts/process-sarif.py`       | `security`                                      |
| `scripts/check-rules-anatomy.py` | `agent-rules`, `agent-loopholes`                |

All bundled tools are stdlib-only and run with plain `python3 <path>` — no
uv or package installs required on the host. In Claude Code the skill
directory is `${CLAUDE_SKILL_DIR}`; other agents resolve the path relative
to this file.
