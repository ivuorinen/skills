---
id: agent-loopholes-8c3cdf74
auditor: agent-loopholes
severity: low
category: security
area: .claude/skills/graphify/.graphify_version
status: open
found: 2026-09-13
location: .claude/settings.json:113
location_sha: 931eb4782d65031d
---

# graphify version pin file is writable, so the pin can follow any installed binary

## Problem

The Bash, Read and Glob guards compare `graphify --version` against `.claude/skills/graphify/.graphify_version`, but nothing protects that file, and the mismatch message names it.

## Evidence

settings.json:113 and :122 read the pin with `cat "$CLAUDE_PROJECT_DIR/.claude/skills/graphify/.graphify_version"` and print `graphify $found does not match the pinned $pinned (.claude/skills/graphify/.graphify_version)`. Probe observed in this audit: `echo 9.9.9 > .claude/skills/graphify/.graphify_version` → exit 0 from the protected-write guard.

## Impact

After an unreviewed graphify upgrade every call is denied, the denial points the agent at the pin file, and editing it silently re-trusts whatever binary is installed.

## Fix

Add `Edit(./.claude/skills/graphify/.graphify_version)` to `permissions.deny` and the path to `PROTECTED_WRITE`, and change the message to tell the agent to ask the owner. Owner-only surface.
