---
id: audit-cd3a47b6
auditor: audit
severity: medium
category: security
area: .claude/settings.json
status: open
found: 2026-08-18
---

# permissions.deny names Edit but not Write, and nothing tests it

## Problem

The deny list protects the agent-enforcement surface with four rules:

```json
"deny": [
  "Read(./.claude/agents/**)",
  "Edit(./.claude/agents/**)",
  "Edit(./scripts/hooks/**)",
  "Edit(./.claude/settings.json)"
]
```

`Write(...)` appears in none of them, yet `CLAUDE.md` line 219 states the block "covers only the Read/Edit/Write tools, not Bash" — asserting Write-tool coverage the configuration does not name. `Write` and `Edit` are separate tools; a rule naming one does not obviously bind the other, and the list's own shape argues it does not, since the agents path needed a separate `Read(...)` entry alongside `Edit(...)` rather than relying on one rule to cover several tools.

Two readings, and the repo does not distinguish them: either Claude Code matches `Edit(...)` against the Write tool too — in which case the behaviour is undocumented and the asymmetry is confusing — or it does not, and creating or overwriting a hook script through Write is ungated.

Deliberately not probed. `.claude/rules/` and this repo's own conventions make the enforcement surface owner-only on every write path, so writing to `scripts/hooks/` to observe whether the guard fires is exactly the move an audit must not make. The finding rests on the configuration and the documentation, not on an attempt.

## Evidence

```text
=== full permissions block ===
{ "deny": [ "Read(./.claude/agents/**)", "Edit(./.claude/agents/**)",
            "Edit(./scripts/hooks/**)", "Edit(./.claude/settings.json)" ] }

=== does anything test the deny list? ===
(no matches for 'permissions' in tests/test_settings.py)

=== what test_settings.py asserts ===
  test_write_edit_hook_registered            — hooks wired
  test_bash_revalidate_hook_registered       — hooks wired
  test_stop_reminder_registered              — hooks wired
  test_pretooluse_hooks_registered           — hooks wired
  test_every_hook_script_on_disk_is_wired    — hooks wired
  test_every_registered_hook_script_exists   — hooks wired
```

`test_settings.py` pins hook wiring from both directions — every script on disk is registered, every registered script exists — and asserts nothing whatsoever about `permissions`. The entire `deny` block could be deleted and the suite stays green.

## Impact

Defense-in-depth only, which is why this is not High: `.github/CODEOWNERS` carries a `* @ivuorinen` catch-all, so every path here already requires an owner review on a PR, and `.claude/rules/vendored-skills.md` correctly names that ruleset as the binding control rather than any in-repo artifact.

What is lost is the in-session layer. `permissions.deny` is what stops an agent from touching the enforcement surface *before* a human ever sees a diff, and its coverage of the Write tool currently rests on an assumption no gate checks and no comment records. The untested half is the more certain defect: a future edit that drops or narrows the block produces no failure anywhere, and the repo's own `agent-loopholes` command exists to catch exactly this class.

## Fix

Two changes, both cheap:

1. Name Write explicitly, so coverage does not depend on how one client resolves rule-to-tool matching:

   ```json
   "Write(./.claude/agents/**)",
   "Write(./scripts/hooks/**)",
   "Write(./.claude/settings.json)"
   ```

   Redundant if `Edit(...)` already covers Write; harmless if so, and load-bearing if not.

2. Add a test to `tests/test_settings.py` pinning the deny list — that each protected path appears, and for which tools — mirroring `test_every_hook_script_on_disk_is_wired`. Without it the block is the only part of the enforcement surface with no gate of its own.

Then correct or confirm the `CLAUDE.md` sentence so the prose and the configuration agree.
