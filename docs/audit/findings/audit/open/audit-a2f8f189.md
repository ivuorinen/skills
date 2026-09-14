---
id: audit-a2f8f189
auditor: audit
severity: low
category: maintainability
area: scripts/hooks/validate-audit-findings-hook.py
status: open
found: 2026-09-13
location: scripts/hooks/validate-audit-findings-hook.py:28-34
location_sha: 435da0dd3abba5a4
---

# Findings hook's store-root helper is a second copy of DEFAULT_ROOT

## Problem

The helper's docstring says it is the one definition keeping the hook and `findings.py` in agreement, but it returns its own literal path; `findings.py` defines `DEFAULT_ROOT` separately.

## Evidence

```python
def store_root(repo_root: Path) -> Path:
    """...One definition, so this hook and findings.py cannot disagree..."""
    return repo_root / "docs" / "audit" / "findings"
```

`findings.py:52`: `DEFAULT_ROOT = Path("docs/audit/findings")`.

## Impact

Changing `DEFAULT_ROOT` silently stops the hook from validating store edits.

## Fix

Path-load `findings` and return `repo_root / findings.DEFAULT_ROOT`. This file is owner-only enforcement surface.
