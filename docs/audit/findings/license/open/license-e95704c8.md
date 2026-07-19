---
id: license-e95704c8
auditor: license
severity: high
category: docs
area: NOTICE:1
status: open
found: 2026-07-19
---

# Vendored graphify has been redistributed on main since a7aa066 without its MIT copyright and permission notice

## Problem

a7aa066 added 1,278 lines of third-party graphify content with no LICENSE and no NOTICE. Both files exist only as untracked working-tree additions today, so every commit from a7aa066 through HEAD redistributes MIT-licensed work without the notice MIT requires be carried in all copies.

## Evidence

`git show --stat a7aa066` lists .claude/skills/graphify/SKILL.md | 678 +++++ and references/*.md - no LICENSE entry. `git status --porcelain` -> `?? .claude/skills/graphify/LICENSE`, `?? NOTICE`. vendored-skills.md:57 requires "Both exist before the skill's name goes on VENDORED_SKILLS" - but a7aa066 added the allowlist entry in the same commit, with neither file present. vendored-skills.md:59 names test_vendored_skills_carry_a_license as the enforcer; a7aa066 added only the allowlist-pinning test, so the LICENSE assertion did not gate that commit.

## Impact

A license-compliance defect on the default branch for five commits. The rule meant to prevent it shipped in the same commit as the violation. The test also passes locally only because the working tree has an untracked file - actions/checkout produces a tree without it, so the Validate gate breaks on push.

## Fix

Commit NOTICE and .claude/skills/graphify/LICENSE before anything else on this branch. Verify test_vendored_skills_carry_a_license is collected (`pytest tests/test_validate_skill.py -k vendored`).
