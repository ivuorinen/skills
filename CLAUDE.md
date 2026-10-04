# CLAUDE.md

@AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

The `@AGENTS.md` line above imports the rules shared with every agent. Where a
`CLAUDE.md` exists, Claude Code reads `AGENTS.md` only through that import, so
keep it (agent-rules-7ab9c0ff). This file adds the Claude Code specifics and
does not restate what `AGENTS.md` says.

## What This Repo Is

A hostile audit toolkit shipped as **one skill** — `nitpicker` — invoked as
`/nitpicker <command> [extra instructions]`.

The router is `skills/nitpicker/SKILL.md`. Each command's instructions live in
`skills/nitpicker/commands/<command>.md`, with shared conventions in
`commands/_conventions.md`.

The repo is installable as a Claude Code plugin via `/plugins`, and into
Copilot, pi and other agents via `npx skills add ivuorinen/skills` (open Agent
Skills format). Internal dev skills — scaffolding, validation, release — live
under `.claude/skills/` and are not shipped to consumers.

## Development Commands

```bash
make check        # the full gate; run before every commit. `make help` lists its targets
make validate     # SKILL.md + command-file structure (public + internal)
make validate-evals # shape of each skill's evals/*.json (evals, trigger-queries, pressure-records)
make ring-deps    # print the module dependency graph; fail on an outward (inner→outer) edge
make test         # run pytest unit tests
make list         # list the skill and its commands
make lint         # ruff check on scripts/, tests/, skills/
make format       # ruff format on scripts/, tests/, skills/
make security     # bandit scan of skills/ and scripts/ (config in [tool.bandit])
make opengrep     # opengrep scan (the rules Codacy reports) + stale-suppression check
make agentlinter  # agentlinter scan (Codacy's other engine) against the committed baseline
```

## Commands

The authoritative command listing (categorized, with aliases) is `## Commands` in `skills/nitpicker/SKILL.md`; `/nitpicker help` prints it. The 1.x standalone skill names (`security-auditor`, `test-auditor`, …) are aliases of the new short names (`security`, `tests`, …).

## Command File Format

- Only the router `skills/nitpicker/SKILL.md` has YAML frontmatter (`name`, `description` with "Use when", ≤1024 chars, single-quoted when it contains ": ", plus `license` and `compatibility`).
- Command files have no frontmatter. Required shape: h1 `# /nitpicker <command> — <Title>` (must match the filename), a `## When to use` section, no header-level jumps. Enforced by `scripts/validate-skill.py`.
- The 1:1 command-file ↔ table-row rule is in `AGENTS.md`. Shared files
  prefixed `_` (`_conventions.md`, `_audit-coverage.md`) are the exception,
  and carry no row.
- The ban on Claude-only argument features (`$ARGUMENTS`, `$N`,
  `argument-hint`) lives in `.claude/rules/skill-format.md`.

## Where the detail lives

Each topic below has a rule under `.claude/rules/` with `paths:` frontmatter, so
it loads with the files it governs rather than on every turn:

- The Agent Skills spec, `metadata`-only client keys, `make spec-check` and its
  install traps — `agent-skills-spec.md`.
- The findings store's generated index, content-hashed ids, `export`, and
  `--location` fingerprints — `audit-store.md`; `AGENTS.md` holds the store
  rules every agent keeps.
- On-trigger protocol loading, the `context_pack.py` firewall and
  `check-context-tokens.py` — `context-discipline.md`.
- The shipped/internal script classes, the entry-point/library shebang split, `--help`,
  stdout/stderr and exit codes — `use-uv-runner.md`.
- The MCP (Model Context Protocol) server running stale code after an edit under `skills/*/scripts/` —
  `mcp-stale-server.md`.
- The PR fetchers behind `cr` — `pr-fetchers.md`.
- `# nosec` / `# nosemgrep` and `make opengrep` — `suppression-markers.md`.
- `make agentlinter` and `.agentlinter-baseline.json` — `agentlinter-baseline.md`.
- The version manifests, `uv.lock` and both bump paths — `version-bumps.md`.

## Adding a New Command

1. Use `/new-command` — it orchestrates the RED → GREEN → REFACTOR → adversarial-review → validate → pr-review cycle for a command file.
2. Create `skills/nitpicker/commands/<name>.md` (short kebab-case name, 2.0 vocabulary — no `-auditor` suffixes).
3. Add its row to the `## Commands` table in `skills/nitpicker/SKILL.md`, the Routing Guide in `.claude/skills/skills/SKILL.md`, and the command table in `README.md`. Update `.github/copilot-instructions.md` only if the new command changes its rules (it deliberately carries no command table).
4. `make check` must pass (the validator enforces table ↔ file sync).
5. Commit with `feat: add /nitpicker <name> command` (minor bump via release-please).

## Conventions

Skill and command writing style, lifecycle, and repo conventions live in
`.claude/rules/`.

How much of each rule is machine-enforced varies: several are gated only in
part, and some not at all. Each rule states its own enforcement. Read that
statement in the rule itself rather than assuming a rule here is gated end to
end.

A rule's own frontmatter decides when it loads, and it is the authority: one
with `paths:` loads with the files it governs, one without loads every turn.
`grep -L '^paths:' .claude/rules/*.md` lists the second kind; file a new rule
under the group its frontmatter puts it in.

Loaded every turn:

- `counts-in-prose.md` (author discipline for counts; the neighbouring
  reference drift — stale paths, dead anchors, stale dates, placeholders — is
  gated by `check-rules-anatomy.py`)
- `instruction-budget.md` (gated by `check-agent-instructions.py`: every file a
  session loads each turn draws on one shared budget; the rule file names the
  command that reports the current total)
- `use-context-mode.md`
- `commit-gate-integrity.md`
- `commit-types.md` (author discipline; the CI `commit-lint` job gates only the
  CI-only-diff-with-a-breaking-marker case)
- `snapshot-before-mutating.md` (partly gated: the hook covers direct Bash and
  context-mode shell calls only, not a `git checkout` inside a script)
- `graphify.md` (the knowledge-graph rules `graphify claude install` wrote)

Path-scoped, loaded with the files they govern:

- `skill-format.md`, `skill-style.md`, `skill-official-best-practices.md`,
  `use-uv-runner.md`, `github-actions-security.md`, `vendored-skills.md`
- `skill-lifecycle.md` and `write-surgical-code.md` (agent discipline; no gate)
- `mcp-stale-server.md`, `suppression-markers.md`, `agentlinter-baseline.md`,
  `version-bumps.md`, `enforcement-surface-owner.md`, `hooks-fail-closed.md`,
  `pr-fetchers.md`, `hook-inventory.md`, `agent-skills-spec.md`,
  `audit-store.md`, `context-discipline.md`

## Plugin Metadata and Releases

`.claude-plugin/plugin.json` holds the plugin's name, version, author and
keywords; `.claude-plugin/marketplace.json` is the marketplace listing `/plugins`
reads. Versioning is [Semantic Versioning](https://semver.org/) driven by
[release-please](https://github.com/googleapis/release-please) from the commit
type (`.claude/rules/commit-types.md`). The release workflow: merge to `main` →
release-please opens a Release PR → merging it creates the GitHub Release and
tag.

## Configuration

`.claude/settings.local.json` — local settings; gitignored.

`.claude/settings.json` — shared PostToolUse hooks on every Write/Edit:

- `validate-skill-hook.py` — validates SKILL.md structure on any edited SKILL.md or `commands/*.md` file
- `validate-json-hook.py` — validates JSON syntax on any edited `.json` file
- `check-version-sync-hook.py` — warns when a version file edit desyncs the version manifests
- `ruff-hook.py` — auto-fixes and lints any edited `.py` file
- `validate-audit-findings-hook.py` — validates files under `docs/audit/findings/` and regenerates the findings index
- `validate-rules-hook.py` — validates any edited `.claude/rules/*.md` file (`validate-rules.py` + `check-rules-anatomy.py`)
- `validate-evals-hook.py` — validates the eval set of any edited `skills/*/evals/*.json`
- `count-in-prose-hook.py` — reports a spelled-out count of a growing set in written Markdown or docstrings; feedback via exit 2, not a gate (`.claude/rules/counts-in-prose.md`)

When a validator behind one of these hooks is missing, hangs or cannot start,
the hook exits 1 with a line naming what did not run and the command to run by
hand, rather than exiting 0 in silence: exit 1 is non-blocking, so the edit
stands and the skip is visible. CI stays the binding gate.

Plus a shell PostToolUse hook (Bash and the context-mode shell tools),
`post-bash-revalidate.py`: an edit made through a shell (`sed -i`, redirection,
`git mv`) is invisible to the Write/Edit matchers, so this one re-runs the whole-tree gates when
`git status` shows a governed path dirty. Ignored entries count only inside the
findings store, so a clean tree costs one `git status`. A gate it cannot run
(script or interpreter missing) is reported through `report_skip` with exit
1, or listed in the exit-2 block beside a failing gate
(agent-loopholes-6ca5b557).

The PreToolUse guards, which can *block* a tool call, the graphify guards' binary
pin, the enforcement-surface integrity check (`enforcement-surface-integrity.py`,
SessionStart plus PostToolUse on the shell and Write/Edit tools) and the Stop
hooks are described in `.claude/rules/hook-inventory.md`, which
loads with `.claude/settings.json` and `scripts/hooks/`. `tests/test_settings.py`
fails when a configured PreToolUse hook is unnamed there.

Every hook resolves the repo root as `CLAUDE_PROJECT_DIR` → `REPO_ROOT` → the computed parent of `scripts/hooks/`, in that order. `CLAUDE_PROJECT_DIR` is set by Claude Code; set `REPO_ROOT` only when running a hook manually outside Claude Code against a non-default tree.

That root picks the tree being validated and the working directory, not the
code doing the validating. The validators a hook runs, and the findings store
location, come from the checkout the hook ships in (`SHIPPED_ROOT` in
`_hooklib.py`). Pointing the environment at another checkout changes what is
checked, not what checks it.

`.claude/skills/nitpicker` is a symlink to `../../skills/nitpicker` so Claude Code discovers the shipped public skill alongside the internal dev skills.
