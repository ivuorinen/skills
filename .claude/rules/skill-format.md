---
paths:
  - "skills/**/SKILL.md"
  - ".claude/skills/**/SKILL.md"
---

# Skill File Format

Every SKILL.md must start with YAML frontmatter containing `name` and `description` fields.
The `name` field must match the parent directory name exactly (kebab-case).
The `description` field must contain "Use when" (the trigger clause).
Description should open with a brief capability summary, then the "Use when" trigger clause:
`<Capability summary>. Use when <trigger conditions>.`
Never describe internal workflow steps in the description — capability summary only, then trigger conditions.
If the description contains ": " (colon + space), wrap the entire value in single quotes.
Never create a skill without YAML frontmatter (body-only is a legacy pattern).
