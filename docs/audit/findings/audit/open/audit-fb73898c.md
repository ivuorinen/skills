---
id: audit-fb73898c
auditor: audit
severity: low
category: conventions
area: git log main..HEAD
status: open
found: 2026-09-04
---

# Five commits take their type from the subject matter rather than consumer impact

## Problem

`.claude/rules/commit-types.md` says the type is picked from what a consumer of the
installed skill sees, never from how much work the change took or what it is about.
Five commits on this branch are typed from the subject instead, in both directions.

## Evidence

Two commits are typed `feat:` while touching only an internal dev skill, which CLAUDE.md
states is not shipped to consumers:

```text
--- ee55434  feat: add epistemic pressure and failing-RED discipline to skill-tester
      .claude/skills/skill-tester/SKILL.md
--- 1c156ce  feat: record what running skill-tester against itself actually showed
      .claude/skills/skill-tester/SKILL.md
```

No path under `skills/` changed in either, so no consumer sees a difference.

One commit is typed `docs:` while adding a new gating test, which the rule names as the
illustrative case for `feat:` ("a new gate wired into `make check` or CI. A new
enforcement gate is a feature"):

```text
--- 2d8f83d  docs: name every PreToolUse hook in CLAUDE.md and pin it with a test
      CLAUDE.md
      tests/test_settings.py
+def test_every_pretooluse_hook_is_documented_in_claude_md():
+    assert undocumented == [], (
```

`tests/` is not in the rule's docs/chore "confined to" list.

Two commits are typed `chore:` while repairing shipped behaviour, which is `fix:`:

```text
--- c85d5a7  chore: allow python3 through the ctx-ok guard
      scripts/hooks/guard-ctx-ok-hook.py
      tests/test_hooks.py
--- 0ec38c7  chore: make index-check test staleness rather than uncommitted state
      .gitignore
      Makefile
```

The first repaired a guard that denied the findings-store CLI, leaving an agent with no
sanctioned way to file a finding. The second repaired a gate that failed on a byte
identical index whenever anything else in the tree was dirty, which stopped `make` before
the scanners and the test suite ran. A sibling commit on the same branch, `892a8c8`, is
typed `fix:` for a directly comparable hook repair, so the branch applies the rule
inconsistently to adjacent commits.

## Impact

The release outcome is unaffected. Merges here are squash-only and release-please reads
the pull request title, and the branch already carries genuine `feat:` commits that earn
a minor bump. The cost is to the audit trail: a reader scanning history for
behaviour-changing repairs misses two, and a reader scanning for new consumer-visible
features finds two that are not. `git log -S` and cherry-picks inherit the wrong signal.

## Fix

Reword the five before merge, while the branch is unmerged and rewording costs nothing:
`ee55434` and `1c156ce` to `docs:`, `2d8f83d` to `feat:`, `c85d5a7` and `0ec38c7` to
`fix:`. Title the squashed pull request `feat:`, which is correct for the branch as a
whole: it adds per-scanner reference files routed through `np_read_reference`, adds the
`np_check_agent_instructions` tool, and hardens the CodeQL gate, alongside the security
repairs.
