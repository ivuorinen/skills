# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A Claude Code plugin containing hostile audit skills. Each skill lives under `skills/<name>/SKILL.md`. The repo is installable via `/plugins` and versioned with semantic versioning + release-please automation.

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
| `security-auditor` | Runs available security tools (grype, trivy, gitleaks, checkov, gosec, snyk, semgrep), parses results, and writes a consolidated findings report |

## Skill File Format

Each skill directory contains one `SKILL.md` with YAML frontmatter — all current skills use it and new skills must too.

```yaml
---
name: skill-name
description: Use when [triggering conditions and symptoms].
---
```

The body is a prompt written in imperative Markdown — define mindset, checklist, output format, and any constraints.

**Body-only (no frontmatter)** is a legacy pattern; avoid it. Skills without frontmatter cannot be auto-discovered by Claude Code from user intent.

### Description authoring rules

1. Start with "Use when..." — describe triggering conditions, not what the skill does
2. Write in third person — the description is injected into the system prompt
3. Never summarize the skill's workflow — if the description contains a workflow summary, Claude may follow it instead of reading the full skill body

## Adding a New Skill

1. Create a kebab-case directory under `skills/` (e.g., `skills/my-skill/`)
2. Add `SKILL.md` with YAML frontmatter (`name` + `description`)
3. Write the `description` following the three rules above
4. Add a row to the Existing Skills table in this file
5. Commit with `feat: add my-skill skill` (triggers a minor version bump via release-please)

## Conventions Observed in This Repo

- Skills are written as hostile/deterministic agents (no hedging, no "potential issue" language)
- Output destinations are explicit (`docs/audit/<skill>-findings.md`, inline, etc.)
- Severity levels and checklists are enumerated, not left to interpretation
- Silence = approval: if something isn't flagged, it is implicitly accepted

## Plugin Metadata

Plugin identity lives in `.claude-plugin/`:

| File | Purpose |
|------|---------|
| `.claude-plugin/plugin.json` | Plugin name, version, author, keywords |
| `.claude-plugin/marketplace.json` | Marketplace listing (used by `/plugins`) |

Version must be kept in sync across `package.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `.release-please-manifest.json`. Use `scripts/bump-version.py` for manual bumps; release-please handles it automatically on CI.

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
