---
id: agent-loopholes-bbe241dd
auditor: agent-loopholes
severity: medium
category: security
area: .claude/settings.json
status: open
found: 2026-09-13
location: scripts/hooks/deny-agents-path-hook.py:86-88
location_sha: 735fdeb0657d9b63
---

# .claude/settings.local.json is unprotected, and one redirect there can disable every hook

## Problem

Neither `permissions.deny` nor `PROTECTED_WRITE` covers `.claude/settings.local.json`, which Claude Code merges over the project settings and where `disableAllHooks` takes effect.

## Evidence

```python
PROTECTED_WRITE = ("scripts/hooks", ".claude/settings.json")
```

The deny list (settings.json:3-11) names `.claude/agents/**`, `scripts/hooks/**` and `.claude/settings.json` only. Probe observed in this audit: `echo {} > .claude/settings.local.json` → exit 0.

## Impact

A single Bash write turns off the entire enforcement surface, contradicting CLAUDE.md's statement that the surface cannot be edited around through `sed -i` or a redirect.

## Fix

Add `Edit(./.claude/settings.local.json)` to `permissions.deny`, add the path to `PROTECTED_WRITE` and to `post-bash-revalidate.py`'s GOVERNED set, and pin both in `tests/test_settings.py`. Owner-only surface.
