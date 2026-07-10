---
paths:
  - "skills/**/*.md"
  - ".claude/skills/**/SKILL.md"
---

# Skill Lifecycle

When creating a new nitpicker command (or a new skill) with `/new-command`, complete every phase in sequence.
Never skip any phase: RED (skill-tester baseline) → scaffold → GREEN (skill-tester verify) → REFACTOR → `/nitpicker review` → validate-skills → `/nitpicker pr` → commit.
