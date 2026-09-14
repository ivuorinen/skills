---
id: agent-loopholes-152e6d90
auditor: agent-loopholes
severity: medium
category: reliability
area: scripts/hooks/ask-destructive-restore-hook.py
status: open
found: 2026-09-13
location: scripts/hooks/ask-destructive-restore-hook.py:65-89
location_sha: 6e0200a4d21d6b5e
---

# Destructive-restore guard ignores git checkout of a path without -- and pathspec magic

## Problem

`_targets` counts `git checkout` only when `--` is present, but `git checkout <path>` restores that path from the index just the same. `_covers` matches only exact paths and directory prefixes, so `:/`, `:(top)` and glob pathspecs never match a dirty entry.

## Evidence

```python
if subcommand == "checkout" and "--" in args:
```

```python
return t in ("", ".") or entry == t or entry.startswith(f"{t}/")
```

The internal-tooling reviewer, in a temp repository: `git checkout f.txt` exited 0 and replaced the unstaged content with the committed version while `_targets` returned `None`; `_covers(":/", "src/a.py")` and `_covers("*.py", "a.py")` both returned `False`.

## Impact

The exact data-loss class `snapshot-before-mutating.md` documents passes the guard silently.

## Fix

For `checkout` without `--`, treat any operand that `git rev-parse --verify --quiet <op>^{commit}` rejects as a path; treat `:/`, `:(top)` and glob pathspecs as covering every dirty entry. Keep branch switches silent, which `tests/test_hooks.py` pins. Owner-only surface.
