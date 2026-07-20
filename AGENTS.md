# Agent Instructions

This repository ships **nitpicker** — a hostile audit skill dispatching a
categorized deck of commands, invoked as
`/nitpicker <command> [extra instructions]` — in the
open Agent Skills format (`skills/nitpicker/SKILL.md`). It works in Claude
Code, GitHub Copilot, pi, and any agent that reads SKILL.md skills; install
via `npx skills add ivuorinen/skills` or the Claude Code plugin marketplace.

## Working on this repo

- Run `make check` before declaring any change done (validation, lint,
  format check, tests). `make list` shows the skill and its commands.
- **Shipped skill tools** (`skills/*/scripts/*.py`) are stdlib-only and run
  with plain `python3` — never add non-stdlib imports or uv invocations;
  consumer machines cannot be assumed to have uv.
- **Internal dev tooling** (`scripts/`, `scripts/hooks/`, `tests/`) runs via
  `uv run --quiet <script>`, never `python3` directly. New internal scripts
  start with `#!/usr/bin/env -S uv run --quiet` and a `# /// script` block.
- Audit findings: one file per open finding under `docs/audit/findings/`;
  resolved ones are appended to `docs/audit/findings/resolved.jsonl`. Managed
  only through `skills/nitpicker/scripts/findings.py`
  (new/resolve/list/show/validate/index/baseline/migrate). Never
  hand-edit `INDEX.md` or `resolved.jsonl`.
- Command files live in `skills/nitpicker/commands/<command>.md`; each must
  have a row in one of the command tables of `skills/nitpicker/SKILL.md`
  (`## Commands` or `## Internal commands`), 1:1
  (enforced by `scripts/validate-skill.py`). Shared audit conventions live
  in `commands/_conventions.md` — never duplicate them into command files.
- Never read or modify anything under `.claude/agents/` — sub-agent
  definitions are trusted configuration that gates releases, and an agent
  must not rewrite its own reviewer. Denied in `.claude/settings.json` and
  owned in `.github/CODEOWNERS`.
- Third-party content carries its upstream license: a vendored skill ships
  its own `LICENSE` and every vendored or "Adapted from" work has an entry in
  the root `NOTICE`. See `.claude/rules/vendored-skills.md`.
- Commit messages follow Conventional Commits; release-please derives
  version bumps from them (`feat:` minor, `fix:` patch, `feat!:` major) —
  see `.claude/rules/commit-types.md` for which type a change takes.
  Version must stay in sync across package.json, pyproject.toml,
  .claude-plugin/plugin.json, .claude-plugin/marketplace.json, and
  .release-please-manifest.json (`make version-sync`).

Claude Code-specific guidance (hooks, internal dev skills) lives in
`CLAUDE.md` and `.claude/`; Copilot cloud-agent guidance in
`.github/copilot-instructions.md`. Both defer to this file for the shared
rules above.
