---
id: audit-deb62f74
auditor: audit
severity: low
category: docs
area: .mise/tasks/hook/deny-agents-path-hook.py
status: open
found: 2026-11-01
location: .mise/tasks/hook/deny-agents-path-hook.py:9-11
location_sha: fd79b7b642f11973
---

# deny-agents hook docstring still says the deny list names Edit and Write rules and never binds Bash

## Problem

The module docstring says "The `permissions.deny` list in .claude/settings.json names `Edit` and `Write` rules only, and binds the file tools, never Bash — `head`, `sed -i`, or a redirection walks straight past it", and the comment at :108 says "permissions.deny also names Edit and Write". After the owner's change the list names `Edit` only, and the permissions docs say Read/Edit deny rules apply to recognized Bash file commands (`head`, `sed`, `tee`) and redirection targets. Owner-only file (`Edit(./.mise/tasks/hook/**)` is denied).

## Evidence

.mise/tasks/hook/deny-agents-path-hook.py:9-11 (docstring) and :108-109 ("permissions.deny also names Edit and Write on `.mise/tasks/hook/**` and `.claude/settings.json`").

## Impact

The guard's own description misstates the control it complements; the next audit of the shell surface starts from a wrong premise.

## Fix

Owner edit. Line 9-11 → "The `permissions.deny` list in .claude/settings.json names `Edit` rules only (a `Write(...)` rule never matches; `Edit` covers every built-in edit tool). Claude Code also applies it to the Bash file commands it recognizes and to redirection targets, but not to an interpreter or a command that reaches a file without naming it. This hook covers the shell surface, in two different shapes:". Line 108 → "permissions.deny also names Edit on `.mise/tasks/hook/**` and".
