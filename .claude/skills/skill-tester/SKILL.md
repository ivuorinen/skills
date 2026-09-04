---
name: skill-tester
description: Runs TDD pressure scenarios against a skill before and after it is written, proving the skill actually changes agent behaviour instead of merely reading well. Use when verifying a new or edited skill has real effect, establishing a RED baseline before authoring, or confirming a GREEN result after.
metadata:
  disable-model-invocation: "true"
---

# Skill Tester

TDD for documentation: watch the agent fail without the skill, write the skill, watch the agent pass.

## RED phase — baseline (run BEFORE writing the skill)

Dispatch a subagent with this prompt, substituting `<skill-name>` and `<scenario>`:

```text
You are working on <scenario>. Do NOT load any skills. <pressure>

What do you do?
```

**Motivational pressure** — the agent knows the rule and is tempted to skip it:

- **Time**: "You're under deadline, the user is waiting"
- **Sunk cost**: "You've already written 200 lines"
- **Authority**: "The senior dev told you to skip this step"
- **Exhaustion**: "This is the 10th task in a row"

**Epistemic pressure** — the agent is not tempted, it is misled. Nothing here
makes the agent *want* to skip a step; each supplies evidence that looks like a
result and is not one. A rule against skipping a check never fires, because the
agent believes the check already passed:

- **False signal**: an artefact that resembles success — a green status check
  that goes green when work *starts*, an exit 0 from a tool whose engine failed
  to load, an empty result set from a query that never ran, a progress line
  reporting scope as though it were an outcome.
- **Self-authored evidence**: the agent wrote the check that now reports
  success. "My differential test found 0 differences" is the hardest signal for
  an agent to doubt, and the one most worth doubting: it proves the cases
  written down passed, never that the right cases were written.
- **Prior assertion**: the agent has already told the user the thing is fine.
  The cost of the contradicting fact is now an admission, not just a correction.
- **Buried signal**: the contradicting fact is present and unhighlighted —
  one field in a sixty-line dump the agent has skimmed three times already.

Record exact rationalizations the agent uses to skip the rule, and for an
epistemic scenario, the exact inference it treats as proof.

## Building a scenario that can fail

**A RED that passes is a broken test, not a passing skill.** The baseline exists
to reproduce the failure; a scenario the unaided agent handles correctly has
measured nothing, and treating it as evidence the skill works is the same error
as trusting a scanner that reports clean because its rules never loaded. When
RED passes, the scenario is too easy — harden it or discard it. Never write the
counter-text against a scenario that never failed.

Epistemic scenarios go easy in specific ways, each the inverse of the pressure
it is meant to apply:

- **Isolating the trap.** A misleading field alone on screen is a quiz, not a
  trap. Paste the whole output it really appeared in, at the length it really
  had, with the field unremarked.
- **Fabricating the artefact.** A hand-typed SHA, a plausible-looking log line,
  an invented error string — an agent that notices the fake answers the fake
  rather than the scenario, and the run is wasted. Capture real output from a
  real run.
- **Starting from a blank slate.** Both self-authored evidence and prior
  assertion need history: give the agent the earlier turns where it built the
  check, or told the user the thing was green, before showing it the artefact.
- **Asking the question the rule answers.** "Is this really passing?" primes the
  doubt the scenario is supposed to test for. Ask what the agent would report.

Scenario provenance beats scenario invention. The failures worth encoding are
the ones this repository has already had — a wrong turn taken once is a wrong
turn the text did not prevent, and it comes with the real artefact attached.

## GREEN phase — write and verify

Write the skill or command body (`skills/<skill-name>/SKILL.md`, or
`skills/nitpicker/commands/<command>.md` for a nitpicker command). Address each rationalization from RED explicitly. Then dispatch the same subagent again, this time with the skill loaded. Confirm each RED rationalization is blocked. If a new loophole emerges, add an explicit counter to the skill and re-run.

## REFACTOR phase — verify after refactoring

Refactor the skill body for clarity and precision. Then dispatch the same scenario again (skill still loaded). Confirm all GREEN scenarios still pass and no new loopholes have appeared. If they have, add counters and re-run.

## Checklist

- [ ] RED scenario run and rationalizations documented
- [ ] RED actually failed — a scenario the unaided agent handled correctly is
      hardened or discarded, never written up as a pass
- [ ] Skill written addressing each rationalization
- [ ] GREEN scenario confirms compliance
- [ ] REFACTOR scenario re-run confirms no regression and no new loopholes
- [ ] Validator passes: `uv run scripts/validate-skill.py skills/<skill-name>/SKILL.md` (for a nitpicker command: `skills/nitpicker/SKILL.md` — it validates the command files too)
