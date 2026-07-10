---
name: skills
description: Routes audit requests to the right /nitpicker command. Use when the user wants to run one of the hostile audit commands in this repo, or asks what audit commands are available.
---

# Skills Launcher

Everything public in this repository is one skill — `nitpicker` — invoked as
`/nitpicker <command> [extra instructions]`. The authoritative command table
lives in `skills/nitpicker/SKILL.md` (`## Commands`); do not duplicate it
here. `/nitpicker help` prints it.

## Routing Guide

If the user says… → run:

- "review the whole repo / audit everything / pre-release check" → `/nitpicker` (default audit)
- "review this code / find bugs / tear this apart" → `/nitpicker review`
- "review this PR / give me a PR comment" → `/nitpicker pr`
- "implement cr comments / address pr feedback" → `/nitpicker cr`
- "security audit / find vulnerabilities / check for secrets" → `/nitpicker security`
- "audit the tests / do the tests actually test anything" → `/nitpicker tests`
- "check the docs / find stale documentation" → `/nitpicker docs`
- "what architecture is this / detect patterns" → `/nitpicker arch-profile`
- "audit the architecture / find violations" → `/nitpicker arch`
- "perf audit / why is this slow / will this scale" → `/nitpicker perf`
- "audit dependencies / prune deps" → `/nitpicker deps`
- "find silent failures / what errors are we swallowing" → `/nitpicker errors`
- "audit the CI / GitHub Actions security" → `/nitpicker ci`
- "audit the commits / verify conventional commits" → `/nitpicker commits`
- "audit the migrations / is this migration safe" → `/nitpicker migrations`
- "audit observability / can we debug this at 3am" → `/nitpicker observability`
- "does the spec match the code / is this change breaking" → `/nitpicker contract`
- "a11y audit / check WCAG / keyboard accessible" → `/nitpicker a11y`
- "privacy audit / PII audit / GDPR check" → `/nitpicker privacy`
- "config audit / check env vars / config drift" → `/nitpicker config`
- "find leaks / unclosed connections / fd leak" → `/nitpicker leaks`
- "i18n audit / find hardcoded strings" → `/nitpicker i18n`
- "find race conditions / is this thread-safe" → `/nitpicker concurrency`
- "close loopholes / can our rules be bypassed" → `/nitpicker agent-loopholes`
- "enforce hooks / harden hook coverage" → `/nitpicker agent-hooks`
- "audit .claude/rules / rules placement" → `/nitpicker agent-rules`
- "be lazy / YAGNI / find bloat / over-engineering" → `/nitpicker complexity`
- "find unwired code / is everything hooked up / incomplete implementations" → `/nitpicker unwired`
- "plan this / how should we build X / design the implementation" → `/nitpicker plan`
- "can we ship / release gate" → `/nitpicker release-gate`
- "what audit commands are there / list the commands" → `/nitpicker help`

## Rules

- Select exactly one command per request. Never chain commands yourself —
  the nitpicker router owns any command-to-command hand-off.
- If the request matches multiple commands, pick the most comprehensive
  (`/nitpicker` default audit covers code, architecture, and docs).

## If Unclear

Run `make list` (or `uv run scripts/list-skills.py`) to print the skill and
its commands with descriptions, then ask the user which one fits.
