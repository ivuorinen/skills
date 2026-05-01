# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A Claude Code plugin containing hostile audit skills. Each skill lives under `skills/<name>/SKILL.md`. The repo is installable via `/plugins` and versioned with semantic versioning + release-please automation. Internal dev skills (scaffolding, validation, release) live under `.claude/skills/` and are used during development only — not shipped to plugin consumers.

## Development Commands

```bash
make check        # validate all skills + validate-rules + version sync + ruff lint + pytest (run before every commit)
make validate     # SKILL.md structure only (public + internal)
make test         # run pytest unit tests for scripts/
make list         # list all skills with descriptions
make lint         # ruff check on scripts/
make format       # ruff format on scripts/
```

## Existing Skills

Skills live in `skills/` — each subdirectory is one skill.

| Skill | Trigger description |
|-------|---------------------|
| `adversarial-reviewer` | Hostile code review; assumes bugs exist and hunts for them |
| `nitpicker` | Exhaustive repository audit; finds defects across code, tests, docs, and config; optionally applies fixes in a single run |
| `arch-detector` | Detects which architectural patterns a codebase uses; produces `docs/audit/arch-profile.md` |
| `arch-auditor` | Audits codebase for architectural violations against detected or declared patterns |
| `doc-auditor` | Verifies all documentation accuracy against the codebase; finds stale, incorrect, and missing docs |
| `pr-reviewer` | Hostile but constructive PR review; outputs copy-paste-ready markdown for GitHub PR comments |
| `security-auditor` | Audits a codebase with available security scanners, parses results, and writes a consolidated findings report |
| `cr-implementer` | Fetches GitHub PR review comments (unresolved where available via GraphQL), evaluates and implements valid ones one at a time, verifies with tests and linting, scans for similar issues, and asks user whether to leave/commit/push |
| `claude-rules-auditor` | Audits `.claude/rules/` files for quality, checks CLAUDE.md for misplaced rules, and suggests new rules from project conventions and audit artifacts |

## Skill File Format

Each skill directory contains one `SKILL.md` with YAML frontmatter — all current skills use it and new skills must too.

```yaml
---
name: skill-name
description: Use when [triggering conditions and symptoms].
---
```

The body is a prompt written in imperative Markdown — define mindset, checklist, output format, and any constraints.

**Body-only (no frontmatter)** is a legacy pattern. Skills without frontmatter cannot be auto-discovered by Claude Code from user intent. Frontmatter requirements are enforced by `.claude/rules/skill-format.md`.

## Adding a New Skill

1. Create a kebab-case directory under `skills/` (e.g., `skills/my-skill/`)
2. Add `SKILL.md` with YAML frontmatter (`name` + `description`)
3. Write the `description` per the format enforced by `.claude/rules/skill-format.md`
4. Add a row to the Existing Skills table in this file, in `README.md`, and in the "Existing Public Skills" table in `.github/copilot-instructions.md`; also update the Skill Catalogue, Mermaid graphs, and Quick Reference in `.claude/skills/README.md`
5. Use `/new-skill` — it orchestrates the full RED → GREEN → REFACTOR → adversarial-review → validate → pr-reviewer cycle.
6. Commit with `feat: add my-skill skill` (triggers a minor version bump via release-please)

## Conventions Observed in This Repo

Skill writing style, output format, and lifecycle rules are enforced by `.claude/rules/` — see `skill-format.md`, `skill-style.md`, `skill-lifecycle.md`, and `use-uv-runner.md`.

## Plugin Metadata

Plugin identity lives in `.claude-plugin/`:

| File | Purpose |
|------|---------|
| `.claude-plugin/plugin.json` | Plugin name, version, author, keywords |
| `.claude-plugin/marketplace.json` | Marketplace listing (used by `/plugins`) |

Version must be kept in sync across `package.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.release-please-manifest.json`, and `pyproject.toml`. Use `scripts/bump-version.py` for manual bumps; release-please handles it automatically on CI.

## Versioning

This repo uses [Semantic Versioning](https://semver.org/) with [release-please](https://github.com/googleapis/release-please) for automated releases.

**Commit message convention** (required for release-please to determine bump type):

| Prefix | Effect |
|--------|--------|
| `feat:` | Minor bump (new skill) |
| `fix:` | Patch bump (skill improvement or bug fix) |
| `feat!:` / `BREAKING CHANGE:` footer | Major bump |
| `chore:`, `docs:`, `refactor:` | No bump |

**Automated release flow** (CI):
1. Merge a `feat:` or `fix:` commit to `main`
2. release-please opens a Release PR with updated CHANGELOG and version
3. Merge the Release PR → GitHub Release + git tag created automatically

**Manual release flow** (local):
```bash
./scripts/bump-version.py [major|minor|patch]
# Edit CHANGELOG.md to add release notes
git add -A && git commit -m "chore: release vX.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```

## Configuration

`.claude/settings.local.json` — Claude Code local settings (tool permissions, etc.). Not shared; gitignored.

`.claude/settings.json` — Shared PostToolUse hooks that run automatically after every Write or Edit:
- `validate-skill-hook.py` — validates SKILL.md structure on any edited SKILL.md
- `validate-json-hook.py` — validates JSON syntax on any edited `.json` file
- `check-version-sync-hook.py` — warns if editing a version file causes a mismatch across the five manifests
- `ruff-hook.py` — auto-fixes and lints any edited `.py` file
- `validate-audit-findings-hook.py` — validates and autofixes `docs/audit/*-findings.md` structure (single Fixed/Invalid h2, `### Pass N — YYYY-MM-DD` h3 sub-sections) and summary counts
