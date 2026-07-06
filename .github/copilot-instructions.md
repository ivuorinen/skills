# Copilot Cloud Agent Instructions

## What This Repository Is

A **Claude Code plugin** (`ivuorinen-skills`) containing hostile audit and enforcement skills. Each skill is a self-contained
prompt file (`SKILL.md`) that Claude Code loads when a user invokes it. The repo is installable via `/plugins`
and is versioned with semantic versioning using release-please automation.

## Repository Layout

```
skills/                    # Public skills (shipped with the plugin)
  <skill-name>/
    SKILL.md               # Skill definition (YAML frontmatter + prompt body)
    <tool>.py              # (optional) bundled executable script for the skill
.claude/
  skills/                  # Internal/dev skills (used during development only)
    <skill-name>/
      SKILL.md
  agents/                  # Claude Code sub-agent definitions — do NOT read or modify
  settings.json            # Claude Code project settings / shared hooks
.claude-plugin/
  plugin.json              # Plugin identity + version
  marketplace.json         # Marketplace listing
scripts/
  validate-skill.py        # Validates public skill `SKILL.md` files by default (run via `make validate`)
  check-version-sync.py    # Verifies version is in sync across all manifests
  bump-version.py          # Manual version bump utility
  list-skills.py           # Lists all skills with their descriptions
  common.py                # Shared helpers for scripts
.github/
  workflows/
    validate-skills.yml    # CI: validates skills + version sync; triggers on SKILL.md files, version files, and validation scripts
    release-please.yml     # CI: automated releases from main
docs/
  audit/                   # Output directory for skill findings (auto-created by skills)
CLAUDE.md                  # Primary guidance document — read this first on any task
README.md                  # Public-facing documentation
package.json               # npm manifest — holds the canonical version
pyproject.toml             # Python project config (uv/ruff)
Makefile                   # Developer workflow commands
```

## Skill File Format — Non-Negotiable Rules

Every `SKILL.md` **must** start with YAML frontmatter:

```yaml
---
name: skill-name
description: '<Capability summary sentence>. Use when <triggering conditions>.'
---
```

Validation checks and repository guidance from `scripts/validate-skill.py` (and CI):

- `name` must match the **directory name exactly** (kebab-case)
- `description` must contain `"Use when"` (trigger clause); recommended format: `"<capability summary>. Use when <trigger conditions>."`
- `description` must be ≤ 1024 characters
- Header levels in the body must not skip (e.g., h2 → h4 is an error)
- Do not reference legacy output paths (`codereview.md`, `fixreport.md`) — use `docs/audit/`
  instead; `scripts/validate-skill.py` currently warns on these references

Body-only (no frontmatter) is a **legacy pattern** — never create new skills without frontmatter.

## Existing Public Skills

| Skill | Directory |
|-------|-----------|
| Adversarial code reviewer | `skills/adversarial-reviewer/` |
| Exhaustive repository audit + auto-fix | `skills/nitpicker/` |
| Architecture pattern detection | `skills/arch-detector/` |
| Architecture violation auditor | `skills/arch-auditor/` |
| Documentation accuracy auditor | `skills/doc-auditor/` |
| PR review (stdout only, no findings file) | `skills/pr-reviewer/` |
| Security audit with available local scanners | `skills/security-auditor/` |
| GitHub PR review comment implementer | `skills/cr-implementer/` |
| Claude rules and CLAUDE.md rule-placement auditor | `skills/claude-rules-auditor/` |
| Claude Code enforcement-surface loophole hunter | `skills/loophole-hunter/` |
| Agent hook-coverage enforcer (evidence-driven) | `skills/hooks-enforcer/` |
| Anti-over-engineering enforcement (lazy-senior mode) | `skills/complexity-hunter/` |
| Performance audit (growth-driver evidence) | `skills/perf-auditor/` |
| Test-suite weakness auditor (tests only, never production source) | `skills/test-auditor/` |
| Dependency health auditor (beyond CVEs) | `skills/dep-auditor/` |
| Silent-failure and error-handling auditor | `skills/silent-failure-hunter/` |
| CI/CD pipeline-definition auditor (GitHub Actions first-class) | `skills/ci-auditor/` |
| Commit-message-vs-diff discipline auditor (release-please truth) | `skills/commit-auditor/` |
| Database schema/data migration auditor (static, never runs migrations) | `skills/migration-auditor/` |
| Observability / signal-surface auditor (logs, metrics, traces, alerts) | `skills/observability-auditor/` |
| Public contract-surface auditor (spec vs implementation, surface vs semver) | `skills/api-contract-auditor/` |
| Accessibility auditor (WCAG 2.2 AA, UI layer) | `skills/a11y-auditor/` |
| Concurrency safety auditor (races, deadlocks, atomicity) | `skills/concurrency-auditor/` |

## Adding a New Skill

1. Create `skills/<kebab-case-name>/SKILL.md` with valid frontmatter
2. Add a row to the skills table in `CLAUDE.md` and the "Existing Public Skills" table in
   `.github/copilot-instructions.md` (these are the source of truth for the public skill list).
   Also update `README.md` (it always contains a mirrored skills table), the Available Skills
   table + Routing Guide in `.claude/skills/skills/SKILL.md`, and the Skill Catalogue, Mermaid
   graphs, and Quick Reference in `.claude/skills/README.md`.
3. Run `/new-skill` — it orchestrates the full RED → GREEN → REFACTOR → adversarial-review → validate → pr-reviewer cycle. Do not skip this; it enforces the TDD baseline and rationalization protection.
4. Commit with `feat: add <name> skill` — this triggers a **minor** version bump via release-please

## Validation — Run Before Every Commit

```bash
make check          # validate + validate-rules + version-sync + audit-consistency + lint + format-check + pytest (all must pass)
make validate       # SKILL.md frontmatter + structure only
make validate-rules # validate .claude/rules/ files (structure + path freshness)
make test           # run pytest unit tests for scripts/
make version-sync   # version consistency across manifests
make lint           # ruff check on scripts/, tests/, skills/
make list           # print all skills with descriptions
```

CI runs six steps on every push/PR that touches a relevant path: validate-skill (twice — public and internal
skills), validate-rules, check-version-sync, `pytest tests/`, `ruff check scripts/ tests/ skills/`, and
`ruff format --check scripts/ tests/ skills/`. Trigger paths include `skills/**/SKILL.md`,
`skills/**/*.py`, `.claude/skills/**/SKILL.md`, `scripts/**`, `tests/**`, `.claude/rules/**`, and all
five version manifest files.

## Versioning — Five Files Must Stay in Sync

The canonical version lives in `package.json`. All five must match:

| File | Field |
|------|-------|
| `package.json` | `"version"` |
| `.claude-plugin/plugin.json` | `"version"` |
| `.claude-plugin/marketplace.json` | `"plugins[0].version"` |
| `.release-please-manifest.json` | `"."` |
| `pyproject.toml` | `project.version` |

Use `scripts/bump-version.py [major|minor|patch]` for manual bumps — it updates all files atomically.
Never update version fields by hand in individual files.

## Commit Message Convention (Controls Release Automation)

| Prefix | Effect |
|--------|--------|
| `feat:` | Minor version bump (new skill) |
| `fix:` | Patch version bump (skill improvement, bug fix) |
| `feat!:` or `BREAKING CHANGE:` footer | Major version bump |
| `chore:`, `docs:`, `refactor:` | No version bump |

Incorrect prefixes will produce wrong version bumps or no release at all.

## Skill Writing Conventions

All skills follow these conventions — new skills must too:

- **Hostile, deterministic agents** — no hedging ("might", "could", "potential"), no compliments
- **Silence = approval** — if a finding is not filed, it is implicitly accepted
- **Output destinations are explicit**: skills that write files write findings under `docs/audit/`
  using a skill-specific filename; `pr-reviewer` writes to stdout only and never writes a file
- **Severity levels are enumerated** (Critical / High / Medium / Low, sometimes Advisory)
- **Every finding must include evidence** and a concrete fix — no abstract advice

## Common Mistakes to Avoid

- **Do not** create a skill without YAML frontmatter — it will fail CI
- **Do not** update version in only one file — all five files must be in sync
- **Do not** use `feat:` for a bug fix or `fix:` for a new skill — the commit prefix controls the release bump
- **Do not** reference `codereview.md` or `fixreport.md` as output paths — use `docs/audit/`
- **Do not** read or modify anything under `.claude/agents/` — those are restricted
- **Do not** commit findings files (`docs/audit/*.md`) silently — every audit skill must ask "Commit findings to git? (y/n)" before staging them. Findings files **are** tracked in this repo as the canonical audit history; the rule is "always ask first", not "never commit"

## Development Environment

The project uses [uv](https://docs.astral.sh/uv/) for Python dependency management. Scripts are run via `uv run`:

```bash
uv run scripts/validate-skill.py         # validate public skills
uv run scripts/validate-skill.py .claude/skills/*/SKILL.md  # validate internal skills
uv run scripts/check-version-sync.py     # verify version consistency
```

No `npm install` or Python venv setup is needed — `uv` handles it automatically.
