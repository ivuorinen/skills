---
id: skill-safety-59f9427a
auditor: skill-safety
severity: medium
category: security
area: .claude/skills/graphify/SKILL.md
status: open
found: 2026-09-13
location: .claude/skills/graphify/SKILL.md:84-95
location_sha: 69a5b4e5679bd9b4
---

# Vendored graphify skill installs the latest graphifyy from PyPI during setup

## Problem

The vendored skill's setup, which it tells the agent to follow in order without skipping, installs `graphifyy` unpinned with `--upgrade`, and falls back to `pip install --break-system-packages`. The repository pins graphify to a specific version through `.graphify_version`.

## Evidence

```bash
uv tool install --upgrade graphifyy -q 2>&1 | tail -3
...
"$PYTHON" -m pip install graphifyy -q 2>/dev/null \
  || "$PYTHON" -m pip install graphifyy -q --break-system-packages 2>&1 | tail -3
```

When `import graphify` fails with the resolved interpreter, the agent installs whatever version PyPI serves and runs its code; the settings.json pin guard then denies every Bash, Read and Glob call.

## Impact

Unreviewed package code runs with the session user's credentials, and the session is left unusable behind the pin guard.

## Fix

Patch the vendored copy to install `graphifyy==` the version in `.graphify_version`, without `--upgrade` or `--break-system-packages`, or replace the step with an instruction to stop and ask the owner. Record the deviation from upstream in `NOTICE`.
