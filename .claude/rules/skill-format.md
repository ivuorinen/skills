---
paths:
  - "skills/**/SKILL.md"
  - ".claude/skills/**/SKILL.md"
---

# Skill File Format

Every SKILL.md must start with YAML frontmatter containing `name` and `description` fields.
The `name` field must match the parent directory name exactly (kebab-case).
The `description` field must start with "Use when".
Never summarize the skill's workflow in the description — describe triggering conditions only.
If the description contains ": " (colon + space), wrap the entire value in single or double quotes.
Never create a skill without YAML frontmatter (body-only is a legacy pattern).
