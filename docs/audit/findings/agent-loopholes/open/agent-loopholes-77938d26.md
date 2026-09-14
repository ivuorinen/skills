---
id: agent-loopholes-77938d26
auditor: agent-loopholes
severity: high
category: security
area: scripts/hooks/deny-agents-path-hook.py
status: open
found: 2026-09-13
location: scripts/hooks/deny-agents-path-hook.py:205-213
location_sha: 86d840c8314befe9
---

# Protected-write guard misses writes behind env, nice or command wrappers

## Problem

`_stage_is_mutating` inspects only the first token of a stage, and `_hooklib._wrapper_variants` unwraps a leading wrapper only when a `git` call follows it. A write verb behind `env`, `nice` or `command` is never seen.

## Evidence

```python
def _stage_is_mutating(tokens: list[str]) -> bool:
    verb = PurePosixPath(tokens[0]).name
    if verb in _WRITE_VERBS:
        return True
```

Probes observed in this audit: `rm -f scripts/hooks/ruff-hook.py` → 2; `env rm -f scripts/hooks/ruff-hook.py` → 0. The internal-tooling reviewer observed exit 0 for `nice cp /tmp/x scripts/hooks/ruff-hook.py` and `command rm .claude/settings.json`.

## Impact

CLAUDE.md states this hook blocks a Bash write to `scripts/hooks/` or `.claude/settings.json`. One wrapper word deletes or overwrites a guard or the settings file.

## Fix

In `_wrapper_variants`, emit a variant starting at every non-option, non-assignment token after a known wrapper, not only at `git`, and evaluate `_stage_is_mutating` on each variant. Add wrapper-led write tests. Owner-only surface.
