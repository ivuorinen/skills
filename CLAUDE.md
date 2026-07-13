# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. Shared cross-agent rules live in `AGENTS.md`; this file adds the Claude Code specifics.

## What This Repo Is

A hostile audit toolkit shipped as **one skill** — `nitpicker` — invoked as `/nitpicker <command> [extra instructions]`. The router is `skills/nitpicker/SKILL.md`; each command's instructions live in `skills/nitpicker/commands/<command>.md`, with shared conventions in `commands/_conventions.md`. The repo is installable as a Claude Code plugin via `/plugins`, and into Copilot/pi/other agents via `npx skills add ivuorinen/skills` (open Agent Skills format). Internal dev skills (scaffolding, validation, release) live under `.claude/skills/` and are not shipped to consumers.

## Development Commands

```bash
make check        # validate skill+commands + validate-rules + version sync + findings-store validate + findings-index check + ruff lint + ruff format check + pytest + pre-commit suite (run before every commit)
make validate     # SKILL.md + command-file structure (public + internal)
make test         # run pytest unit tests
make list         # list the skill and its commands
make lint         # ruff check on scripts/, tests/, skills/
make format       # ruff format on scripts/, tests/, skills/
```

## Commands

The authoritative command listing (categorized, with aliases) is `## Commands` in `skills/nitpicker/SKILL.md`; `/nitpicker help` prints it. The 1.x standalone skill names (`security-auditor`, `test-auditor`, …) are aliases of the new short names (`security`, `tests`, …).

## Command File Format

- Only the router `skills/nitpicker/SKILL.md` has YAML frontmatter (`name`, `description` with "Use when", ≤1024 chars, single-quoted when it contains ": ").
- Command files have no frontmatter. Required shape: h1 `# /nitpicker <command> — <Title>` (must match the filename), a `## When to use` section, no header-level jumps. Enforced by `scripts/validate-skill.py`.
- Every file in `commands/` must have a row in one of the command tables of SKILL.md (`## Commands` or `## Internal commands`), 1:1, enforced by `scripts/validate-skill.py`.
- Never duplicate `_conventions.md` content (severity table, findings protocol, generic rules) into a command file.
- No behavioral reliance on Claude-only features (`$ARGUMENTS`, `argument-hint`): arguments are parsed from the free text after the invocation so the skill works in Copilot and pi.

## Findings Store

One file per **open** finding under `docs/audit/findings/<auditor>/open/<id>.md`; resolving one appends a record to the append-only `docs/audit/findings/resolved.jsonl` ledger and deletes the open file (so the tree never accumulates hundreds of resolved files). `INDEX.md` is generated, and an in-store `.gitattributes` (self-written by findings.py) marks the store `linguist-generated` so audit runs don't flood PR diffs. Managed exclusively through the shipped, stdlib-only CLI:

```bash
python3 skills/nitpicker/scripts/findings.py new|resolve|list|show|validate|index|migrate|migrate-resolved ...
```

IDs are content-hashed — never hand-assigned, never reused. `migrate` converts 1.x `docs/audit/*-findings.md` documents; `migrate-resolved` folds a legacy `<auditor>/resolved/*.md` tree into the ledger. The PostToolUse hook `validate-audit-findings-hook.py` validates edited open findings and the ledger, and regenerates the index.

## Script Execution

Two classes (see `.claude/rules/use-uv-runner.md`):

- **Shipped skill tools** (`skills/*/scripts/`): stdlib-only, plain `python3`, `#!/usr/bin/env python3`. The stdlib-only rule is enforced by `scripts/check-stdlib-only.py` (pre-commit + CI) — a third-party import fails the gate.
- **Internal dev tooling** (`scripts/`, `scripts/hooks/`, `tests/`): `uv run --quiet`, `#!/usr/bin/env -S uv run --quiet` + `# /// script` block.

## Adding a New Command

1. Use `/new-command` — it orchestrates the RED → GREEN → REFACTOR → adversarial-review → validate → pr-review cycle for a command file.
2. Create `skills/nitpicker/commands/<name>.md` (short kebab-case name, 2.0 vocabulary — no `-auditor` suffixes).
3. Add its row to the `## Commands` table in `skills/nitpicker/SKILL.md`, the Routing Guide in `.claude/skills/skills/SKILL.md`, and the command table in `README.md`. Update `.github/copilot-instructions.md` only if the new command changes its rules (it deliberately carries no command table).
4. `make check` must pass (the validator enforces table ↔ file sync).
5. Commit with `feat: add /nitpicker <name> command` (minor bump via release-please).

## Conventions

Skill/command writing style and lifecycle are enforced by `.claude/rules/` — see `skill-format.md`, `skill-style.md`, `skill-lifecycle.md`, `use-uv-runner.md`, `github-actions-security.md` (SHA-pinned actions + least-privilege, gated by the `zizmor` pre-commit hook), `use-context-mode.md` (route inspection commands through context-mode; `# ctx-ok` only for real mutations), `commit-gate-integrity.md` (CI `Validate` is the authoritative gate; no `--no-verify` on governed files), and `write-surgical-code.md` (how the repo's own Python gets written — surgical, simplicity-first, verifiable; from Karpathy's LLM-coding notes).

## Plugin Metadata

| File                              | Purpose                                  |
| --------------------------------- | ---------------------------------------- |
| `.claude-plugin/plugin.json`      | Plugin name, version, author, keywords   |
| `.claude-plugin/marketplace.json` | Marketplace listing (used by `/plugins`) |

Version must stay in sync across `package.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.release-please-manifest.json`, and `pyproject.toml`. Use `scripts/bump-version.py` for manual bumps; release-please handles it on CI.

## Versioning

[Semantic Versioning](https://semver.org/) with [release-please](https://github.com/googleapis/release-please):

| Prefix                               | Effect                                      |
| ------------------------------------ | ------------------------------------------- |
| `feat:`                              | Minor bump (new command or feature)         |
| `fix:`                               | Patch bump (command improvement or bug fix) |
| `feat!:` / `BREAKING CHANGE:` footer | Major bump                                  |
| `chore:`, `docs:`, `refactor:`       | No bump                                     |

Merge to `main` → release-please opens a Release PR → merging it creates the GitHub Release and tag.

## Configuration

`.claude/settings.local.json` — local settings; gitignored.

`.claude/settings.json` — shared PostToolUse hooks on every Write/Edit:

- `validate-skill-hook.py` — validates SKILL.md structure on any edited SKILL.md or `commands/*.md` file
- `validate-json-hook.py` — validates JSON syntax on any edited `.json` file
- `check-version-sync-hook.py` — warns when a version file edit desyncs the five manifests
- `ruff-hook.py` — auto-fixes and lints any edited `.py` file
- `validate-audit-findings-hook.py` — validates files under `docs/audit/findings/` and regenerates `INDEX.md`

Plus a Stop hook, `stop-reminder.py`, which reminds about **staged** skill files (`git diff --cached`) before Claude hands back control — so it fires at commit time, not on every turn a working-tree edit exists.

Every hook resolves the repo root as `CLAUDE_PROJECT_DIR` → `REPO_ROOT` → the computed parent of `scripts/hooks/`, in that order. `CLAUDE_PROJECT_DIR` is set by Claude Code; set `REPO_ROOT` only when running a hook manually outside Claude Code against a non-default tree.

`.claude/skills/nitpicker` is a symlink to `../../skills/nitpicker` so Claude Code discovers the shipped public skill alongside the internal dev skills.
