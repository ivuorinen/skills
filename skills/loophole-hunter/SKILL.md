---
name: loophole-hunter
description: Audits a Claude Code project's enforcement surface (rules, hooks, settings, permissions, skills) for bypassable or unenforced constraints and closes them. Use when auditing .claude/rules, hooks, .claude/settings.json, and skills for loopholes, when asked to close loopholes or harden the Claude Code setup against evasion, or when invoked by nitpicker in loophole mode.
---

# Loophole Hunter

## Overview

Hostile audit of the project's Claude Code enforcement surface. It assumes every constraint is bypassable until the enforcement path is traced end-to-end and proven to bind. It enumerates every rule, every hook script, every settings hook wiring, every permission, and every skill body, then hunts for loopholes — places where an intended constraint does not actually constrain: a rule no hook enforces, a hook that fails open, a settings permission that contradicts a rule, a matcher that misses inputs it claims to cover, a hook script that is never wired in, a skill step an agent can rationalize past. It writes a findings report and, on approval, closes each loophole — then re-runs the bypass to prove the loophole is gone. Single-shot: re-validate existing findings, enumerate the surface, file new findings, optionally fix, re-validate.

This is not `claude-rules-auditor`. That skill checks whether rules are well-formed and well-placed. This skill checks whether the enforcement — across rules, hooks, settings, and skills together — can be evaded.

## When to Use

- Auditing `.claude/rules/`, hook scripts, `.claude/settings.json`, and skills for bypassable or unenforced constraints
- A new rule, hook, skill, or settings change was added and you want to confirm it actually binds
- Before a release, to prove the enforcement surface has no silent gaps
- When asked to "close the loopholes", "harden the Claude Code setup", or "find ways our rules can be bypassed"
- Invoked by `nitpicker` in `loophole` mode

**When NOT to use:** For rule *quality and placement* (kebab-case, grab-bags, misplaced CLAUDE.md rules), use `claude-rules-auditor`. For application source security, use `security-auditor`.

## Enforcement Surface

Enumerate all of these every run. Never sample.

| Surface | What to read |
|---------|--------------|
| Rules | Every file in `.claude/rules/` (and `~/.claude/rules/` if present) |
| Hook scripts | Every script referenced by a hook entry in settings, plus every script under any hooks directory (e.g. `scripts/hooks/`, `.claude/hooks/`) whether referenced or not |
| Hook wiring | Every `hooks` entry in `.claude/settings.json` and `.claude/settings.local.json` — event, matcher, command |
| Permissions | `permissions.allow` / `permissions.deny` / `permissions.ask` in both settings files |
| Skills | Every `SKILL.md` under `skills/` and `.claude/skills/` |
| Exclusions | `claudeMdExcludes` and any disable flags in settings |

Discover hook script paths from the settings wiring, not from a hardcoded directory — the wiring is the source of truth for what actually runs.

## Loophole Classes

Check every element against every applicable class. A loophole is filed only with a concrete bypass scenario as evidence.

| Class | Definition | Bypass evidence to construct |
|-------|------------|------------------------------|
| **Unenforced rule** | A `.claude/rules/` mandate with no hook, validator, or CI step that blocks its violation | Run the action the rule forbids and show no mechanism blocks it |
| **Fail-open hook** | A hook that exits 0 (allow) when its own logic errors, throws, or hits an unexpected input | The malformed/edge input that makes the hook pass instead of block |
| **Matcher gap** | A settings hook matcher whose pattern misses inputs the paired rule/validator claims to govern | The file path, extension variant, rename, or new-file case the matcher does not match |
| **Permission contradiction** | A `permissions.allow` entry permits what a rule forbids, or `deny`/`ask` fails to cover a forbidden action | The exact command allowed by settings but forbidden by a rule |
| **Unwired hook** | A hook script that no settings entry references (dead enforcement), or a settings entry pointing to a missing/renamed script (broken enforcement) | The script that never runs, or the command path that does not resolve |
| **Excluded/disabled rule** | A rule file matched by `claudeMdExcludes`, or enforcement disabled by a flag | The exclusion glob or flag that silences it |
| **Rationalizable step** | A skill body step that is hedged or optional ("optionally", "if time", "should", "when possible", "prefer", "consider") where the intent is mandatory; or an unhandled mode/flag combination that skips a safety step | The sentence an agent quotes to skip the step, or the mode combo that bypasses it |
| **Warn-only enforcement** | A hook that only prints a warning and exits 0 where the rule implies a hard block | Show the violating input passes despite the warning |
| **Bypassable mechanism** | A constraint enforced only by a path that can be skipped (e.g. a git pre-commit hook defeated by `--no-verify`, or a check in `make check` but not on the path actually used) with no rule forbidding the skip | The command that reaches the protected state without triggering enforcement |
| **Self-exempting carve-out** | A rule or hook with an exception broad enough to swallow the rule | The common case that falls entirely inside the exception |
| **Semantic validator gap** | A validator that checks structure but not the property the rule actually requires | The structurally-valid input that violates the rule yet passes |

## Process

```
0. Re-validate existing findings
   If docs/audit/loophole-hunter-findings.md exists, re-validate each OPEN finding:
   - Loophole now closed (re-run the bypass — it blocks) → move to Fixed (record date)
   - Finding was wrong → move to Invalid (record reason)
   - Still bypassable → leave Open

1. Enumerate the surface
   Build a complete inventory of every element in the Enforcement Surface table.
   Record the count of each. This inventory is the coverage checklist — every element
   must be marked examined before the run is complete. Do not proceed on a sample.
   Full examination of every enumerated element is the default and the only COMPLETE
   outcome. `Open-Unexamined` is reserved for genuine time exhaustion, not convenience,
   and any run with one or more `Open-Unexamined` elements has run verdict INCOMPLETE.

2. Trace every enforcement path
   For each rule, answer: what mechanism blocks its violation, and is that mechanism
   reachable on the path a user actually takes? Existence of a same-named hook is not
   an answer — read the hook's code and confirm it (a) matches the input, (b) exits
   non-zero on violation, and (c) exits non-zero on its own internal error.

3. Read every hook script line by line
   For each hook script: confirm its matcher in settings covers every input the rule
   claims; confirm it fails closed (non-zero) on exception and on unexpected input;
   confirm the settings command path resolves to the script that exists.

4. Cross-check the matrices
   - Rule × permission: every rule prohibition vs every settings allow/deny/ask entry.
   - Rule × hook: every rule vs the hook (if any) that enforces it.
   - Hook script × settings wiring: every script vs the entry that runs it (both directions).
   Record each cell. An unchecked cell is an unexamined loophole.

5. Read every skill body
   Read every SKILL.md in full — including ones you recognize. Flag every hedged or
   optional step where intent is mandatory, and every mode/flag combination that lets a
   safety step be skipped.

6. File findings
   For each loophole, assign the next LH-NNN id and record class, evidence (the concrete
   bypass), impact, and the exact fix. No finding without a constructed bypass.

7. Write docs/audit/loophole-hunter-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.

8. Present summary — state the run verdict (COMPLETE only if zero elements are
   Open-Unexamined) — then ask: "Close loopholes? (a)ll  (c)ritical-and-high only  (s)afe  (n)o"
   - `(a)ll` / `(c)ritical-and-high only`: apply the matching Auto-applicable fixes.
   - `(s)afe`: apply only skill-body wording hardening and wiring an already-existing hook
     script into settings. Make no edits to existing hook logic, no permission removals, and
     add no new hooks or rules.
   Apply fixes in severity order (Critical first). After each fix, prove closure per
   "Proving Closure" below; a loophole is not closed until proven. Move proven-closed
   findings to Fixed.

9. Commit gate
   Fix edits to tracked files (`.claude/settings.json`, hook scripts, rule files, skills)
   are left in the working tree unstaged — never stage or commit them silently. Then ask:
   "Commit findings to git? (y/n)" and, on yes, stage only `docs/audit/loophole-hunter-findings.md`.
```

## Proving Closure

"Re-run the bypass" means demonstrate the exact evading input or quote no longer evades.
The demonstration depends on the loophole class:

- **Executable classes** (fail-open-hook, matcher-gap, permission-contradiction, warn-only,
  bypassable-mechanism, semantic-gap): feed the Evidence input to the mechanism and show it
  now exits non-zero / blocks.
- **rationalizable-step / self-exempting**: diff the body and show the hedged wording or the
  swallowing carve-out is gone, replaced by an unconditional imperative.
- **unenforced-rule / unwired-hook / excluded-rule**: run the named forbidden action (or its
  triggering input) against the newly-wired hook/validator/CI step and show it now blocks.

A finding for which closure cannot be demonstrated stays Open — never moved to Fixed.

## Utility script reuse

Two sibling skills ship scripts this skill reuses. Invoke both with the `uv run --quiet`
runner the repo mandates:

```bash
uv run --quiet skills/claude-rules-auditor/check-rules-anatomy.py
uv run --quiet skills/nitpicker/check-audit-consistency.py docs/audit/loophole-hunter-findings.md
```

Run `check-rules-anatomy.py` for a programmatic first pass on `.claude/rules/` files, and
`check-audit-consistency.py` on the findings file before step 0 re-validation. If either
script is absent, proceed and record the gap as Advisory. Do not duplicate their checks —
`check-rules-anatomy.py` already detects hedged language in `.claude/rules/` files, so for a
rule file flag only the *enforcement consequence* (the unenforced-rule loophole), not the
wording; reserve the `rationalizable-step` class for skill bodies and hook/CI scripts.

## Findings Format

Output path: `docs/audit/loophole-hunter-findings.md`

```
# Loophole Hunter Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N elements Open-Unexamined)
- Surface enumerated: rules N | hook scripts N | hook wirings N | permissions N | skills N
- Examined: rules N | hook scripts N | hook wirings N | permissions N | skills N
- Open-Unexamined: N
- Unexamined: <surface element path> — <why not examined>

## Open Findings

### Critical

#### [LH-NNN] Short title
Status: Open
Class: <unenforced-rule|fail-open-hook|matcher-gap|permission-contradiction|unwired-hook|excluded-rule|rationalizable-step|warn-only|bypassable-mechanism|self-exempting|semantic-gap>
Area: <file path or settings key>
Problem: <what constraint fails to bind>
Evidence: <the concrete bypass — the exact input, command, or quoted step that evades enforcement>
Impact: <what the bypass allows>
Fix: <exact change — the line, matcher, permission, or hook to add/alter>

### High
[same structure]

### Medium
[same structure]

### Low
[same structure]

### Advisory
[same structure]

## Fixed

### Pass N — YYYY-MM-DD

#### [LH-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <what changed, and the re-run of the bypass that now blocks>

## Invalid

### Pass N — YYYY-MM-DD

#### [LH-NNN] Short title
Notes: <why the bypass does not actually work>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and
rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding
entries, and re-emits all other `## Summary` bullets after it. Keep the Total line in exactly
that shape and never insert extra fields into it, or the hook's regex will not match. All
supplementary bullets (`Run verdict`, `Surface enumerated`, `Examined`, `Open-Unexamined`,
`Unexamined:`) follow the Total line; the hook preserves them but will not preserve any `##`
section it does not recognize, so unexamined elements live as `Unexamined:` Summary bullets,
never in a separate section. `Open-Unexamined` equals the number of `Unexamined:` bullets and
is not part of the Open/Fixed/Invalid finding totals.

The per-finding `Status:` field is `Open` for an examined-and-bypassable finding. Surface
elements left unexamined are not findings — they are the `Unexamined:` Summary bullets. Step 0
re-validation re-checks every finding with `Status: Open`.

Finding ID format: `LH-NNN` (zero-padded to 3 digits). Assign sequentially; never reuse ids.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | A security, safety, or release-gate constraint can be silently bypassed: fail-open hook on a gating validator; permission that allows a forbidden destructive action; rule forbidding a dangerous action that settings permit |
| High | An enforcement constraint does not bind at all: unenforced rule with real consequence; unwired hook meant to enforce; matcher gap admitting a whole input class; warn-only where a block is intended; settings entry pointing to a missing script |
| Medium | Rationalizable mandatory step in a skill; bypassable-via-skip mechanism with no rule forbidding the skip; semantic validator gap; unhandled mode/flag combination skipping a safety step |
| Low | Redundant or overlapping enforcement; matcher narrower than ideal with low blast radius; hook script that is unwired but provably obsolete |
| Advisory | Hardening suggestion where no current bypass exists; defense-in-depth opportunity |

## Fix Strategy

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
- Closing a finding without re-running its bypass and confirming it now blocks

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"The hooks are battle-tested, I'll trust them and spot-check a couple."** Authority and reputation are not evidence. Trace every hook's enforcement path yourself; a battle-tested hook can still fail open on an input nobody tried.

**"I skimmed the files and they look fine."** A skim is not an enforcement-path trace. Read every rule, hook, and skill body line by line. "Looks fine" is not a finding state — "bypass constructed and it blocks" is.

**"I'll check the important rules and assume the rest follow the same pattern."** Sampling is the loophole. Enumerate the entire surface in step 1 and mark every element examined. An unchecked element is an unfiled finding, which is implicit approval of a bypass.

**"The hook is named after the rule, so the rule is enforced."** A matching name proves nothing. Confirm the hook matches the input, exits non-zero on violation, and exits non-zero on its own error before calling a rule enforced.

**"The hook exists and is wired, so it works."** Existence is not function. Read the error handling. A hook that catches its own exception and exits 0 enforces nothing.

**"The matcher covers the obvious case, so it covers all cases."** Diff the matcher's actual pattern against the rule's stated scope: extension variants, path forms, renames, new versus edited files. The gap between them is the loophole.

**"Cross-checking every permission against every rule is tedious bookkeeping, I'll eyeball it."** The permission × rule matrix in step 4 is mandatory and recorded cell by cell. An allow-entry that overrides a rule is exactly the loophole an eyeball misses.

**"I recognize this skill, I don't need to re-read it."** Re-read every skill body in full. Recognition skips the hedged step an agent will quote to bypass a safety check.

**"This hook script isn't wired in — probably deprecated, not my problem."** An unwired script is a finding, not a non-issue. Confirm whether it was meant to enforce something; either wire it or record why it is obsolete. Assuming intent is how dead enforcement hides.

**"I found and described the fix, so the loophole is effectively closed."** A described fix is an open loophole. A loophole is closed only after the fix is applied and the bypass from the Evidence line is re-run and proven to block.

**"It's an internal surface and I'm tired — good enough is good enough."** The bar is fixed by evidence, not by audience or fatigue. Internal enforcement surfaces gate releases and other agents; a silent bypass there is a Critical, not a rounding error.

**"A truly exhaustive hunt would take too long, the fast findings are the deliverable."** "All loopholes" means the entire enumerated surface examined, not the subset found before the deadline. If time is genuinely insufficient, report the inventory with unexamined elements marked Open-Unexamined — never present a partial sweep as complete.

**"I'll mark the rest Open-Unexamined and ship it as done."** Open-Unexamined is not a free pass to skip work. It exists only for genuine time exhaustion, and any run that uses it has run verdict INCOMPLETE — never COMPLETE, never "done with caveats". State the INCOMPLETE verdict and the unexamined count prominently in the summary. A run is COMPLETE only when every enumerated element is examined.
