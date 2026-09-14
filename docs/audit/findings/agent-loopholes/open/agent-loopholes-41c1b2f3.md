---
id: agent-loopholes-41c1b2f3
auditor: agent-loopholes
severity: high
category: security
area: .claude/settings.json
status: open
found: 2026-09-13
location: .claude/settings.json:98-152
location_sha: 8087c439f9288d3e
---

# Every shell guard matches the Bash tool only, while the rules route shell work through context-mode

## Problem

Each PreToolUse guard and the post-Bash revalidation hook is registered with `"matcher": "Bash"`. `.claude/rules/use-context-mode.md` requires shell commands to run through the context-mode `ctx_execute` and `ctx_batch_execute` tools, whose calls never reach these hooks.

## Evidence

`.claude/settings.json` lines 79, 100, 109, 127, 136 and 145: `"matcher": "Bash"`; no matcher names a context-mode tool. Project memory records the incident of 2026-09-10: a failed `cd` inside `ctx_execute` let `git init`, `git config` and `git add -A` run in the real repository, staging 61 paths, where the same `git add -A` sent through Bash is denied. This audit itself ran commits and store writes through `ctx_execute` with no guard involved.

## Impact

The pre-commit bypass guard, protected-branch push, agents-path, protected-write, ctx-ok and destructive-restore guards, and post-Bash revalidation are all bypassed by the tool the repository's own rules tell agents to use.

## Fix

Extend each guard's matcher to `Bash|mcp__plugin_context-mode_context-mode__ctx_execute|mcp__plugin_context-mode_context-mode__ctx_batch_execute|mcp__plugin_context-mode_context-mode__ctx_execute_file`; teach `_hooklib` to read the command text from `tool_input.code` when `language` is `shell` and from each `tool_input.commands[].command`; for other languages, deny when the code names `git` or a protected path. Owner-only surface.
