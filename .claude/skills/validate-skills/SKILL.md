---
name: validate-skills
description: Use when verifying all skills in the repository are well-formed before a release or after adding/editing a skill.
disable-model-invocation: true
---

# Validate Skills

## Steps

1. Run the validator across all skills:
   ```bash
   uv run scripts/validate-skill.py
   ```

2. If any **errors** are reported, fix them before proceeding. Errors are blocking.

3. **Warnings** should be reviewed; fix if the skill is being released.

4. Run the version sync check:
   ```bash
   uv run scripts/check-version-sync.py
   ```

5. If all checks pass, skills are release-ready.

## What is checked

| Check | Level |
|-------|-------|
| Frontmatter present | Error |
| `name` field present | Error |
| `description` field present | Error |
| Description starts with "Use when" | Error |
| Description ≤ 500 chars | Error |
| Skill name matches directory name | Error |
| `## Overview` or `## Mindset` section | Warning |
| `## When to Use` or `## Operating Rules` section | Warning |
| Legacy output paths (`./codereview.md` etc.) | Warning |
