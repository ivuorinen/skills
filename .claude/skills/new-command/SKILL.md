---
name: new-command
description: Use when creating a new hostile audit command for the nitpicker skill in this repository.
disable-model-invocation: true
---

# New Command Scaffolder

Creates a public command under `skills/nitpicker/commands/<name>.md` and
stress-tests it through the full RED → GREEN → REFACTOR → adversarial-review
→ validate → PR cycle before declaring it done.

Every command this skill produces is built to counter rationalizations. This
skill holds itself to the same standard: the phases below are not skippable,
and the excuses for skipping them are countered here, in the same table form
the commands use.

## Sequencing rule — read before Phase 1

The phases run **in order**, and each phase is a **real tool call** that
leaves an **exit artifact in this conversation**. A phase you "reasoned
through", "already know the outcome of", or "folded into" another phase did
**not run**. You do not advance to phase N+1 until phase N's exit artifact is
present in the transcript above.

At the start, list the seven phases as a todo (one item each) and mark each
done only when its exit artifact exists. The skill is finished only when the
Command Quality Gate is satisfied by **pasted evidence**, not by assertion.

## Do not skip — rationalizations

Every row is an excuse for collapsing this lifecycle. Every row is countered.
If you catch yourself forming one of these thoughts, that is the signal the
phase is load-bearing — run it.

| Rationalization | Counter |
| --- | --- |
| "It's a simple command, RED is overkill." | RED is where you learn which rationalizations the command must counter. Skip it and the command ships with uncountered loopholes — the exact defect this skill exists to prevent. |
| "I can run skill-tester in my head / I know what the subagent would say." | You cannot. The subagent runs in a **clean context** with no command loaded; your context already holds the command's intent and cannot reproduce the naive baseline. An imagined RED/GREEN is not RED/GREEN. Dispatch the real subagent. |
| "ponytail / laziness says minimal — collapse the phases." | ponytail governs solution **size**, never prescribed **process**. `.claude/rules/skill-lifecycle.md` forbids skipping any phase. Dropping a phase is not lazy, it is unfinished work. |
| "GREEN passed conceptually, no need to re-run after REFACTOR." | Refactoring wording reopens loopholes. Phase 4 re-runs the subagent because edits to rule text change what the agent can rationalize. |
| "The review/PR phases are the same lens twice — run one." | Phase 5 reviews the command **body** as source. Phase 7 reviews the **staged diff** (table sync, routing, README). They catch different defects. Run both. |
| "I'm under deadline / this is the Nth task / a reviewer said skip it." | Time, sunk cost, exhaustion, and authority are the four pressure types skill-tester itself injects. Yielding to them here is the failure mode the tool is built to expose. |
| "I'll commit now and finish the gate after." | The commit is Phase 7's exit artifact and lands **only** after the gate passes. A `feat: add /nitpicker <name>` commit on an unfinished gate is a skipped lifecycle. |

## Phase 1 — TDD Baseline (RED)

Before writing a single line of command content, dispatch a `/skill-tester`
RED subagent (clean context, no command loaded) against a scenario that
exercises the rule you are encoding. Combine the pressure types
(time, sunk-cost, authority, exhaustion). Record every rationalization the
agent uses to skip the rule — each one must be countered in the command body.

**Exit artifact:** the dispatched subagent's result in the transcript, plus
the enumerated list of rationalizations it produced. No subagent call → phase
not run.

## Phase 2 — Scaffold

1. Choose a short kebab-case command name (2.0 vocabulary: `perf`, `deps`,
   `errors` — not `-auditor`/`-hunter` suffixes).

2. Create the file `skills/nitpicker/commands/<name>.md`:

   ```markdown
   # /nitpicker <name> — <Short Title>

   <one-line purpose>

   ## When to use

   <trigger conditions and phrasings>
   ```

3. Required sections after that (no YAML frontmatter — only the router
   SKILL.md has frontmatter): the hostile mindset/scope, a deterministic
   checklist, domain-specific rules, and domain-specific common mistakes.
   Do NOT restate what `commands/_conventions.md` already binds (severity
   table, findings store protocol, generic rules) — findings are filed via
   `findings.py --auditor <name>`.

4. Counter every Phase 1 rationalization explicitly in the command body.
   Use "rationalization" (US spelling) consistently.

**Exit artifact:** the created command file, with a written mapping of each
Phase 1 rationalization to the sentence in the body that counters it.

## Phase 3 — Verify Behaviour (GREEN)

Dispatch the `/skill-tester` subagent again — same scenario and pressure —
this time with the command loaded (`/nitpicker <name>`). Confirm the agent
complies with every rule and that each Phase 1 rationalization is blocked. If
the agent finds a new loophole, add an explicit counter and re-run until no
loopholes remain.

**Exit artifact:** the second subagent's result in the transcript, showing
each Phase 1 rationalization now blocked. An assertion that "it would comply"
is not this artifact.

## Phase 4 — Refactor

- Remove hedging language ("might", "could", "potential", "consider") — every
  statement must be unconditional.
- Tighten rule wording so each rule can be tested by a single scenario.
- Consolidate duplicate or overlapping rules; anything generic moves to
  `_conventions.md` (only if it truly binds every command).
- Re-run `/skill-tester` after refactoring — all GREEN scenarios must pass.

**Exit artifact:** the post-refactor skill-tester subagent result, confirming
no regression and no new loophole.

## Phase 5 — Adversarial Review

Run `/nitpicker review` against the new command file. Treat the command body
as code under review — hunt ambiguous rules, missing edge-case coverage,
hedged language, instructions that permit rationalization. Fix every HIGH or
CRITICAL finding and re-run until none remain.

**Exit artifact:** the `/nitpicker review` output showing zero HIGH or
CRITICAL findings on the final pass.

## Phase 6 — Structural Validation

1. Add the command's row to the `## Commands` table in
   `skills/nitpicker/SKILL.md` (the validator enforces table ↔ file 1:1).
2. Add the routing phrase to `.claude/skills/skills/SKILL.md` (Routing
   Guide) and the command row in `README.md`. Update
   `.github/copilot-instructions.md` only if the command changes a rule
   stated there.
3. Run the validator:

   ```bash
   uv run scripts/validate-skill.py skills/nitpicker/SKILL.md
   ```

4. Run `/validate-skills` to confirm everything remains consistent.

**Exit artifact:** the validator output (exit 0) and the `/validate-skills`
output (clean), both pasted.

## Phase 7 — PR Review

Run `/nitpicker pr` on the staged diff. Fix all findings at HIGH or above,
re-running until clean. Only then commit with
`feat: add /nitpicker <name> command` — this triggers a minor version bump.

**Exit artifact:** the `/nitpicker pr` output showing zero HIGH+ findings,
followed by the commit.

## Command Quality Gate

A command is **not done** until every box below is checked **by pasted
evidence in this conversation** — the subagent result, the tool output, the
validator exit line. A checkbox ticked without its evidence is a skipped
phase, not a passed gate.

- [ ] Phase 1 RED: subagent dispatched, rationalizations enumerated
- [ ] Phase 3 GREEN: subagent re-dispatched with command loaded, every RED rationalization blocked
- [ ] Phase 4 REFACTOR verify: subagent re-run, no new loopholes
- [ ] Phase 5 `/nitpicker review`: no HIGH or CRITICAL findings remain
- [ ] Phase 6 `uv run scripts/validate-skill.py skills/nitpicker/SKILL.md` exits 0
- [ ] Phase 6 `/validate-skills` exits clean
- [ ] Phase 7 `/nitpicker pr`: no HIGH or CRITICAL findings in the diff
