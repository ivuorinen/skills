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

| Command | Purpose |
| --- | --- |
| `audit` | Default. Exhaustive whole-repository review across code, tests, docs, config; optional fixes (alias: `full`) |
| `review` | Hostile code review of a diff or file set; assumes bugs exist and hunts them (alias: `adversarial-reviewer`) |
| `pr` | Copy-paste-ready markdown review for a GitHub PR (alias: `pr-reviewer`) |
| `cr` | Fetch unresolved PR review comments, evaluate, implement valid ones one at a time (alias: `cr-implementer`) |
| `complexity` | Force the laziest working solution; audit for over-engineering (alias: `complexity-hunter`) |
| `unwired` | Find unwired and incomplete implementations; wire, merge into a wired twin, or remove — each per-finding user-confirmed |

### Planning

| Command | Purpose |
| --- | --- |
| `plan` | Turn a change request into an implementation plan hardened by the audit lenses; writes a plan doc and stops until the user approves implementation |
| `execute-plan` | Execute an approved plan task by task, verifying each task as it lands, stopping when blocked instead of guessing; the sequel to `plan` (adapted from obra/superpowers) |

### Learning

| Command | Purpose |
| --- | --- |
| `teach` | Teach a skill or concept across sessions; builds a persistent teaching workspace under `docs/lessons/` (mission, resources, lessons, learning records). Writes lessons, not findings (adapted from mattpocock/skills) |

### Security and data

| Command | Purpose |
| --- | --- |
| `security` | Run available security scanners, consolidate results into findings (alias: `security-auditor`) |
| `privacy` | Personal data stored/transmitted without the control its class requires (alias: `data-privacy-auditor`) |
| `config` | Undocumented env vars, unsafe prod defaults, config drift, committed secrets (alias: `config-auditor`) |
| `iac` | Infrastructure-as-code misconfig: root containers, open ingress, public stores, overbroad IAM |
| `prompt-safety` | LLM-integration safety: prompt injection, model-output-to-sink, excessive tool agency, secrets in context |

### Runtime behavior

| Command | Purpose |
| --- | --- |
| `perf` | Hunt N+1 queries, O(n²)+ hotspots, sync-blocking-in-async, unbounded growth (alias: `perf-auditor`) |
| `concurrency` | Data races, TOCTOU, deadlock ordering, unsafe publication (alias: `concurrency-auditor`) |
| `errors` | Find swallowed exceptions, fail-open defaults, masking fallbacks (alias: `silent-failure-hunter`) |
| `leaks` | Acquire-without-guaranteed-release: handles, pools, listeners, tasks (alias: `resource-leak-auditor`) |

### Structure and contracts

| Command | Purpose |
| --- | --- |
| `arch` | Audit architectural violations against detected or declared patterns (alias: `arch-auditor`) |
| `arch-profile` | Detect architectural patterns; writes `docs/audit/arch-profile.md` (alias: `arch-detector`) |
| `contract` | Declared API surface vs implementation vs declared semver bump (alias: `api-contract-auditor`) |
| `deps` | Dependency health beyond CVEs: unused, phantom, duplicate, unmaintained (alias: `dep-auditor`) |
| `license` | License compliance: project license, dep compatibility, copyleft contamination, attribution |
| `migrations` | Audit DB schema/data migrations for production safety (alias: `migration-auditor`) |

### Quality surfaces

| Command | Purpose |
| --- | --- |
| `tests` | Audit the test suite itself: tautological tests, over-mocking, coverage holes (alias: `test-auditor`) |
| `types` | Static-typing soundness: suppressed errors, any-escapes, unsound casts, lax strictness |
| `docs` | Verify documentation accuracy against the codebase (alias: `doc-auditor`) |
| `contributing` | Audit `CONTRIBUTING.md` against the repo's real tooling; offer to scaffold one from actual conventions when absent |
| `ci` | Audit CI/CD pipeline definitions: unpinned actions, injection, token scope (alias: `ci-auditor`) |
| `commits` | Audit commit-message discipline against the actual diffs (alias: `commit-auditor`) |
| `observability` | Audit logs, metrics, traces, alerts: dark paths, PII, unfireable alerts (alias: `observability-auditor`) |
| `a11y` | Accessibility audit of the UI layer against WCAG 2.2 AA (alias: `a11y-auditor`) |
| `i18n` | Localization audit against the declared locale scope (alias: `i18n-auditor`) |

### Coding-agent enforcement

| Command | Purpose |
| --- | --- |
| `agent-loopholes` | Audit the agent enforcement surface (rules, hooks, settings) for bypasses (aliases: `loopholes`, `loophole-hunter`) |
| `agent-hooks` | Audit hook coverage against the project's evidence base (aliases: `hooks`, `hooks-enforcer`) |
| `agent-rules` | Audit `.claude/rules/` quality; suggest new rules from conventions (aliases: `rules`, `claude-rules-auditor`) |

### Meta

| Command | Purpose |
| --- | --- |
| `baseline` | Snapshot open findings as accepted; gate fails only on new ones |
| `release-gate` | Fail if open findings at or above a threshold exist (default: High) |
| `help` | Print this command listing (alias: `list`) |

## Internal commands

Dispatched like any command but not part of the public listing — `help`
prints only the `## Commands` section above.

| Command | Purpose |
| --- | --- |
| `x-findings-migrator` | Migrate legacy 1.x `docs/audit/*-findings.md` files into the findings store; requires explicit per-run user consent, even in autonomous/goal mode |

Each command's full behavior lives in its `commands/<command>.md`, loaded per
the execution order above — `audit` (the default), `release-gate`, and
`baseline` included. This router only dispatches; it never restates a command's
flow.

## Bundled tools

| Tool | Used by |
| --- | --- |
| `scripts/findings.py` | every file-writing command (findings store CLI) |
| `scripts/fetch-pr-comments.py` | `cr` |
| `scripts/process-sarif.py` | `security` |
| `scripts/check-rules-anatomy.py` | `agent-rules`, `agent-loopholes` |
| `scripts/mcp_server.py` | the bundled stdio MCP server (see below) |
| `scripts/skill_catalog.py` | `mcp_server.py` — skill/command enumeration |

All bundled tools are stdlib-only and run with plain `python3 <path>` — no
uv or package installs required on the host. In Claude Code the skill
directory is `${CLAUDE_SKILL_DIR}`; other agents resolve the path relative
to this file.

## MCP server

Installing this plugin registers a stdio MCP server (`nitpicker`) from the
`mcpServers` block in `.claude-plugin/plugin.json` (plugin scope, resolved via
`${CLAUDE_PLUGIN_ROOT}`); this repo additionally registers the same server for
project scope from `.mcp.json`. It is stdlib-only Python 3.11+
(`scripts/mcp_server.py`), starts automatically, and exposes 10 tools:

Every tool name carries the `np_` prefix, so a nitpicker tool stays
recognizable wherever a name appears without its server qualifier.

| Scope | Tools |
| --- | --- |
| Plugin skills (introspection) | `np_list_skills`, `np_read_skill`, `np_read_command`, `np_list_commands` |
| Findings — read | `np_list_findings`, `np_show_finding`, `np_findings_index`, `np_validate_store` |
| Findings — mutate | `np_new_finding`, `np_resolve_finding` |

Skill tools read the plugin's own bundled skills. Findings tools act on the
audited project's store — pass `project_dir`, or the server falls back to
`CLAUDE_PROJECT_DIR` then the working directory's repo root. `project_dir` may
only narrow that root, never escape it.

When these tools are available, commands prefer them over `scripts/findings.py`
for every operation both cover; `_conventions.md` holds the mapping and the
CLI-only exceptions. The preference is never a dependency — the server is
Claude-native, so in Copilot, pi, or CI the CLI is the only interface and is
fully sufficient.

The mutate tools run **without** the interactive consent prompts of the
`/nitpicker` command flow: git is the safety net — every change is a
reviewable, revertible working-tree edit and nothing is pushed. The server is
Claude-native and not portable to Copilot/pi.
