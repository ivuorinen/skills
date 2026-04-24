---
name: skills
description: Use when the user wants to run one of the hostile audit skills in this repo, or asks what skills are available. Routes to the correct public skill based on the request.
---

# Skills Launcher

Lists and invokes the public skills in this repository.

## When to Use

- User asks "what skills are available?" or "what can you do?"
- User wants to run a review, audit, or analysis but hasn't named a specific skill
- Use as a quick reference for which skill fits the current situation

## Available Skills

| Skill | Invoke | Use when |
|-------|--------|----------|
| `adversarial-reviewer` | `/adversarial-reviewer` | Hostile bug hunt on specific code; no praise, provable failures only |
| `nitpicker` | `/nitpicker` | Exhaustive whole-repo audit across code, tests, docs, config; can apply fixes |
| `pr-reviewer` | `/pr-reviewer` | Review a PR or diff; outputs copy-paste markdown for GitHub PR comments |
| `arch-detector` | `/arch-detector` | Detect which architectural patterns the codebase uses; writes `docs/audit/arch-profile.md` |
| `arch-auditor` | `/arch-auditor` | Audit for architectural violations against detected or declared patterns |
| `doc-auditor` | `/doc-auditor` | Verify all documentation against the codebase; find stale, missing, or incorrect docs |

## Routing Guide

If the user says… → invoke this skill:

- "review this code / find bugs / tear this apart" → `/adversarial-reviewer`
- "review the whole repo / audit everything / pre-release check" → `/nitpicker`
- "review this PR / review my changes / give me a PR comment" → `/pr-reviewer`
- "what architecture is this / detect patterns" → `/arch-detector`
- "audit the architecture / find violations" → `/arch-auditor`
- "check the docs / find stale docs / verify documentation" → `/doc-auditor`

## If Unclear

Run `make list` (or `uv run scripts/list-skills.py`) to print the current skill list with full descriptions, then ask the user which one fits.
