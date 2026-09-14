---
id: agent-loopholes-c7170a25
auditor: agent-loopholes
severity: low
category: reliability
area: scripts/hooks/deny-agents-path-hook.py
status: open
found: 2026-09-14
location: scripts/hooks/deny-agents-path-hook.py:52-54
location_sha: 22052698f1212945
---

# Agents-path guard denies every Bash command naming a Claude Code isolation worktree

## Problem

The indirect-reference pattern that catches variable-built spellings of the protected agents tree also matches the directory names Claude Code gives isolation worktrees, `.claude/worktrees/agent-<id>`. Any Bash command naming such a worktree is denied as if it referenced `.claude/agents`, although it does not.

## Evidence

```python
_DENIED_RE = re.compile(r"\.claude/agents\b")
_CLAUDE_RE = re.compile(r"\.claude\b")
_AGENTS_INDIRECT_RE = re.compile(r"[=/$]agents?\b|\.claude/a")
```

`/agent-` matches `[=/$]agents?\b` (the hyphen is a word boundary) and `.claude` matches `_CLAUDE_RE`. Probes piped to the hook during this fix pass:

- `git -C .claude/worktrees/agent-a79572a0c34809bc4 diff --cached` → exit 2, `DENIED  Bash command references .claude/agents`
- `ls .claude/worktrees/my-feature` → exit 0
- `git -C .claude/agents status` → exit 2 (control)
The same denial blocked integrating a fix group's worktree diff from the main session.

## Impact

Every workflow built on Claude Code's `isolation: "worktree"` subagents breaks at the point the parent session reads or applies a worktree by path, and the agent is pushed toward alternate spellings of a path the guard exists to police.

## Fix

Exempt the exact `.claude/worktrees/<name>` directory shape before the indirect match (for example strip `\.claude/worktrees/[^/\s]+` segments from the canonicalised command before applying `_AGENTS_INDIRECT_RE`), keeping `.claude/agents`, `.claude/a*`, `.claude/a[g]ents` and variable-built spellings denied. Add both the worktree probe (allowed) and those controls (denied) to `tests/test_hooks.py`. Owner-only surface.
