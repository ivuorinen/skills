---
id: audit-8845c8bd
auditor: audit
severity: medium
category: performance
area: scripts/hooks/post-bash-revalidate.py:56
status: open
found: 2026-07-26
---

# post-bash-revalidate re-runs all six whole-tree gates on every Bash call once any governed path is dirty

## Problem

The hook scopes on whole-tree dirtiness rather than what the current Bash call changed, so once any governed path is dirty, every subsequent Bash call — including read-only ones — triggers a full six-gate revalidation.

## Evidence

post-bash-revalidate.py:56-65 runs `git status --porcelain --ignored` then `if not any(marker in status.stdout for marker in GOVERNED): return`. The docstring claims a read-only Bash call costs one git status, but that holds only on a clean tree.

## Impact

During normal skill development (an unstaged edit under skills/ present), every ls, grep, cat, or git log run through Bash re-runs validate-skill (whole tree), validate-rules (whole tree), check-version-sync, check-stdlib-only (whole tree), plus findings.py validate and index — six subprocesses per read. The gate cannot distinguish "this call mutated a governed file" from "the tree was already dirty."

## Fix

Cache the prior governed-path status and re-run gates only for markers newly appearing versus that snapshot, rather than on any dirty state; at minimum correct the docstring's cost claim to reflect the dirty-tree case.
