---
name: validate-skills
description: Validates every SKILL.md and command file in this repository against the Agent Skills specification and the repo's own conventions, reporting structural errors before they reach CI. Use when verifying skills are well-formed — before a release, after adding or editing a skill, or when a skill-validation gate fails.
---

# Validate Skills

## Steps

1. Run the validator across all skills — public and internal:

   ```bash
   uv run scripts/validate-skill.py
   uv run scripts/validate-skill.py .claude/skills/*/SKILL.md
   ```

   To validate only public skills:

   ```bash
   uv run scripts/validate-skill.py
   ```

   To validate only internal skills:

   ```bash
   uv run scripts/validate-skill.py .claude/skills/*/SKILL.md
   ```

2. If any **errors** are reported, fix them before proceeding. Errors are blocking.

3. **Warnings** should be reviewed; fix if the skill is being released.

4. Run the version sync check:

   ```bash
   uv run scripts/check-version-sync.py
   ```

5. If all checks pass, skills are release-ready.

## What is checked

| Check                                                                                                              | Level   |
| ------------------------------------------------------------------------------------------------------------------ | ------- |
| Frontmatter present                                                                                                | Error   |
| `name` field present                                                                                               | Error   |
| `description` field present                                                                                        | Error   |
| Description contains "Use when" trigger clause                                                                     | Error   |
| Description ≤ 1024 chars                                                                                           | Error   |
| Skill name matches directory name                                                                                  | Error   |
| `name` ≤ 64 chars, lowercase letters, digits and hyphens only                                                      | Error   |
| `name` has no leading, trailing, or consecutive hyphen                                                             | Error   |
| `name` contains no reserved word ("anthropic", "claude")                                                           | Error   |
| `compatibility` is non-empty and ≤ 500 chars when present                                                          | Error   |
| `metadata` is a mapping of string keys to string values                                                            | Error   |
| `allowed-tools` is one space-separated string, not a list                                                          | Error   |
| Header level progression (no skipping levels)                                                                      | Error   |
| Description with `': '` must be single-quoted                                                                      | Error   |
| Command tables (`## Commands`, `## Internal commands`) ↔ `commands/*.md` files 1:1 (skills with a `commands/` dir) | Error   |
| Duplicate headers within a SKILL.md body                                                                           | Error   |
| Unterminated code fence                                                                                            | Error   |
| Shared `commands/_*.md` reference is named in SKILL.md (no two-level chain)                                        | Error   |
| Command file h1 is `# /<skill> <command> — …`                                                                      | Error   |
| Command file has `## When to use`                                                                                  | Error   |
| Command file has no YAML frontmatter                                                                               | Error   |
| Command file header level progression                                                                              | Error   |
| Frontmatter key outside the Agent Skills spec (use `metadata`)                                                     | Error   |
| Legacy output paths (`./codereview.md` etc.)                                                                       | Warning |
| Body exceeds 500 lines                                                                                             | Warning |
| Body exceeds ~5000 tokens (progressive-disclosure tier)                                                            | Warning |

Constraints come from the Agent Skills specification
(<https://agentskills.io/specification>) plus this repo's stricter conventions;
`.claude/rules/skill-official-best-practices.md` records which is which.

Vendored skills (`VENDORED_SKILLS` in `scripts/validate-skill.py`) are skipped
and print a `SKIP` line rather than passing silently.

## Cross-checking against the reference validator

`make spec-check` runs the Agent Skills reference implementation over every
skill. It needs network access, so it is not part of `make check`;
`validate-skill.py` enforces the same constraints offline.

Every skill in the repo passes it, internal dev skills included. Two traps when
reading its output: failures go to **stderr** and successes to stdout, so a
stdout-only read looks clean while skills fail; and the PyPI package is
`skills-ref` while its console script is `agentskills`. Confirm the validator
still rejects a known-bad skill before trusting a clean run.
