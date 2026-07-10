# Copilot Cloud Agent Instructions

## What This Repository Is

This repo ships **one public skill** — `nitpicker`, a hostile audit toolkit invoked as
`/nitpicker <command> [extra instructions]` — in the open Agent Skills format. The router is
`skills/nitpicker/SKILL.md`; each command's instructions live in `skills/nitpicker/commands/<command>.md`.
It installs into Claude Code (`/plugins` marketplace `ivuorinen/skills`), Copilot, pi, and any
SKILL.md-reading agent via `npx skills add ivuorinen/skills`. Copilot reads skills from
`.github/skills/`, `.claude/skills/`, and `.agents/skills/`; pi invokes `/skill:nitpicker`.

Shared cross-agent rules live in `AGENTS.md` — read it first. `CLAUDE.md` holds Claude Code
specifics. This file adds the Copilot cloud-agent specifics.

## Repository Layout

```text
skills/nitpicker/
  SKILL.md                 # The router: frontmatter + dispatch + Commands table
  commands/
    _conventions.md        # Shared conventions binding every command (severity, findings protocol)
    <command>.md           # One file per command, no frontmatter
  scripts/                 # Shipped tools: findings.py, fetch-pr-comments.py,
                           #   process-sarif.py, check-rules-anatomy.py — stdlib-only, plain python3
.claude/
  skills/                  # Internal dev skills (new-command, release-prep, skills, skill-tester,
                           #   validate-skills) — not shipped to consumers
  rules/                   # Enforced conventions (skill-format, skill-style, use-uv-runner, …)
  settings.json            # Shared PostToolUse hooks
  agents/                  # Sub-agent definitions — do NOT read or modify
.claude-plugin/            # plugin.json + marketplace.json (plugin identity + version)
scripts/                   # Internal dev tooling: validate-skill.py, bump-version.py, hooks, …
docs/audit/findings/       # Per-finding audit store (see below)
tests/                     # pytest suite for the tooling
```

## The Commands

The authoritative command listing (categorized; each command keeps its 1.x skill-name alias) is the
`## Commands` section of `skills/nitpicker/SKILL.md` — do not duplicate it here. Nitpicker in one
line: adversarial, exhaustive auditing across code, security, tests, docs, architecture,
performance, dependencies, error handling, CI, commits, migrations, observability, contracts,
a11y, privacy, config, leaks, i18n, and concurrency, plus PR review and review-comment
implementation.

## File Format — Non-Negotiable Rules

Enforced by `scripts/validate-skill.py` (run via `make validate`, part of `make check` and CI):

**Router (`skills/nitpicker/SKILL.md`)** — the only file with YAML frontmatter:

- `name` must match the directory name exactly (kebab-case)
- `description` must contain `"Use when"`, be ≤ 1024 characters, and be wrapped in single
  quotes when the value contains `": "` (colon + space)

**Command files (`commands/*.md`)** — no frontmatter. Required shape:

- h1 `# /nitpicker <command> — <Title>` where `<command>` matches the filename
- a `## When to use` section
- no header-level jumps (h2 → h4 is an error)
- every file in `commands/` must have a row in one of the command tables of SKILL.md
  (`## Commands` or `## Internal commands`), **1:1**, enforced by `scripts/validate-skill.py` —
  a table row without a file or a file without a row fails validation
- never restate `_conventions.md` content (severity table, findings protocol, generic rules)
- no reliance on Claude-only features (`$ARGUMENTS`, `argument-hint`) in skill bodies:
  arguments are parsed from the free text after the invocation so the skill works in Copilot and pi

## Findings Store

Audits write one file per open finding — never a monolithic report — and append resolved findings to a ledger:

```text
docs/audit/findings/
  INDEX.md                      # generated — never hand-edit
  resolved.jsonl                # append-only ledger of fixed/invalid findings
  .gitattributes                # marks the store linguist-generated (self-written)
  <auditor>/open/<id>.md        # <auditor> is the command name; IDs are content-hashed
```

Drive the store only through the shipped CLI:

```bash
python3 skills/nitpicker/scripts/findings.py new|resolve|list|show|validate|index|migrate|migrate-resolved ...
```

Every finding carries `## Problem`, `## Evidence`, `## Impact`, `## Fix`. `migrate` converts
1.x `docs/audit/*-findings.md` documents.

## Two Script Classes

| Class                | Location                               | Runner                                                                                                                   |
| -------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Shipped skill tools  | `skills/*/scripts/*.py`                | plain `python3`, stdlib-only, `#!/usr/bin/env python3` — consumers cannot be assumed to have uv or any installed package |
| Internal dev tooling | `scripts/`, `scripts/hooks/`, `tests/` | `uv run --quiet <script>`, shebang `#!/usr/bin/env -S uv run --quiet` + `# /// script` block                             |

## Validation — Run Before Every Commit

```bash
make check     # validate skill+commands + rules + version sync + findings store + findings index + lint + format check + pytest + pre-commit
make list      # list the skill and its commands
make test      # pytest suite for the tooling
```

CI runs the same checks on every push/PR touching skills, scripts, tests, rules, or version files.

## Versioning — Five Files Must Stay in Sync

The canonical version lives in `package.json`. All five must match: `package.json`,
`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (`plugins[0].version`),
`.release-please-manifest.json`, `pyproject.toml`. Use `scripts/bump-version.py [major|minor|patch]`
for manual bumps — never edit version fields by hand in individual files.

## Commit Message Convention (Controls Release Automation)

| Prefix                                | Effect                                    |
| ------------------------------------- | ----------------------------------------- |
| `feat:`                               | Minor bump (new command or feature)       |
| `fix:`                                | Patch bump (command improvement, bug fix) |
| `feat!:` or `BREAKING CHANGE:` footer | Major bump                                |
| `chore:`, `docs:`, `refactor:`        | No bump                                   |

release-please derives releases from these prefixes; a wrong prefix mis-versions the release.

## Adding a New Command

1. Create `skills/nitpicker/commands/<name>.md` (short kebab-case name, 2.0 vocabulary — no
   `-auditor` suffixes) with the required h1 and `## When to use`.
2. Add its row to the `## Commands` table in `skills/nitpicker/SKILL.md`.
3. Add it to the Routing Guide in `.claude/skills/skills/SKILL.md`.
4. Add it to the command table in `README.md` and mention it here if it changes the rules above.
5. `make check` must pass (the validator enforces table ↔ file sync).
6. Commit with `feat: add /nitpicker <name> command`.

## Common Mistakes to Avoid

- **Do not** duplicate `_conventions.md` content into a command file — commands inherit it.
- **Do not** hand-edit `docs/audit/findings/INDEX.md` — it is generated by `findings.py index`.
- **Do not** add uv invocations or non-stdlib imports to shipped tools under
  `skills/nitpicker/scripts/` — they must run with plain `python3` on any consumer machine.
- **Do not** add a Commands-table row without its command file, or a command file without its
  row — the 1:1 sync check fails CI.
- **Do not** use `$ARGUMENTS` or other Claude-only substitution in skill bodies — parse the
  free text after the invocation instead.
- **Do not** add frontmatter to command files, or omit it from the router SKILL.md.
- **Do not** update the version in only one manifest — all five must move together.
- **Do not** read or modify anything under `.claude/agents/` — those are restricted.
- **Do not** commit finding files silently — audits ask "Commit findings to git? (y/n)" first.
