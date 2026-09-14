---
id: types-44e0e1c7
auditor: types
severity: low
category: conventions
area: scripts/hooks
status: open
found: 2026-09-13
location: scripts/hooks/post-bash-revalidate.py:24
location_sha: 51e28e6eaab49520
---

# Mypy-style type: ignore comments blanket-suppress pyright and most are unnecessary

## Problem

Pyright runs the type gate (`make typecheck`), and it does not honour the bracketed mypy error code in `# type: ignore[...]`: the comment suppresses every diagnostic on its line. Most of these comments no longer suppress anything real.

## Evidence

```python
from _hooklib import HOOK_TIMEOUT, repo_root  # type: ignore[import-not-found]
```

The same comment sits on the `_hooklib` import of every hook and on `scripts/validate-skill.py:19` and `scripts/list-skills.py:12`; `findings.py:421` has `# type: ignore[assignment]`. With `reportUnnecessaryTypeIgnoreComment` enabled on a scratch config, pyright flagged 16 of them as unnecessary. Renaming `_hooklib.repo_root` on a copy produced errors in the hooks with multi-line imports but none in the two with single-line imports.

## Impact

The type gate is blind to real errors on those lines, such as a renamed helper the hooks import.

## Fix

Delete the unnecessary comments; convert the needed ones (for example `scripts/common.py:13-14`) to `# pyright: ignore[<rule>]`; set `reportUnnecessaryTypeIgnoreComment = "error"` in `[tool.pyright]`.
