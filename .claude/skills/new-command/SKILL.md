---
name: new-command
description: Use when creating a new hostile audit command for the nitpicker skill in this repository.
disable-model-invocation: true
---

# New Command Scaffolder

Creates a public command under `skills/nitpicker/commands/<name>.md` and
stress-tests it through the full RED → GREEN → REFACTOR → adversarial-review
→ validate cycle before declaring it done.

## Phase 1 — TDD Baseline (RED)

Before writing a single line of command content, run `/skill-tester` to
establish the baseline. Use its checklist to have a subagent run **without**
the new command loaded and record every rationalization the agent uses to
skip the rule you are encoding. Document those rationalizations — every one
must be countered in the command body.

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

4. Counter every RED-phase rationalization explicitly in the command body.
   Use "rationalization" (US spelling) consistently.

## Phase 3 — Verify Behaviour (GREEN)

Run `/skill-tester` again with the command loaded (`/nitpicker <name>`).
Confirm the agent complies with every rule. If the agent finds a new
loophole, add an explicit counter and re-run until no loopholes remain.

## Phase 4 — Refactor

- Remove hedging language ("might", "could", "potential") — every statement
  must be unconditional.
- Tighten rule wording so each rule can be tested by a single scenario.
- Consolidate duplicate or overlapping rules; anything generic moves to
  `_conventions.md` (only if it truly binds every command).
- Re-run `/skill-tester` after refactoring — all GREEN scenarios must pass.

## Phase 5 — Adversarial Review

Run `/nitpicker review` against the new command file. Treat the command body
as code under review — hunt ambiguous rules, missing edge-case coverage,
hedged language, instructions that permit rationalization. Fix every HIGH or
CRITICAL finding and re-run until none remain.

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

1. Run `/validate-skills` to confirm everything remains consistent.

## Phase 7 — PR Review

Run `/nitpicker pr` on the staged diff. Fix all findings at HIGH or above,
re-running until clean. Commit with `feat: add /nitpicker <name> command` —
this triggers a minor version bump.

## Command Quality Gate

A command is **not done** until all of these pass:

- [ ] skill-tester GREEN phase: agent complies with every rule
- [ ] skill-tester REFACTOR verify: no new loopholes after refactoring
- [ ] `/nitpicker review`: no HIGH or CRITICAL findings remain
- [ ] `uv run scripts/validate-skill.py skills/nitpicker/SKILL.md` exits 0
- [ ] `/validate-skills` exits clean
- [ ] `/nitpicker pr`: no HIGH or CRITICAL findings in the diff
