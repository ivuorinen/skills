# Copilot Cloud Agent Instructions

## What This Repository Is

A **Claude Code plugin** (`ivuorinen-skills`) containing hostile audit skills. Each skill is a self-contained prompt file (`SKILL.md`) that Claude Code loads when a user invokes it. The repo is installable via `/plugins` and is versioned with semantic versioning using release-please automation.

## Repository Layout

```
skills/                    # Public skills (shipped with the plugin)
  <skill-name>/
    SKILL.md               # Skill definition (YAML frontmatter + prompt body)
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
    validate-skills.yml    # CI: validates skills + version sync when SKILL.md files or scripts/validate-skill.py change
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
description: Use when [triggering conditions and symptoms].
---
```

Validation rules enforced by `scripts/validate-skill.py` (and CI):

- `name` must match the **directory name exactly** (kebab-case)
- `description` must start with `"Use when"` — describes triggering conditions, not what the skill does
- `description` must be ≤ 500 characters
- Header levels in the body must not skip (e.g., h2 → h4 is an error)
- Do not reference legacy output paths (`codereview.md`, `fixreport.md`) — use `docs/audit/` instead

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

## Adding a New Skill

1. Create `skills/<kebab-case-name>/SKILL.md` with valid frontmatter
2. Add a row to the skills table in `CLAUDE.md` and the "Existing Public Skills" table in `.github/copilot-instructions.md` (these are the source of truth for the public skill list). If `README.md` includes a mirrored skills table, update it too so it stays in sync.
3. Run `make validate` to confirm the new skill passes validation
4. Run `/pr-reviewer` and fix all findings; repeat until `pr-reviewer` reports no findings
5. Commit with `feat: add <name> skill` — this triggers a **minor** version bump via release-please

## Validation — Run Before Every Commit

```bash
make check          # validate + version-sync + ruff lint (all three must pass)
make validate       # SKILL.md frontmatter + structure only
make version-sync   # version consistency across manifests
make lint           # ruff check on scripts/
make list           # print all skills with descriptions
```

CI runs `make validate` + version sync on every push/PR that touches a `SKILL.md` file or `scripts/validate-skill.py`.

## Versioning — Five Files Must Stay in Sync

The canonical version lives in `package.json`. All five must match:

| File | Field |
|------|-------|
| `package.json` | `"version"` |
| `.claude-plugin/plugin.json` | `"version"` |
| `.claude-plugin/marketplace.json` | `"plugins[0].version"` |
| `.release-please-manifest.json` | `"."` |
| `pyproject.toml` | `project.version` |

Use `scripts/bump-version.py [major|minor|patch]` for manual bumps — it updates all files atomically. Never update version fields by hand in individual files.

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
- **Output destinations are explicit**: skills that write files write to `docs/audit/<skill>-findings.md`; `pr-reviewer` writes to stdout only and never writes a file
- **Severity levels are enumerated** (Critical / High / Medium / Low, sometimes Advisory)
- **Every finding must include evidence** and a concrete fix — no abstract advice

## Common Mistakes to Avoid

- **Do not** create a skill without YAML frontmatter — it will fail CI
- **Do not** update version in only one file — all five files must be in sync
- **Do not** use `feat:` for a bug fix or `fix:` for a new skill — the commit prefix controls the release bump
- **Do not** reference `codereview.md` or `fixreport.md` as output paths — use `docs/audit/`
- **Do not** read or modify anything under `.claude/agents/` — those are restricted
- **Do not** commit findings files (`docs/audit/*.md`) unless explicitly asked — skills always ask first

## Development Environment

The project uses [uv](https://docs.astral.sh/uv/) for Python dependency management. Scripts are run via `uv run`:

```bash
uv run scripts/validate-skill.py         # validate public skills
uv run scripts/validate-skill.py .claude/skills/*/SKILL.md  # validate internal skills
uv run scripts/check-version-sync.py     # verify version consistency
```

No `npm install` or Python venv setup is needed — `uv` handles it automatically.
