---
id: agent-loopholes-c3a684c9
auditor: agent-loopholes
severity: low
category: reliability
area: scripts/hooks/deny-unsafe-git-hook.py
status: open
found: 2026-09-13
location: scripts/hooks/deny-unsafe-git-hook.py:53-89
location_sha: 7a72e4fd7982d0bc
---

# Stage-everything check compares pathspec spellings instead of what they reach

## Problem

`_ADD_ALL` and `_norm_pathspec` fold only `.`, `./`-prefixed and exact `:/` spellings. Any other pathspec that reaches the whole tree passes the guard.

## Evidence

```python
_ADD_ALL = frozenset({"-A", "--all", "--no-ignore-removal", ".", ":/"})
...
if arg.startswith(":/"):
    return ":/" if not arg[2:].strip("./") else arg
```

`:/*` keeps its `*` and is returned unchanged, so it is not in `_ADD_ALL`. The enforcement reviewer observed exit 0 for `git add ':/*'`, `git add '*'`, `git add <absolute repo root>`, `git add "$PWD"`, `git add ../skills` and `git add ':(top)'`, while `git add .` and `git add :/` are denied.

## Impact

The ban on staging everything is avoidable with ordinary spellings. `commit-gate-integrity.md` keeps CI as the binding gate, hence Low.

## Fix

Resolve each operand against the repository root (absolute paths, `..`, `$PWD`, `:(top)` and `:/` magic with any suffix, a lone `*`) and deny when it resolves to the root. Owner-only surface.
