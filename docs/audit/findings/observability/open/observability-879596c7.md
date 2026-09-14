---
id: observability-879596c7
auditor: observability
severity: low
category: reliability
area: scripts/hooks
status: open
found: 2026-09-13
location: scripts/hooks/validate-skill-hook.py:57-58
location_sha: 9b9899f36026acc9
---

# Validator hooks skip silently when their validator cannot run

## Problem

When a hook's validator is missing, hangs past the timeout or cannot start, the hook returns with exit 0 and prints nothing, so the agent gets the same signal as a passing validation.

## Evidence

```python
except (OSError, subprocess.SubprocessError):
    return  # uv absent or the validator hung — CI remains the gate
```

The same silent return is at `check-version-sync-hook.py:62-63`, `validate-evals-hook.py:78`, `validate-audit-findings-hook.py:86-87, 106-107, 126-127`, `stop-reminder.py:71-72`, `validate-json-hook.py:46` and `post-bash-revalidate.py:90-93`. `post-bash-revalidate.py:104` does print `gate skipped` for a missing gate script, so the silent paths are inconsistent with the file's own practice.

## Impact

An agent keeps building on an invalid SKILL.md, eval set or findings store until CI rejects it, with no in-session hint that validation never ran.

## Fix

Print one stderr line naming the hook, the reason and the command to run by hand (`validator did not run: <reason>; run make validate`) on every such path. Owner-only surface.
