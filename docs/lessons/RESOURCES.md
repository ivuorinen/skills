# Nitpicker dispatch Resources

For a repo-internal topic the trusted sources are the repo's own files, not the
open web. Every claim in a lesson links back to one of these, by path, so you
can verify it against the code that actually runs.

## Knowledge

- [`skills/nitpicker/SKILL.md` — the router](../../skills/nitpicker/SKILL.md)
  The authoritative dispatch rules (the `## Dispatch` section) and the
  command↔category tables. **Use for:** first-word resolution, alias matching,
  the unknown-word fallback, and execution order.
- [`skills/nitpicker/commands/_conventions.md` — the shared binding](../../skills/nitpicker/commands/_conventions.md)
  Read first on every run, before any command file. **Use for:** what every
  command inherits — severity levels, the findings-store protocol, the `inline`
  and `changed-files` modifiers, and the generic rules.
- [`scripts/validate-skill.py` — the enforcement gate](../../scripts/validate-skill.py)
  The validator CI runs. **Use for:** what makes a command file structurally
  valid, and the 1:1 rule that every `commands/*.md` file has exactly one
  `SKILL.md` table row and vice versa.
- [`.claude/rules/skill-format.md` — command-file shape](../../.claude/rules/skill-format.md)
  **Use for:** the h1 format, the required `## When to use` section, and the
  no-frontmatter rule for command files.
- [`.claude/skills/new-command/SKILL.md` — the scaffolder](../../.claude/skills/new-command/SKILL.md)
  **Use for:** the full lifecycle of adding a command (the path an extension
  actually travels).

## Wisdom (Communities)

A repo-internal topic has no external community. The equivalent feedback loop is
**dogfooding**: run a real `/nitpicker <command>` invocation and watch it
resolve, and run `/nitpicker review` on a command file you change. That is where
routing knowledge gets tested against reality.

## Gaps

- No worked example yet of an invocation that resolves via an *alias* rather
  than a canonical name — a good candidate for lesson 0002.
