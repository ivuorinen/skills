# /nitpicker agent-loopholes — Loophole Hunter

Hostile audit of the project's agent enforcement surface: assume every constraint is bypassable until the enforcement path is traced end-to-end and proven to bind, then close each proven loophole and re-run the bypass to prove it blocks.

## When to use

- Auditing `.claude/rules/`, hook scripts, `.claude/settings.json`, and skills for bypassable or unenforced constraints
- A new rule, hook, skill, or settings change was added and you want to confirm it actually binds
- Before a release, to prove the enforcement surface has no silent gaps
- When asked to "close the loopholes", "harden the Claude Code setup", or "find ways our rules can be bypassed"
- Run standalone or by the `/nitpicker` default audit flow

Not for rule _quality and placement_ (kebab-case, grab-bags, misplaced CLAUDE.md rules) — that is `/nitpicker agent-rules`. Not for application source security — that is `/nitpicker security`. This command checks whether the enforcement — rules, hooks, settings, and skills together — can be _evaded_.

## Enforcement surface

Enumerate all of these every run. Never sample.

| Surface | What to read |
| --- | --- |
| Rules | Every file in `.claude/rules/` (and `~/.claude/rules/` if present) |
| Hook scripts | Every script referenced by a hook entry in settings, plus every script under any hooks directory (e.g. `scripts/hooks/`, `.claude/hooks/`) whether referenced or not |
| Hook wiring | Every `hooks` entry in `.claude/settings.json` and `.claude/settings.local.json` — event, matcher, command |
| Permissions | `permissions.allow` / `permissions.deny` / `permissions.ask` in both settings files |
| Skills | Every `SKILL.md` under `skills/` and `.claude/skills/` |
| Exclusions | `claudeMdExcludes` and any disable flags in settings |

Discover hook script paths from the settings wiring, not from a hardcoded directory — the wiring is the source of truth for what actually runs.

## Loophole classes

Check every element against every applicable class. A loophole is filed only with a concrete bypass scenario as evidence.

| Class | Definition | Bypass evidence to construct |
| --- | --- | --- |
| **Unenforced rule** | A `.claude/rules/` mandate with no hook, validator, or CI step that blocks its violation | Run the action the rule forbids and show no mechanism blocks it |
| **Fail-open hook** | A hook that exits 0 (allow) when its own logic errors, throws, or hits an unexpected input | The malformed/edge input that makes the hook pass instead of block |
| **Matcher gap** | A settings hook matcher whose pattern misses inputs the paired rule/validator claims to govern | The file path, extension variant, rename, or new-file case the matcher does not match |
| **Permission contradiction** | A `permissions.allow` entry permits what a rule forbids, or `deny`/`ask` fails to cover a forbidden action | The exact command allowed by settings but forbidden by a rule |
| **Unwired hook** | A hook script no settings entry references (dead enforcement), or a settings entry pointing to a missing/renamed script (broken enforcement) | The script that never runs, or the command path that does not resolve |
| **Excluded/disabled rule** | A rule file matched by `claudeMdExcludes`, or enforcement disabled by a flag | The exclusion glob or flag that silences it |
| **Rationalizable step** | A skill body step that is hedged or optional ("optionally", "should", "prefer", "consider") where the intent is mandatory; or an unhandled mode/flag combination that skips a safety step | The sentence an agent quotes to skip the step, or the mode combo that bypasses it |
| **Warn-only enforcement** | A hook that only prints a warning and exits 0 where the rule implies a hard block | Show the violating input passes despite the warning |
| **Bypassable mechanism** | A constraint enforced only by a skippable path (e.g. a pre-commit hook defeated by `--no-verify`, or a check in `make check` but not on the path actually used) with no rule forbidding the skip | The command that reaches the protected state without triggering enforcement |
| **Self-exempting carve-out** | A rule or hook with an exception broad enough to swallow the rule | The common case that falls entirely inside the exception |
| **Semantic validator gap** | A validator that checks structure but not the property the rule actually requires | The structurally-valid input that violates the rule yet passes |

## Process

1. Enumerate the surface. Build a complete inventory of every element in the
   Enforcement Surface table and record the count of each. Every element must be
   marked examined before the run is complete. Full examination is the only
   COMPLETE outcome; `Unexamined` is reserved for genuine time exhaustion, and any
   run with unexamined elements has run verdict INCOMPLETE — state the verdict and
   the unexamined elements prominently in the summary.
2. Trace every enforcement path. For each rule: what mechanism blocks its
   violation, and is that mechanism reachable on the path a user actually takes?
   A same-named hook is not an answer — read the hook's code and confirm it
   (a) matches the input, (b) exits non-zero on violation, and (c) exits non-zero
   on its own internal error.
3. Read every hook script line by line. Confirm its matcher covers every input
   the rule claims, it fails closed on exception and unexpected input, and the
   settings command path resolves to a script that exists.
4. Cross-check the matrices: rule × permission, rule × hook, hook script ×
   settings wiring (both directions). Record each cell. An unchecked cell is an
   unexamined loophole.
5. Read every skill body in full — including ones you recognize. Flag every
   hedged or optional step where intent is mandatory, and every mode/flag
   combination that lets a safety step be skipped.
6. File findings via the store protocol in `_conventions.md`, using
   `--auditor agent-loopholes`. Record the class and the concrete constructed bypass in
   Evidence. No finding without a constructed bypass.
7. Present the summary with the run verdict, then follow the apply-fixes prompt
   from `_conventions.md`. For this command, `(s)afe` means: only skill-body
   wording hardening and wiring an already-existing hook script into settings —
   no edits to existing hook logic, no permission removals, no new hooks or
   rules. After each fix, prove closure per Proving Closure; a loophole is not
   closed until proven. Fix edits to tracked files stay unstaged in the working
   tree.

## Proving closure

"Re-run the bypass" means demonstrate the exact evading input or quote no longer evades:

- **Executable classes** (fail-open-hook, matcher-gap, permission-contradiction, warn-only, bypassable-mechanism, semantic-gap): feed the Evidence input to the mechanism and show it now exits non-zero / blocks.
- **rationalizable-step / self-exempting**: diff the body and show the hedged wording or the swallowing carve-out is gone, replaced by an unconditional imperative.
- **unenforced-rule / unwired-hook / excluded-rule**: run the named forbidden action against the newly-wired hook/validator/CI step and show it now blocks.

A finding for which closure cannot be demonstrated stays open — never resolved as fixed.

## Bundled tool

Run the rules-anatomy checker for a programmatic first pass on `.claude/rules/` files:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/check-rules-anatomy.py" [<project_root>]
```

Non-Claude agents resolve the path relative to the nitpicker skill directory. It already detects hedged language in `.claude/rules/` files, so for a rule file flag only the _enforcement consequence_ (the unenforced-rule loophole), not the wording; reserve the `rationalizable-step` class for skill bodies and hook/CI scripts.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | A security, safety, or release-gate constraint can be silently bypassed: fail-open hook on a gating validator; permission allowing a forbidden destructive action; rule forbidding a dangerous action that settings permit |
| High | An enforcement constraint does not bind at all: unenforced rule with real consequence; unwired hook meant to enforce; matcher gap admitting a whole input class; warn-only where a block is intended; settings entry pointing to a missing script |
| Medium | Rationalizable mandatory step in a skill; bypassable-via-skip mechanism with no rule forbidding the skip; semantic validator gap; unhandled mode/flag combination skipping a safety step |
| Low | Redundant or overlapping enforcement; matcher narrower than ideal with low blast radius; unwired but provably obsolete hook script |
| Advisory | Hardening suggestion where no current bypass exists; defense-in-depth opportunity |

## Fix strategy

**Auto-applicable (ask first, apply only on approval):**

- Wire an existing-but-unreferenced hook script into `.claude/settings.json`
- Change a fail-open hook to fail closed (non-zero exit on error/unexpected input)
- Tighten a hook matcher to cover the missed input class
- Remove or narrow a `permissions.allow` entry that contradicts a rule
- Harden a hedged skill step to an unconditional imperative

**Requires explicit approval per change:**

- Adding a new enforcement hook that did not exist
- Adding a new rule to forbid a bypass (e.g. forbidding `--no-verify`)
- Deleting a rule file, hook script, or settings entry
- Any change to settings permission semantics beyond removing a contradiction

**Never auto-apply:**

- Weakening, disabling, or removing any existing constraint to resolve a finding
- Editing `.claude/settings.local.json` (gitignored, machine-specific) — propose the change and let the user apply it
- Resolving a finding as fixed without re-running its bypass and confirming it now blocks

## Common mistakes

- **"The hooks are battle-tested, I'll spot-check a couple."** Reputation is not evidence. Trace every hook's enforcement path; a battle-tested hook can still fail open on an input nobody tried.
- **"The hook is named after the rule, so the rule is enforced."** A matching name proves nothing. Confirm match, non-zero on violation, non-zero on own error.
- **"The hook exists and is wired, so it works."** Read the error handling. A hook that catches its own exception and exits 0 enforces nothing.
- **"The matcher covers the obvious case."** Diff the matcher's actual pattern against the rule's stated scope: extension variants, path forms, renames, new versus edited files. The gap is the loophole.
- **"Cross-checking every permission against every rule is tedious — I'll eyeball it."** The matrices in step 4 are mandatory and recorded cell by cell. An allow-entry that overrides a rule is exactly the loophole an eyeball misses.
- **"I recognize this skill, I don't need to re-read it."** Re-read every skill body in full. Recognition skips the hedged step an agent will quote to bypass a safety check.
- **"This hook script isn't wired in — probably deprecated."** An unwired script is a finding. Either wire it or record why it is obsolete; assuming intent is how dead enforcement hides.
- **"I described the fix, so the loophole is effectively closed."** A described fix is an open loophole. Closed means applied, bypass re-run, and proven to block.
- **"Marking the rest unexamined and shipping it as done."** Any run with unexamined elements has verdict INCOMPLETE — never "done with caveats". A run is COMPLETE only when every enumerated element is examined.
