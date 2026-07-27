---
id: audit-4ca96a58
auditor: audit
severity: advisory
category: security
area: .claude/settings.json (PreToolUse coverage)
status: open
found: 2026-07-26
---

# No PreToolUse guard prevents an agent from editing hooks or settings.json to fail-open mid-session

## Problem

Nothing blocks an agent from editing the hook scripts or settings.json mid-session to neutralize enforcement; the deny block and every PostToolUse validator can be disabled within the session even though the threat model explicitly includes self-weakening.

## Evidence

settings.json wires validators as PostToolUse and one Bash-deny as PreToolUse, but nothing matches `Edit(scripts/hooks/**)` or `Edit(.claude/settings.json)`. An Edit turning deny-agents-path-hook.py's match branch into `return` disables the guard for the rest of the session.

## Impact

Session-scoped only — changes still reach main through PR + CI, and CODEOWNERS owns both settings.json and (via `* @ivuorinen`) scripts/hooks/, so the blast radius is one session, not the protected branch. Worth recording because the threat model names self-weakening as in-scope.

## Fix

Accept as residual (CI/CODEOWNERS is the real gate) and document it as such, or add a PreToolUse Edit|Write deny on scripts/hooks/** and .claude/settings.json requiring out-of-band change.
