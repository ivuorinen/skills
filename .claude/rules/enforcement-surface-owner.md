---
paths:
  - ".mise/tasks/hook/**"
  - ".claude/settings.json"
---

# The Enforcement Surface Belongs to the Owner

The hooks under `.mise/tasks/hook/`, `.claude/settings.json` and the sub-agent
definitions decide what an agent session may do. An agent that edits them is
rewriting its own constraints, so every change to them is the owner's to make.

The project's mise config (`mise.toml`, `mise.lock`, and every other file mise
reads) is not on the surface, and stays agent-writable. The hooks are mise file
tasks, but Claude Code never runs them through mise: each runs by path as
`uv run --quiet "$CLAUDE_PROJECT_DIR/.mise/tasks/hook/<file>"` (graphify-guard
under `bash`), so no `[tasks]` entry can replace one and no `[env]`, `[tools]`,
version file or `.miserc.toml` env selection reaches one.

`deny-agents-path-hook.py` blocks a shell **write** to any `PROTECTED_WRITE`
path — `.mise/tasks/hook/`, `.claude/settings.json`, `.claude/settings.local.json`
and `.claude/skills/graphify/.graphify_version` — from Bash or a context-mode
shell call, and refuses context-mode code in another language that names one of
them, while reading stays allowed. Hand those edits to the owner rather than
reaching for another spelling. The guard
matches command text, so a route it does not recognise — an interpreter
one-liner, a script, a differently quoted path — is a gap in the guard, not
permission.

When a fix needs a change there, stop and describe the edit — the file, the
change, and why — for the owner to apply.

## Enforcement

Partly gated. `deny-agents-path-hook.py` blocks the Bash write forms it
recognises; `.github/CODEOWNERS` plus branch protection is the binding control.
Every other route is agent discipline.
