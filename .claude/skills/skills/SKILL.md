---
name: skills
description: Use when the user wants to run one of the hostile audit skills in this repo, or asks what skills are available.
---

# Skills Launcher

Lists and invokes the public skills in this repository.

## When to Use

- User asks "what skills are available?" or "what can you do?"
- User wants to run a review, audit, or analysis but hasn't named a specific skill
- Use as a quick reference for which skill fits the current situation

## Available Skills

| Skill | Invoke | Use when |
|-------|--------|----------|
| `adversarial-reviewer` | `/adversarial-reviewer` | Hostile bug hunt on specific code; no praise, provable failures only |
| `nitpicker` | `/nitpicker` | Exhaustive whole-repo audit across code, tests, docs, config; can apply fixes |
| `pr-reviewer` | `/pr-reviewer` | Review a PR or diff; outputs copy-paste markdown for GitHub PR comments |
| `arch-detector` | `/arch-detector` | Detect which architectural patterns the codebase uses; writes `docs/audit/arch-profile.md` |
| `arch-auditor` | `/arch-auditor` | Audit for architectural violations against detected or declared patterns |
| `doc-auditor` | `/doc-auditor` | Verify all documentation against the codebase; find stale, missing, or incorrect docs |
| `security-auditor` | `/security-auditor` | Run available security tools, parse output, write consolidated vulnerability and secret findings report |
| `cr-implementer` | `/cr-implementer` | Fetch GitHub PR review comments (unresolved where available via GraphQL), evaluate, implement valid ones with validation, ask user to leave/commit/push |
| `claude-rules-auditor` | `/claude-rules-auditor` | Audit `.claude/rules/` files for quality, check CLAUDE.md for misplaced rules, suggest new rules from project conventions |
| `loophole-hunter` | `/loophole-hunter` | Audit the Claude Code enforcement surface (rules, hooks, settings, permissions, skills) for bypassable or unenforced constraints and close them |
| `hooks-enforcer` | `/hooks-enforcer` | Audit hook *coverage* against the project's evidence base (findings history, git, memory); find recurring failures no hook guards and context-discipline gaps; specify and wire the missing hooks in the harness's correct shape |
| `complexity-hunter` | `/complexity-hunter` | Force the laziest solution that actually works on every coding task; reuse-first ladder before new code; sticky for the session; also audits a diff or whole repo for over-engineering (tagged, ranked findings, applies nothing) |
| `perf-auditor` | `/perf-auditor` | Hostile single-shot performance audit; hunt N+1 queries, O(n²)+ hotspots, sync-blocking calls in async contexts, unbounded caches/queues/retries, missing pagination, loop-invariant work, and chatty per-item I/O — every finding names the code path, growth driver, and concrete fix |
| `test-auditor` | `/test-auditor` | Audit the test suite itself: tests that cannot fail, mocks of the unit under test, severed code paths, flaky patterns, untracked skips, critical-path coverage holes, mutation-blind spots; fixes touch tests only, never production source |
| `dep-auditor` | `/dep-auditor` | Audit dependency health beyond CVEs: unused, phantom, duplicate, heavyweight, unmaintained, license-conflicting, drifted, and misclassified dependencies; cross-references manifest, lockfile, and a full import/usage scan; never installs anything |

## Routing Guide

If the user says… → invoke this skill:

- "review this code / find bugs / tear this apart" → `/adversarial-reviewer`
- "review the whole repo / audit everything / pre-release check" → `/nitpicker`
- "review this PR / review my changes / give me a PR comment" → `/pr-reviewer`
- "what architecture is this / detect patterns" → `/arch-detector`
- "audit the architecture / find violations" → `/arch-auditor`
- "check the docs / find stale docs / verify documentation" → `/doc-auditor`
- "security audit / run security scan / find vulnerabilities / check for secrets / scan dependencies" → `/security-auditor`
- "implement cr comments / fix review feedback / address pr comments" → `/cr-implementer`
- "audit rules / check .claude/rules / rules placement / CLAUDE.md rules" → `/claude-rules-auditor`
- "close loopholes / harden the Claude Code setup / find ways our rules can be bypassed" → `/loophole-hunter`
- "enforce hooks / harden hook coverage / add the hooks we keep needing / make sure context-mode is used" → `/hooks-enforcer`
- "be lazy / simplest solution / YAGNI / do less / stop over-engineering this / find bloat / what can I delete" → `/complexity-hunter`
- "perf audit / find performance issues / why is this slow / will this scale" → `/perf-auditor`
- "audit the tests / find weak tests / do the tests actually test anything" → `/test-auditor`
- "audit dependencies / unused dependencies / prune deps / dependency health" → `/dep-auditor`

## Rules

- Select exactly one skill per request. Do NOT invoke multiple skills simultaneously.
- If the request matches multiple skills, pick the most comprehensive one (e.g., `/nitpicker` covers code, architecture, and docs).
- Never chain skills — the router hands off to one skill and stops.

## If Unclear

Run `make list` (or `uv run scripts/list-skills.py`) to print the current skill list with full descriptions, then ask the user which one fits.
