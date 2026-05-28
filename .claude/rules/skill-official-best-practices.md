---
paths:
  - "skills/**/SKILL.md"
  - ".claude/skills/**/SKILL.md"
---

# Skill Official Best Practices

Rules derived from the official Anthropic skill authoring best-practices:
https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices

## Name Constraints

- Maximum 64 characters.
- Only lowercase letters, numbers, and hyphens.
- Cannot contain reserved words: "anthropic" or "claude".

## Description Format

Description must include **both** a capability summary and trigger conditions:

```yaml
description: <Capability summary sentence>. Use when <trigger conditions>.
```

Good example:
```yaml
description: Generates descriptive commit messages by analyzing git diffs. Use when asked to write commit messages or review staged changes.
```

Bad (trigger-only, no capability context):
```yaml
description: Use when asked to write commit messages or review staged changes.
```

Bad (vague, no trigger):
```yaml
description: Helps with git.
```

## Body Length

Keep SKILL.md body under 500 lines for optimal performance.
If body exceeds 500 lines, split content into separate files using progressive disclosure (link from SKILL.md).

## File Reference Depth

All reference files must link directly from SKILL.md (one level deep).
Never chain references: SKILL.md → advanced.md → details.md is forbidden.

## No Time-Sensitive Content

Do not embed specific dates, version numbers, or other time-sensitive data directly in skill instructions.
Use "current version", "latest release", or point to a file that contains the up-to-date value instead.

## Context Window Courtesy

The context window is a shared resource. Keep SKILL.md concise.
Verbose skills degrade all Claude responses in the same session.
Move large reference materials, API docs, and examples into separate files.
