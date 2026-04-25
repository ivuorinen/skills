---
name: new-skill
description: Use when creating a new hostile audit skill for this repository. Scaffolds the correct directory structure, frontmatter, and required sections.
disable-model-invocation: true
---

# New Skill Scaffolder

Creates a public skill under `skills/<name>/` and stress-tests it through the full
RED → GREEN → REFACTOR → adversarial-review → validate cycle before declaring it
done.

## Phase 1 — TDD Baseline (RED)

Before writing a single line of skill content, run `/skill-tester` to establish the
baseline. The skill-tester dispatches a subagent **without** the new skill loaded and
records every rationalization the agent uses to skip the rule you are encoding.
Document those rationalizations — every one must be countered in the skill body.

## Phase 2 — Scaffold

1. Choose a kebab-case name (e.g. `dep-auditor`).

2. Create the directory and file:
   ```
   skills/<name>/SKILL.md
   ```

3. Write the frontmatter:
   ```yaml
   ---
   name: <name>
   description: Use when <specific triggering conditions — no workflow summary, ≤500 chars>
   ---
   ```

4. Required sections (in order):
   - `## Overview` — one paragraph: what it does, hostile framing, single-shot behaviour
   - `## When to Use` — bullet list of triggering conditions and situations
   - `## Process` — numbered steps (find → ask → fix → re-validate)
   - `## Output Format` — findings grouped by severity: Critical / High / Medium / Low / Advisory; Fixed section at bottom; output path `docs/audit/<name>-findings.md`
   - `## Fix Strategy` — what may be auto-applied, what requires user approval
   - `## Common Mistakes` — what the skill must NOT do

5. Counter every RED-phase rationalization explicitly in the skill body — add a rule or
   a Common Mistakes entry for each one. "Rationalisation" and "rationalization" refer
   to the same thing; use "rationalization" (US spelling) consistently throughout.

## Phase 3 — Verify Behaviour (GREEN)

Run `/skill-tester` again, this time with the skill loaded. Confirm the agent
complies with every rule. If the agent finds a new loophole, add an explicit counter
and re-run until no loopholes remain.

## Phase 4 — Refactor

With the GREEN phase clean, refactor the skill body for clarity and hostile
precision:

- Remove hedging language ("might", "could", "potential") — every statement must be
  unconditional
- Tighten rule wording so each rule can be tested by a single scenario
- Consolidate duplicate or overlapping rules
- Ensure the Common Mistakes section names the exact rationalizations captured in the
  RED phase
- Re-run `/skill-tester` after refactoring to confirm no regression — all GREEN
  scenarios must still pass

## Phase 5 — Adversarial Review

Run `/adversarial-reviewer` against the new `skills/<name>/SKILL.md` file. Treat the
skill body as code under review — hunt for ambiguous rules, missing edge-case
coverage, hedged language, and instructions that permit rationalization. Fix every
HIGH or CRITICAL finding. Re-run until adversarial-reviewer reports no findings at
HIGH or above.

## Phase 6 — Structural Validation

6. Add a row to the Existing Skills table in `CLAUDE.md`.

7. Add a row to the Available Skills table in `.claude/skills/skills/SKILL.md` — this is the launcher skill users invoke to discover and route to public skills. Keep it in sync.

8. Add a row to the "Existing Public Skills" table in `.github/copilot-instructions.md`.
   If `README.md` contains a mirrored skills table, update it too.

9. Add a row to the Skill Catalogue table and all relevant Mermaid diagrams in
   `.claude/skills/README.md` (the wiring guide). Update the Quick Reference
   Input/Output table and the New Skill Registration Checklist as needed.

10. Run the validator:
    ```
    uv run scripts/validate-skill.py skills/<name>/SKILL.md
    ```

11. Run `/validate-skills` to confirm all skills remain consistent.

## Phase 7 — PR Review

12. Run `/pr-reviewer` on the staged diff. Fix all findings at HIGH or above.
    Re-run until pr-reviewer reports no findings at HIGH or above.

13. Commit with `feat: add <name> skill` — this triggers a minor version bump.

## Skill Quality Gate

A skill is **not done** until all of these pass:

- [ ] skill-tester GREEN phase: agent complies with every rule
- [ ] adversarial-reviewer: no HIGH or CRITICAL findings remain
- [ ] `uv run scripts/validate-skill.py skills/<name>/SKILL.md` exits 0 with no errors
- [ ] `/validate-skills` exits clean
- [ ] pr-reviewer: no HIGH or CRITICAL findings in the diff
