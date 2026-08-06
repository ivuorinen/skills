# Contributing

This repo ships **nitpicker**, a hostile audit toolkit, as one skill plus a
Claude Code plugin. Everything below is enforced by tooling in the repo — none
of it is aspirational.

## Before every commit

```bash
make check
```

`check` runs eleven targets in this order (see `Makefile`):

| Step                | What it does                                                              |
| ------------------- | ------------------------------------------------------------------------- |
| `validate`          | `scripts/validate-skill.py` on the router, command files, internal skills |
| `validate-rules`    | `scripts/validate-rules.py` — `.claude/rules/` structure + path freshness |
| `version-sync`      | `scripts/check-version-sync.py` — version equal across five manifests     |
| `audit-consistency` | `findings.py validate` — the `docs/audit/findings/` store is well-formed  |
| `index-check`       | regenerates `INDEX.md`, fails if it was stale (`git diff --exit-code`)    |
| `lint`              | `ruff check scripts/ tests/ skills/`                                      |
| `format-check`      | `ruff format --check` (no writes)                                         |
| `security`          | `bandit` over `skills/` + `scripts/`; config in `[tool.bandit]`           |
| `typecheck`         | `pyright` — zero floor: any error fails the gate                          |
| `test`              | `pytest tests/`                                                           |
| `pre-commit`        | full pre-commit suite (markdownlint, yamllint, gitleaks, zizmor, …)       |

`index-check` and `pre-commit` are the slow ones. The CI `Validate` job is the
authoritative gate — a green `make check` locally is the fast path to it, not a
substitute.

## Two script classes

Never mix the runners (`.claude/rules/use-uv-runner.md`):

- **Shipped skill tools** — anything under `skills/*/scripts/`. Standard library
  only, run with plain `python3 <script>`, shebang `#!/usr/bin/env python3`, no
  `# /// script` block. These execute on consumer machines where `uv` cannot be
  assumed to exist. `scripts/check-stdlib-only.py` (pre-commit + CI) fails the
  build on any third-party import.
- **Internal dev tooling** — `scripts/`, `scripts/hooks/`, `tests/`. Run with
  `uv run --quiet <script>`; new files start with `#!/usr/bin/env -S uv run
  --quiet` and carry a `# /// script` inline metadata block.

## Commit messages

Conventional Commits; release-please derives the version bump:

| Prefix                                | Effect                           |
| ------------------------------------- | -------------------------------- |
| `feat:`                               | Minor bump — new command/feature |
| `fix:`                                | Patch bump — bug or improvement  |
| `feat!:` / `BREAKING CHANGE:` footer  | Major bump                       |
| `chore:`, `docs:`, `refactor:`, `ci:` | No bump                          |

A docs-only or `.claude/rules/`-only change is `docs:` or `chore:`, never
`feat:` — it ships no new capability and must not bump the minor version.

Merging to `main` opens a release-please Release PR; merging that PR creates the
tag and GitHub Release.

## Adding a command

Use `/new-command`, which drives the RED → GREEN → REFACTOR → adversarial-review
→ validate → PR-review cycle. Five registration surfaces must end up in sync
(the validator enforces 1–2):

1. `skills/nitpicker/commands/<name>.md` — short kebab-case name, no
   frontmatter, h1 `# /nitpicker <name> — <Title>`, a `## When to use` section.
2. The `## Commands` table in `skills/nitpicker/SKILL.md` — 1:1 with the files
   in `commands/`; a row without a file or a file without a row fails
   `scripts/validate-skill.py`.
3. The Routing Guide in `.claude/skills/skills/SKILL.md`.
4. The command table in `README.md`.
5. `.github/copilot-instructions.md`, only if the change alters a stated rule.

Never duplicate `commands/_conventions.md` (severity table, findings protocol,
generic rules) into a command file. Never rely on Claude-only argument
substitution (`$ARGUMENTS`, `argument-hint`) — arguments are parsed from the free
text after the invocation so the skill behaves identically in Copilot and pi.

Commit as `feat: add /nitpicker <name> command`.

## The findings store is CLI-only

`docs/audit/findings/` is managed exclusively through the shipped CLI:

```bash
python3 skills/nitpicker/scripts/findings.py new|resolve|list|show|validate|index|baseline|migrate ...
```

IDs are content-hashed — never hand-assigned, never reused. Never hand-edit
`INDEX.md` (generated) or `resolved.jsonl` (append-only ledger).

## Never bypass the gate

Do not pass `--no-verify` when committing skill files, version manifests, or the
findings store (`.claude/rules/commit-gate-integrity.md`). It skips the
pre-commit validators that guard them, and PostToolUse hooks never fire on Bash
edits (`sed -i`, redirection, `git mv`), so CI `Validate` is the only check that
binds every change on its way into a protected branch.
