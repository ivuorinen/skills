# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A Claude Code plugin containing hostile audit and enforcement skills. Each skill lives under `skills/<name>/SKILL.md`. The repo is installable via `/plugins` and versioned with semantic versioning + release-please automation. Internal dev skills (scaffolding, validation, release) live under `.claude/skills/` and are used during development only — not shipped to plugin consumers.

## Development Commands

```bash
make check        # validate all skills + validate-rules + version sync + audit-consistency + ruff lint + ruff format check + pytest (run before every commit)
make validate     # SKILL.md structure only (public + internal)
make test         # run pytest unit tests for scripts/
make list         # list all skills with descriptions
make lint         # ruff check on scripts/, tests/, skills/
make format       # ruff format on scripts/, tests/, skills/
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
| `loophole-hunter` | Audits the Claude Code enforcement surface (`.claude/rules/`, hooks, `.claude/settings.json`, permissions, skills) for bypassable or unenforced constraints and closes them; invoked by `nitpicker` in `loophole` mode and by `release-prep` as a gate |
| `hooks-enforcer` | Audits an agent project's hook *coverage* against its evidence base (current hooks, audit-findings history, git history, project memory); finds recurring failures no hook guards and context-discipline gaps where large-output work bypasses a context-saving tool; specifies and wires the missing hooks in the host harness's correct shape; invoked by `nitpicker` in `loophole` mode and by `release-prep` as a gate |
| `complexity-hunter` | Forces the laziest solution that actually works on every coding task — reuse-first ladder (YAGNI, codebase, stdlib, platform, installed dependency, one line) before new code; sticky on every coding response once invoked; also audits a diff or whole repo for over-engineering with tagged, ranked findings; never simplifies away trust-boundary validation, data-loss error handling, security, or accessibility |
| `perf-auditor` | Hostile single-shot performance audit; hunts N+1 queries, O(n²)+ hotspots on real data paths, sync-blocking calls in async contexts, unbounded caches/queues/retries, missing pagination, loop-invariant work redone per iteration, and chatty per-item I/O; every finding names the code path, the growth driver, and a concrete fix — no speculation; uses installed measurement tools, never adds a dependency; receives performance findings routed from `complexity-hunter`; invoked by `nitpicker` in `perf` mode and by `release-prep` as a gate |
| `test-auditor` | Hostile audit of the test suite itself; assumes the tests are weaker than they look and proves it — assertion-free and tautological tests, mocks of the unit under test, over-mocking that severs the code path, flaky patterns, untracked skips, coverage holes on money/security/data-loss paths, and mutation-blind spots; fixes add or strengthen tests only, never production source; invoked by `nitpicker` in `tests` mode and by `release-prep` as a gate |
| `dep-auditor` | Hostile audit of dependency health beyond CVEs — unused, phantom, duplicate, heavyweight, unmaintained, license-conflicting, drifted, and misclassified dependencies; cross-references manifest, lockfile, and a full import/usage scan; uses installed tools only (depcheck, deptry, npm ls, pip list, cargo tree), never installs anything; CVEs route to `security-auditor`, new-dependency decisions to `complexity-hunter`; invoked by `nitpicker` in `deps` mode and by `release-prep` as a gate |
| `silent-failure-hunter` | Hostile audit of application error handling; assumes failures are being swallowed and proves where — swallowed exceptions, fail-open defaults, overbroad catches, ignored error signals, masking fallbacks, silent retries, cause-destroying rethrows; on approval fixes the error path only, never the happy path; invoked by `nitpicker` in `errors` mode and by `release-prep` as a gate |
| `ci-auditor` | Hostile single-shot audit of CI/CD pipeline definitions (GitHub Actions first-class; GitLab CI and other YAML pipelines by the same principles); finds unpinned actions, over-broad token permissions, script injection via untrusted interpolation, privileged-trigger misuse, secrets leakage, non-gating checks, masked failures, missing concurrency, cache poisoning, and self-hosted runner exposure; uses actionlint/zizmor when installed and verifies gating via `gh api` when authenticated; invoked by `nitpicker` in `ci` mode and by `release-prep` as a gate |
| `commit-auditor` | Hostile single-shot audit of commit-message discipline against the actual diffs; finds type-understatement (a `chore:`/`docs:` diff that ships behavior unreleased), type-overstatement (a `feat:` on a pure fix), unmarked and spurious breaking changes, squash-title scope-lies, and malformed convention; every finding cites the SHA, quoted message, contradicting hunks, and the version consequence release-please takes vs the bump the diff earns; amends unpushed messages on approval, never rewrites pushed history — proposes `Release-As`/corrected-footer correction commits instead; invoked by `nitpicker` in `commits` mode and by `release-prep` as a gate |
| `migration-auditor` | Hostile single-shot audit of database schema and data migrations; assumes every migration eats production until proven safe — destructive ops with no rollout story, irreversible downs, long-lock operations (engine-specific safe forms named), missing FK indexes, schema-model drift, unbatched data migrations, deploy-order breaks under rolling deploys, and duplicate migration versions; static analysis only, never runs a migration; never edits an applied migration — its fix is a new migration; SQL injection routes to `security-auditor`, query performance to `perf-auditor`; invoked by `nitpicker` in `migrations` mode and by `release-prep` as a gate |
| `observability-auditor` | Hostile single-shot audit of the signal surface a codebase emits; assumes production failures are invisible until logs, metrics, traces, and alerts prove otherwise — dark paths, missing correlation IDs, level misuse, unfireable alerts, cardinality bombs, PII in logs, silent jobs, context-free errors; cross-checks in-repo alert configs against emitted metrics; on approval fixes add or correct emissions only, never business logic; invoked by `nitpicker` in `observability` mode and by `release-prep` as a gate |
| `api-contract-auditor` | Hostile single-shot audit of the declared public contract surface (OpenAPI/Swagger and GraphQL specs, package exports, published types, documented CLI flags) against the implementation, and of every surface change since the last release tag against the semver bump the commits declare; every finding names the declared element, the implementation, the mismatch, and the consumer-visible consequence; spec edits and code edits are separate per-finding approvals — which side is right is the user's call; pairs with `commit-auditor` (label vs diff) by checking the surface against the label; invoked by `nitpicker` in `contract` mode and by `release-prep` as a gate |
| `a11y-auditor` | Hostile single-shot accessibility audit of the codebase's UI layer against WCAG 2.2 AA; assumes the interface is unusable without a mouse and screen until the code proves otherwise — missing alternatives, unlabeled controls, keyboard-unreachable handlers, focus loss, ARIA misuse, contrast violations computed from design tokens with the math shown, structure breaks, and motion hazards; runs axe-core/eslint-plugin-jsx-a11y/pa11y when installed, never installs anything; a repo with no UI surface gets the explicit verdict "no auditable UI surface"; verifies the accessibility floor `complexity-hunter` never simplifies away; invoked by `nitpicker` in `a11y` mode and by `release-prep` as a gate |

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
4. Add a row to the Existing Skills table in this file, in `README.md`, and in the "Existing Public Skills" table in `.github/copilot-instructions.md`; add it to the Available Skills table and Routing Guide in `.claude/skills/skills/SKILL.md`; also update the Skill Catalogue, Mermaid graphs, and Quick Reference in `.claude/skills/README.md`
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
