---
id: audit-1e48d360
auditor: audit
severity: low
category: maintainability
area: scripts/hooks
status: open
found: 2026-09-13
location: scripts/hooks/validate-rules-hook.py:26-35
location_sha: 335787738079bc70
---

# Hooks disagree on whether validator paths come from __file__ or the environment

## Problem

`validate-rules-hook.py` builds validator paths from `__file__` to close a CodeQL command-line-injection report; the other validator hooks still build them from `REPO_ROOT`, which comes from `CLAUDE_PROJECT_DIR`.

## Evidence

```python
_SHIPPED_ROOT = Path(__file__).resolve().parent.parent.parent     # validate-rules-hook.py:35
```

`validate-skill-hook.py` (lines 45, 52), `validate-evals-hook.py`, `check-version-sync-hook.py` and `validate-audit-findings-hook.py:25` use `REPO_ROOT` for the scripts they execute.

## Impact

With `CLAUDE_PROJECT_DIR` pointing at another checkout that carries `scripts/hooks/_hooklib.py`, four hooks run that checkout's validators while the rules hook runs this one's.

## Fix

Move `_SHIPPED_ROOT` into `_hooklib` and derive every executed validator path from it, keeping `REPO_ROOT` as the subprocess `cwd`. This is owner-only enforcement surface.
