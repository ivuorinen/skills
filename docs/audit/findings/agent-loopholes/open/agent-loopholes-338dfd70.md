---
id: agent-loopholes-338dfd70
auditor: agent-loopholes
severity: high
category: security
area: scripts/hooks/post-bash-revalidate.py
status: open
found: 2026-08-09
---

# An agent can disable its own guards with one Bash edit: scripts/hooks and settings.json are denied to Edit but ungoverned by every Bash-side control

## Problem

`.claude/settings.json` denies `Edit`, `Write`, and `NotebookEdit` on `scripts/hooks/**` and on `.claude/settings.json` itself. As CLAUDE.md states for the sibling case, `permissions.deny` "covers only the Read/Edit/Write tools, not Bash". No Bash-side control covers these two paths: `deny-agents-path-hook.py` matches only `.claude/agents/`, and `post-bash-revalidate.py`'s `GOVERNED` list omits both. A single `sed -i` therefore rewrites the enforcement surface with nothing denying, revalidating, or reporting it.

## Evidence

The deny list (`.claude/settings.json`) reaches only the file-editing tools:

```json
"deny": [
  "Read(./.claude/agents/**)", "Edit(./.claude/agents/**)", "Write(./.claude/agents/**)",
  "Edit(./scripts/hooks/**)", "Write(./scripts/hooks/**)", "NotebookEdit(./scripts/hooks/**)",
  "Edit(./.claude/settings.json)", "Write(./.claude/settings.json)", "NotebookEdit(./.claude/settings.json)"
]
```

`post-bash-revalidate.py:31-40` — the paths a Bash edit re-validates:

```python
GOVERNED = (
    "skills/", ".claude/rules/", "docs/audit/findings/",
    "package.json", "pyproject.toml", ".release-please-manifest.json",
    ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
)
```

Neither `scripts/hooks/` nor `.claude/settings.json` appears. Nor does
`scripts/` — the validators (`validate-skill.py`, `validate-rules.py`,
`check-stdlib-only.py`, `check-version-sync.py`) those gates invoke.

The PreToolUse `Bash` matchers registered in settings are
`deny-agents-path-hook.py`, `deny-unsafe-git-hook.py`, `guard-ctx-ok-hook.py`,
`ask-destructive-restore-hook.py` and the two graphify guards. Only the first
inspects paths, and its patterns are `_DENIED_RE` plus the
`_CLAUDE_RE`/`_AGENTS_INDIRECT_RE` pair at line 163 — all scoped to
`.claude/agents`.

Failing scenario:

```bash
sed -i 's/^PROTECTED = .*/PROTECTED = frozenset()/' scripts/hooks/deny-unsafe-git-hook.py
```

`deny-agents-path-hook` sees no agents token and allows it. The edit lands.
`post-bash-revalidate` runs `git status`, finds no `GOVERNED` marker in the
porcelain line for `scripts/hooks/...`, and returns at line 69 without running
a single gate. The push-to-protected-branch guard is now inert, silently, and
the next `git push origin main` succeeds. The same one-liner against
`.claude/settings.json` unregisters every hook at once.

The inconsistency is the proof this is an oversight rather than a decision:
`.claude/agents/` received a dedicated Bash guard precisely because the deny
list could not reach Bash, and `post-bash-revalidate.py`'s own comment
explains that Write|Edit validators "never see a Bash-mediated mutation
(`sed -i`, `>` redirection, `git mv`, `cp`, `patch`)" — the exact vector left
open here.

## Impact

Every in-session control this repo documents — the no-verify guard, the protected-branch push guard, the ctx-ok guard, the destructive-restore confirmation, the agents-path guard, and all six PostToolUse validators — is disableable by one Bash command that no control observes. The paths are protected against the honest mistake (an Edit call) and open to the mechanism the repo already identified as the bypass. CI remains the binding gate, as `commit-gate-integrity.md` says, but the session-level surface is defeated silently and the operator gets no signal.

## Fix

Two changes, both narrow:

1. Add `"scripts/"` and `".claude/settings.json"` to `GOVERNED` in `scripts/hooks/post-bash-revalidate.py`. The list is matched as substrings against `git status --porcelain --ignored` output, so `"scripts/"` covers both `scripts/` and `scripts/hooks/` and the existing over-validation note already accepts false positives as fail-safe.
2. Extend the PreToolUse deny guard to the enforcement surface: generalise `deny-agents-path-hook.py` from an agents-only matcher to a protected-paths matcher covering `.claude/agents/`, `scripts/hooks/`, and `.claude/settings.json`, keeping the existing literal/quoted/escaped/variable-built/glob token coverage and the fail-closed exit 2.

Both files are under `permissions.deny` for Edit/Write, so these edits need the repo owner. Cover the new denials with cases in `tests/test_hooks.py`, which already has the harness. Note that `.github/CODEOWNERS` plus branch protection stays the binding control either way — this raises the cost of the bypass, it does not close it.
