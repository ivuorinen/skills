---
id: agent-hooks-da747c0c
auditor: agent-hooks
severity: medium
category: reliability
area: scripts/hooks
status: open
found: 2026-09-13
location: .claude/rules/use-context-mode.md:1-8
location_sha: 9f2ed157d51819b7
---

# No hook enforces a guarded cd in mutating context-mode shell scripts

## Problem

Shell code sent to `ctx_execute` runs against the real filesystem and continues after a failed `cd`. The project's memory mandates `cd <dir> || exit 1` before any mutation in such scripts, and no hook checks it.

## Evidence

Project memory, incident of 2026-09-10: a probe script whose `cd` failed ran `git init`, `git config user.email` and `git add -A` in the real repository. The rule file directs agents to `ctx_execute` for shell work; `.claude/settings.json` registers no hook for that tool.

## Impact

The same class of accidental repository mutation can recur on any probe script whose `cd` fails.

## Fix

Add a PreToolUse hook on `ctx_execute` with `language` `shell` that denies when a `cd` line is not followed by `||` or `&&` and a later line mutates state (`git`, `rm`, `mv`, `>`). It shares the matcher change in the Bash-only-guards finding.
