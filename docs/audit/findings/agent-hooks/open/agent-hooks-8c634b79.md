---
id: agent-hooks-8c634b79
auditor: agent-hooks
severity: high
category: docs
area: scripts/hooks
status: open
found: 2026-09-13
location: .claude/rules/counts-in-prose.md:1-10
location_sha: 39fd79b42218d4b2
---

# Count-in-prose drift keeps recurring and no hook watches for it

## Problem

Stale counts in prose are a recurring defect class in the resolved ledger, and `counts-in-prose.md` states it is author discipline with no gate. No PostToolUse hook flags a spelled-out count added to documentation.

## Evidence

Resolved ledger records of this class: N-053 (`make check` description stale in three files), N-097, N-101 ("five steps" now six), audit-0aa80c9a ("30+ commands" understates by ten), audit-0bc97950 (claims 21 audit gates; release-prep defines 22), agent-rules-aa40a4c3 (a CLI-only set of three stated as five), agent-rules-51707aba, audit-c810221c. Live instances found in this audit: `post-bash-revalidate.py:7` "The five Write|Edit validators" against seven registered, and the stale counts filed under docs.

## Impact

Each new file, tool or gate silently falsifies another count, and every audit re-files the same class.

## Fix

Add a PostToolUse hook on `Write|Edit` for `*.md` files and Python docstrings that matches a spelled-out number word followed by a set noun (tools, hooks, validators, modules, operations, manifests, classes, commands, gates, rules) and returns the matching lines on stderr with a reminder to name the set or cite its gate. Feedback only, since structural counts are allowed.
