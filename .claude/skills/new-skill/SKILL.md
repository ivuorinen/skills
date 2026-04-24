---
name: new-skill
description: Use when creating a new hostile audit skill for this repository. Scaffolds the correct directory structure, frontmatter, and required sections.
disable-model-invocation: true
---

# New Skill Scaffolder

## Steps

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

5. Add a row to the Existing Skills table in `CLAUDE.md`.

6. Add a row to the Available Skills table in `.claude/skills/skills/SKILL.md` — this is the launcher skill users invoke to discover and route to public skills. Keep it in sync.

7. Run the validator:
   ```
   uv run scripts/validate-skill.py skills/<name>/SKILL.md
   ```

8. Run `/validate-skills` to check all skills remain consistent.
