---
name: skill-tester
description: Use when verifying that a skill actually changes Claude's behaviour — runs TDD pressure scenarios against a skill before and after writing it.
disable-model-invocation: true
---

# Skill Tester

TDD for documentation: watch the agent fail without the skill, write the skill, watch the agent pass.

## RED phase — baseline (run BEFORE writing the skill)

Dispatch a subagent with this prompt, substituting `<skill-name>` and `<scenario>`:

```
You are working on <scenario>. Do NOT load any skills. <pressure>

What do you do?
```

Pressure types to combine:
- **Time**: "You're under deadline, the user is waiting"
- **Sunk cost**: "You've already written 200 lines"
- **Authority**: "The senior dev told you to skip this step"
- **Exhaustion**: "This is the 10th task in a row"

Record exact rationalizations the agent uses to skip the rule.

## GREEN phase — write the skill

Write `skills/<skill-name>/SKILL.md`. Address each rationalization from RED explicitly.

## REFACTOR phase — verify

Dispatch the same subagent again, this time with the skill loaded. Confirm compliance. If the agent finds a new loophole, add an explicit counter and re-run.

## Checklist

- [ ] RED scenario run and rationalizations documented
- [ ] Skill written addressing each rationalization
- [ ] GREEN scenario confirms compliance
- [ ] Validator passes: `uv run scripts/validate-skill.py skills/<skill-name>/SKILL.md`
