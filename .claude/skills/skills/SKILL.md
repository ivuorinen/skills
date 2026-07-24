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
- "audit the types / check type safety / find the anys / are the type ignores real" → `/nitpicker types`
- "check the docs / find stale documentation" → `/nitpicker docs`
- "audit CONTRIBUTING / is our contributor guide accurate / we have no CONTRIBUTING.md" → `/nitpicker contributing`
- "what architecture is this / detect patterns" → `/nitpicker arch-profile`
- "audit the architecture / find violations" → `/nitpicker arch`
- "perf audit / why is this slow / will this scale" → `/nitpicker perf`
- "audit dependencies / prune deps" → `/nitpicker deps`
- "audit the licenses / license compatibility / are we GPL-contaminated / check attribution" → `/nitpicker license`
- "find silent failures / what errors are we swallowing" → `/nitpicker errors`
- "audit the CI / GitHub Actions security" → `/nitpicker ci`
- "audit the commits / verify conventional commits" → `/nitpicker commits`
- "audit the migrations / is this migration safe" → `/nitpicker migrations`
- "audit observability / can we debug this at 3am" → `/nitpicker observability`
- "does the spec match the code / is this change breaking" → `/nitpicker contract`
- "a11y audit / check WCAG / keyboard accessible" → `/nitpicker a11y`
- "privacy audit / PII audit / GDPR check" → `/nitpicker privacy`
- "config audit / check env vars / config drift" → `/nitpicker config`
- "audit the infra / Dockerfile / Terraform / k8s security / IaC misconfig" → `/nitpicker iac`
- "audit prompt safety / check for prompt injection / is this agent safe / LLM integration" → `/nitpicker prompt-safety`
- "find leaks / unclosed connections / fd leak" → `/nitpicker leaks`
- "i18n audit / find hardcoded strings" → `/nitpicker i18n`
- "find race conditions / is this thread-safe" → `/nitpicker concurrency`
- "is this safe to retry / will this double-charge / audit reliability / retry idempotency timeouts" → `/nitpicker reliability`
- "audit the cache / is this cache safe / why is this data stale / will this cache leak across tenants" → `/nitpicker cache`
- "close loopholes / can our rules be bypassed" → `/nitpicker agent-loopholes`
- "enforce hooks / harden hook coverage" → `/nitpicker agent-hooks`
- "audit .claude/rules / rules placement" → `/nitpicker agent-rules`
- "be lazy / YAGNI / find bloat / over-engineering" → `/nitpicker complexity`
- "find unwired code / is everything hooked up / incomplete implementations" → `/nitpicker unwired`
- "find dead code / what can we delete / unused exports / is this still used" → `/nitpicker dead-code`
- "plan this / how should we build X / design the implementation" → `/nitpicker plan`
- "execute the plan / implement the approved plan / build what we planned" → `/nitpicker execute-plan`
- "teach me X / help me learn X / explain X so it sticks / next lesson" → `/nitpicker teach`
- "can we ship / release gate" → `/nitpicker release-gate`
- "baseline the findings / accept existing debt / only fail on new findings" → `/nitpicker baseline`
- "what audit commands are there / list the commands" → `/nitpicker help`

## Rules

- Select exactly one command per request. Never chain commands yourself —
  the nitpicker router owns any command-to-command hand-off.
- If the request matches multiple commands, pick the most comprehensive
  (`/nitpicker` default audit covers code, architecture, and docs).

## If Unclear

Run `make list` (or `uv run scripts/list-skills.py`) to print the skill and
its commands with descriptions, then ask the user which one fits.
