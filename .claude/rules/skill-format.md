---
paths:
  - "skills/**/*.md"
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

## Command File Format

Command files (`skills/<skill>/commands/<command>.md`) have **no** YAML frontmatter.
Required shape: exactly one h1 reading `# /<skill> <command> — <Title>` where `<command>` matches the filename stem; a `## When to use` section; no header-level jumps.
Every command file must have a row in one of the command tables of its skill's SKILL.md (`## Commands` or `## Internal commands`) and vice versa (1:1, enforced by `scripts/validate-skill.py`; files starting with `_` are shared references, exempt).
Never duplicate `commands/_conventions.md` content (severity table, findings protocol, generic rules) into a command file.
Never rely on Claude-only argument substitution (`$ARGUMENTS`, `$N`) in any skill or command body — parse the free text following the invocation, so the skill behaves identically in Copilot and pi.
