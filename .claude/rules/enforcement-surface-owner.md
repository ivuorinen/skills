---
paths:
  - "scripts/hooks/**"
  - ".claude/settings.json"
---

# The Enforcement Surface Belongs to the Owner

The hooks under `scripts/hooks/`, `.claude/settings.json` and the sub-agent
definitions decide what an agent session may do. An agent that edits them is
rewriting its own constraints, so every change to them is the owner's to make.

`deny-agents-path-hook.py` blocks a Bash **write** to `scripts/hooks/` or
`.claude/settings.json` (`PROTECTED_WRITE`) while reading stays allowed. Hand
those edits to the owner rather than reaching for another spelling. The guard
matches command text, so a route it does not recognise — an interpreter
one-liner, a script, a differently quoted path — is a gap in the guard, not
permission.

When a fix needs a change there, stop and describe the edit — the file, the
change, and why — for the owner to apply.

## Enforcement

Partly gated. `deny-agents-path-hook.py` blocks the Bash write forms it
recognises; `.github/CODEOWNERS` plus branch protection is the binding control.
Every other route is agent discipline.
