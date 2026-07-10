---
id: arch-0feca257
auditor: arch
severity: medium
category: maintainability
area: scripts/validate-rules.py:13
status: open
found: 2026-07-10
---

# Rule-file validation logic duplicated across the shipped/internal boundary and already diverging

## Problem

`check-rules-anatomy.py` (shipped skill tool) and `validate-rules.py` (internal) both validate the same `.claude/rules/*.md` files with the same rule set, each carrying its own near-identical copy of a multi-line frontmatter parser and a symlink-safe recursive directory walker.

## Evidence

`parse_rules_frontmatter` (validate-rules.py:13-64) and `_parse_frontmatter` (check-rules-anatomy.py:34-80) are ~50-line twins; `_iter_rules_dir` (validate-rules.py:138-161) and `_iter_rules` (check-rules-anatomy.py:159-183) are ~25-line twins. They have already drifted: check-rules-anatomy parses YAML flow-style `paths: ["a","b"]` (lines 71-74) while validate-rules rejects it (line 113) — same input, opposite verdicts.

## Impact

Every rule-format change must be made twice or the two validators disagree; a flow-style `paths:` line passes the shipped tool but fails the internal CI gate. The drift is not hypothetical — it already exists.

## Fix

Make one source of truth: delete the parser/walker/per-check logic from `validate-rules.py` and have it import the shipped `check-rules-anatomy.py` helpers (internal tooling depending on the stdlib-only shipped tool points the dependency the safe direction), then render the returned findings as text + exit code.
