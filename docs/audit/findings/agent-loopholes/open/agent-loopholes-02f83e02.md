---
id: agent-loopholes-02f83e02
auditor: agent-loopholes
severity: high
category: security
area: scripts/hooks/deny-agents-path-hook.py
status: open
found: 2026-09-13
location: scripts/hooks/deny-agents-path-hook.py:366-371
location_sha: 300d8bfae5dc4d51
---

# Agents-path and protected-write guard fails open when it raises

## Problem

`hit.resolve()` runs without a guard and the entry point calls `main()` with no exception handler, so any exception ends the hook with exit 1. Claude Code treats exit codes other than 0 and 2 as non-blocking, and the command proceeds.

## Evidence

```python
for hit in _shell_glob(base, rel):
    resolved = hit.resolve()
```

```python
if __name__ == "__main__":
    main()
```

Probe observed in this audit: in a scratch directory holding a two-link symlink loop, the command `cd <loop dir> && ls * ; sed -i s/a/b/ scripts/hooks/_hooklib.py` made the hook exit 1 with `RuntimeError: Symlink loop`; the same `sed -i` alone exits 2.

## Impact

`ln` is not guarded, so creating a loop and adding a glob before the payload disables both the agents-tree denial and the enforcement-surface write denial.

## Fix

Wrap `main()` so any exception prints a DENIED line naming the error to stderr and exits 2, and catch `(OSError, RuntimeError)` around `hit.resolve()` treating the entry as a match. Give every PreToolUse guard the same fail-closed wrapper. Owner-only surface.
