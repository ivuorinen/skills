---
id: perf-74e03db5
auditor: perf
severity: medium
category: performance
area: scripts/hooks/post-bash-revalidate.py
status: open
found: 2026-09-13
location: scripts/hooks/post-bash-revalidate.py:82-97
location_sha: 7fc025f8d73e2c11
---

# post-bash-revalidate runs every gate after each Bash call on a clean tree

## Problem

The hook asks `git status --porcelain --ignored` and runs all gates when any GOVERNED marker appears anywhere in its output. Ignored entries that exist on every clean checkout contain those markers, so the gates run after every Bash call.

## Evidence

```python
["git", "status", "--porcelain", "--ignored"],
...
if not any(marker in status.stdout for marker in GOVERNED):
    return
```

On this repository's clean tree the output includes `!! docs/audit/findings/.lock`, `!! scripts/__pycache__/`, `!! scripts/hooks/__pycache__/` and `!! skills/nitpicker/scripts/__pycache__/`, each containing a GOVERNED substring. The runtime reviewer measured 1.21 s per Bash call with those entries present and 0.08 s without. One gate is `findings.py index`, which takes the store lock and rewrites INDEX.md each time. The docstring (lines 11-12) says a clean tree costs one `git status`, and line 7 says five Write|Edit validators where `settings.json` registers seven.

## Impact

About fifteen times the latency on every Bash call, multiplied by parallel subagents, plus a store-lock acquisition and index rewrite per call.

## Fix

Evaluate GOVERNED per porcelain entry; for `!!` entries accept only paths under `docs/audit/findings/` excluding `.lock` and `*.tmp`, and never match `__pycache__/`. Correct the docstring. Owner-only surface.
