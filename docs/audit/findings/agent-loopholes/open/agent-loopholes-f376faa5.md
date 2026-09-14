---
id: agent-loopholes-f376faa5
auditor: agent-loopholes
severity: medium
category: security
area: scripts/hooks/deny-unsafe-git-hook.py
status: open
found: 2026-09-13
location: scripts/hooks/deny-unsafe-git-hook.py:223-237
location_sha: 97611e304f4dce8d
---

# Git guard misses hook-disabling settings written outside the command and the separate --config-env form

## Problem

The guard inspects hook-disabling configuration only when it is typed into the same command, and for `--config-env` only in its `=` form: the separate-argument form is consumed as a value option without being recorded.

## Evidence

```python
if opt in _VALUE_OPTS:
    if opt == "-c" and i + 1 < len(tokens) and "=" in tokens[i + 1]:
        ...
    i += 2
```

Probes observed in this audit: `HP=/dev/null git --config-env core.hooksPath=HP commit -m x` → 0; `git config core.hooksPath /dev/null` → 0. The enforcement reviewer also observed exit 0 for `git config alias.ci 'commit --no-verify'` followed by `git ci -m x`, for a `SKIP=<hook ids>` prefix on `git commit`, and for `pre-commit uninstall && git commit`. CLAUDE.md describes `--config-env` and alias bodies resolving to a denied call as closed.

## Impact

The local pre-commit and commit-msg gates can be switched off. CI's `Validate` job still binds, which keeps this at Medium.

## Fix

Record the separate `--config-env <key>=<var>` form exactly like `-c`, resolving the variable through the environment; deny `git config` writes to `core.hooksPath` and `alias.*`; resolve persistent aliases with `git config --get alias.<sub>` before judging; deny `SKIP=` and `PRE_COMMIT_` prefixes on `git commit` and `pre-commit uninstall`. Correct the CLAUDE.md claim. Owner-only surface.
