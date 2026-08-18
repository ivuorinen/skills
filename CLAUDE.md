# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. Shared cross-agent rules live in `AGENTS.md`; this file adds the Claude Code specifics.

## What This Repo Is

A hostile audit toolkit shipped as **one skill** — `nitpicker` — invoked as `/nitpicker <command> [extra instructions]`. The router is `skills/nitpicker/SKILL.md`; each command's instructions live in `skills/nitpicker/commands/<command>.md`, with shared conventions in `commands/_conventions.md`. The repo is installable as a Claude Code plugin via `/plugins`, and into Copilot/pi/other agents via `npx skills add ivuorinen/skills` (open Agent Skills format). Internal dev skills (scaffolding, validation, release) live under `.claude/skills/` and are not shipped to consumers.

## Development Commands

```bash
make check        # the full gate; run before every commit. `make help` lists its targets
make validate     # SKILL.md + command-file structure (public + internal)
make validate-evals # evals/evals.json + evals/trigger-queries.json shape per skill
make test         # run pytest unit tests
make list         # list the skill and its commands
make lint         # ruff check on scripts/, tests/, skills/
make format       # ruff format on scripts/, tests/, skills/
make security     # bandit scan of skills/ and scripts/ (config in [tool.bandit])
```

## Commands

The authoritative command listing (categorized, with aliases) is `## Commands` in `skills/nitpicker/SKILL.md`; `/nitpicker help` prints it. The 1.x standalone skill names (`security-auditor`, `test-auditor`, …) are aliases of the new short names (`security`, `tests`, …).

## Agent Skills Spec Compliance

The normative format is the open spec at <https://agentskills.io/specification>.
`scripts/validate-skill.py` enforces it. Required: `name` (≤64 chars,
lowercase/digits/hyphens, no leading, trailing or consecutive hyphen, matching
its directory) and `description` (≤1024 chars). Optional: `license`,
`compatibility` (≤500 chars), `metadata` (a string→string map) and
`allowed-tools` (one space-separated string).

A top-level key outside that set is an **error**. Client-specific properties go
under `metadata`, which is what the spec designates it for. There is no
allowlist and no exemption; internal dev skills are held to the same rule. Body
size warns past 500 lines or ~5000 tokens, the progressive-disclosure
instructions tier.

`disable-model-invocation` therefore lives under `metadata` as `"true"`, quoted
because metadata values are strings. Claude Code reads that key from the top
level only, so under `metadata` it is inert and those skills become
model-invocable. That trade was accepted deliberately, buying portability.

Each skill's eval sets live in `<skill-dir>/evals/` — `evals.json` (output-quality cases with gradable assertions) and `trigger-queries.json` (description trigger accuracy, fixed train/validation split) — gated by `make validate-evals`. See `.claude/rules/skill-official-best-practices.md`.

`make spec-check` cross-checks every skill against the Agent Skills reference
validator. It needs network access, so it sits outside `make check`;
`validate-skill.py` enforces the same constraints offline. Every skill passed at
the time of writing, internal dev skills included — re-run it rather than
trusting that, since a spec release can change the verdict.

Three install traps, each hit once already:

- The PyPI package is `skills-ref`, but its console script is `agentskills`.
  The spec page still documents a `skills-ref` command, which no longer exists
  and exits 1 with no output.
- The identically-named npm package is unrelated to Anthropic.
- Failures print to stderr and successes to stdout, so merge stderr before
  judging a run clean.

## Command File Format

- Only the router `skills/nitpicker/SKILL.md` has YAML frontmatter (`name`, `description` with "Use when", ≤1024 chars, single-quoted when it contains ": ", plus `license` and `compatibility`).
- Command files have no frontmatter. Required shape: h1 `# /nitpicker <command> — <Title>` (must match the filename), a `## When to use` section, no header-level jumps. Enforced by `scripts/validate-skill.py`.
- Every command file in `commands/` whose name does not begin with `_` must have a row in one of the command tables of SKILL.md (`## Commands` or `## Internal commands`), 1:1, enforced by `scripts/validate-skill.py`; shared files prefixed `_` (e.g. `_conventions.md`, `_audit-coverage.md`) are exempt from the cross-check.
- Never duplicate `_conventions.md` content (severity table, findings protocol, generic rules) into a command file.
- No behavioral reliance on Claude-only features (`$ARGUMENTS`, `argument-hint`): arguments are parsed from the free text after the invocation so the skill works in Copilot and pi.

## Findings Store

One file per **open** finding under `docs/audit/findings/<auditor>/open/<id>.md`; resolving one appends a record to the append-only `docs/audit/findings/resolved.jsonl` ledger and deletes the open file (so the tree never accumulates hundreds of resolved files). `INDEX.md` is generated, and an in-store `.gitattributes` (self-written by findings.py) marks the store `linguist-generated` so audit runs don't flood PR diffs. Managed exclusively through the shipped, stdlib-only CLI:

```bash
python3 skills/nitpicker/scripts/findings.py new|resolve|list|show|validate|index|baseline|migrate ...
```

IDs are content-hashed — never hand-assigned, never reused. `migrate` converts 1.x `docs/audit/*-findings.md` documents; `migrate-resolved` folds a legacy `<auditor>/resolved/*.md` tree into the ledger. The PostToolUse hook `validate-audit-findings-hook.py` validates edited open findings and the ledger, and regenerates the index.

## PR Fetchers

`cr` reads a PR's review surface through two entry points —
`fetch-pr-comments.py` and `fetch-pr-status.py` — that cover GitHub, GitLab and
Bitbucket Cloud behind **one** JSON format. Both are thin: they resolve their
sibling directory and delegate to `pr_common.run_cli`, which parses the argument
forms, dispatches on platform, and maps exceptions to the 0/1/2 exit contract.

`pr_common.py` owns everything shared — git-remote parsing, platform detection,
the `Target` (platform + git host + project path, from which the API base is
derived), the credential-pinned HTTP layer, both pagination styles, and the
output envelopes. One provider module per platform (`pr_github.py`,
`pr_gitlab.py`, `pr_bitbucket.py`) exposes exactly `fetch_comments(target, n)`
and `fetch_status(target, n)`.

Two invariants make the shared format worth having, and both are pinned by
tests. A field a platform cannot supply is present and empty or null, never
absent — a caller must never branch on key existence to learn which platform
answered. And a credential is only ever sent to the host it was declared for:
the redirect handler is built per-request with that host, every paginated URL is
re-validated before it is followed (both `Link` headers and body `next` fields
are server-controlled), and `GH_HOST`/`GITLAB_HOST` gate a token against a
self-hosted instance. Platform detection refuses an unrecognised host rather
than guessing, since a wrong guess is a credential handed to a third party.

The MCP tools `np_pr_comments` and `np_pr_status` wrap the same providers. They
are the only tools on the server carrying `openWorldHint: true`, and the only
ones whose results are wrapped in an `<untrusted-data source="pull-request">`
envelope — PR bodies are written by anyone who can comment on the PR.

## Script Execution

Two classes (see `.claude/rules/use-uv-runner.md`):

- **Shipped skill tools** (`skills/*/scripts/`): stdlib-only, plain `python3`, `#!/usr/bin/env python3`. The stdlib-only rule is enforced by `scripts/check-stdlib-only.py` (pre-commit + CI) — a third-party import fails the gate.
- **Internal dev tooling** (`scripts/`, `scripts/hooks/`, `tests/`): `uv run --quiet`, `#!/usr/bin/env -S uv run --quiet` + `# /// script` block.

Every shipped tool answers `--help`/`-h` with its interface on stdout at exit 0.
Structured data goes to stdout, diagnostics to stderr. Exit codes are distinct
per failure class: 0 success, 1 runtime or I/O error, 2 usage error.

Handle `--help` before any positional argument resolves as a path. Otherwise the
flag is read as input and the agent gets a path error in place of usage text.
The design rules live in `.claude/rules/use-uv-runner.md`; enforcement is author
discipline plus the per-tool `--help` tests.

## Adding a New Command

1. Use `/new-command` — it orchestrates the RED → GREEN → REFACTOR → adversarial-review → validate → pr-review cycle for a command file.
2. Create `skills/nitpicker/commands/<name>.md` (short kebab-case name, 2.0 vocabulary — no `-auditor` suffixes).
3. Add its row to the `## Commands` table in `skills/nitpicker/SKILL.md`, the Routing Guide in `.claude/skills/skills/SKILL.md`, and the command table in `README.md`. Update `.github/copilot-instructions.md` only if the new command changes its rules (it deliberately carries no command table).
4. `make check` must pass (the validator enforces table ↔ file sync).
5. Commit with `feat: add /nitpicker <name> command` (minor bump via release-please).

## Conventions

Skill/command writing style, lifecycle, and repo conventions live in `.claude/rules/`. How much of each rule is machine-enforced varies — several are gated only in part, and some not at all. Each rule states its own enforcement; read that statement in the rule itself rather than assuming a rule here is gated end to end.

- `skill-format.md`
- `skill-style.md`
- `skill-lifecycle.md` (agent discipline; no gate)
- `skill-official-best-practices.md`
- `use-uv-runner.md`
- `github-actions-security.md`
- `use-context-mode.md`
- `commit-gate-integrity.md`
- `commit-types.md` (author discipline; the CI `commit-lint` job gates only the
  CI-only-diff-with-a-breaking-marker case)
- `write-surgical-code.md` (agent discipline; no gate)
- `snapshot-before-mutating.md` (partly gated: the hook covers direct Bash only,
  not a `git checkout --` inside a script)
- `vendored-skills.md`

## Plugin Metadata

| File                              | Purpose                                  |
| --------------------------------- | ---------------------------------------- |
| `.claude-plugin/plugin.json`      | Plugin name, version, author, keywords   |
| `.claude-plugin/marketplace.json` | Marketplace listing (used by `/plugins`) |

Version must stay in sync across `package.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.release-please-manifest.json`, and `pyproject.toml`. Use `scripts/bump-version.py` for manual bumps; release-please handles it on CI.

`uv.lock` carries a sixth copy in its root `[[package]]` entry.
Neither `check-version-sync.py` nor release-please covers it — 3.0.0 shipped
with the lockfile still declaring 2.0.0. `make lock-check` gates it with
`uv lock --check`, uv's own staleness test, which also catches dependency drift.

Both bump paths keep it current. `bump-version.py` re-locks after writing the
manifests. On CI, the `sync-lockfile` job in `release-please.yml` commits the
regenerated lockfile onto the release PR, because release-please has no updater
for it.

Re-locking is best-effort rather than guaranteed. When `uv` is absent, times
out, or fails, `bump-version.py` reports the failure and continues instead of
aborting a bump whose manifests are already written. It names the recovery in
its output.

Run `uv lock` to resync — that is the supported way to move the version in the
lockfile. Hand-edit `uv.lock` only where uv cannot run at all, and treat that as
a stopgap: the next `uv lock` overwrites the value.

## Versioning

[Semantic Versioning](https://semver.org/) with [release-please](https://github.com/googleapis/release-please):

| Prefix                                | Effect                                      |
| ------------------------------------- | ------------------------------------------- |
| `feat:`                               | Minor bump (new command or feature)         |
| `fix:`                                | Patch bump (command improvement or bug fix) |
| `feat!:` / `BREAKING CHANGE:` footer  | Major bump                                  |
| `chore:`, `docs:`, `refactor:`, `ci:` | No bump                                     |

Merge to `main` → release-please opens a Release PR → merging it creates the GitHub Release and tag.

## Configuration

`.claude/settings.local.json` — local settings; gitignored.

`.claude/settings.json` — shared PostToolUse hooks on every Write/Edit:

- `validate-skill-hook.py` — validates SKILL.md structure on any edited SKILL.md or `commands/*.md` file
- `validate-json-hook.py` — validates JSON syntax on any edited `.json` file
- `check-version-sync-hook.py` — warns when a version file edit desyncs the five manifests
- `ruff-hook.py` — auto-fixes and lints any edited `.py` file
- `validate-audit-findings-hook.py` — validates files under `docs/audit/findings/` and regenerates `INDEX.md`
- `validate-rules-hook.py` — validates any edited `.claude/rules/*.md` file (`validate-rules.py` + `check-rules-anatomy.py`)
- `validate-evals-hook.py` — validates the eval set of any edited `skills/*/evals/*.json`

Plus a **Bash** PostToolUse hook, `post-bash-revalidate.py`: Write/Edit matchers
never see a Bash-mediated edit (`sed -i`, redirection, `git mv`), so this one
re-runs the whole-tree gates when `git status` shows a governed path dirty.

Plus three **PreToolUse** hooks, which can *block* a tool call before it runs —
the most behaviour-changing entries in the file:

- matcher `Bash` — `deny-agents-path-hook.py`, which blocks a Bash command whose
  text names `.claude/agents/` **or a full protected agent filename** —
  literally, quoted, escaped, variable-built, or glob-spelled (the
  `permissions.deny` block binds file tools, never Bash — and it names only
  `Read(...)` and `Edit(...)` rules; whether an `Edit` rule also binds the
  **Write** tool is undocumented, so treat Write coverage as unverified.
  `tests/test_settings.py` pins the list as configured). So
  `find . -name release-readiness-reviewer.md -exec cat {} +` is blocked too.
  It raises the cost of reaching that tree; it does not close it. The guard
  matches tokens, so a command that locates the files by **content** rather than
  by path or name (`git ls-files | grep review | xargs cat`) carries neither
  token and passes — the one token it does carry, `review`, is a nitpicker
  command name that appears in ordinary commands constantly, so matching it
  would block routine work. Treat `.github/CODEOWNERS` plus branch protection as
  the binding control, not this hook.
- matcher `Bash` — `graphify hook-guard search`
- matcher `Read|Glob` — `graphify hook-guard read`

Each graphify guard is wrapped `command -v graphify >/dev/null || exit 0; exec
graphify hook-guard …`, so on a clone without graphify installed it exits 0 and
is a no-op; when graphify is on `PATH` the guard's own exit code propagates and
can block the call.

Plus a Stop hook, `stop-reminder.py`, which reminds about pending skill files — the union of the git index (`git diff --cached`) and the working tree (`git diff`), so **unstaged** edits count too — before Claude hands back control. A `stop_hook_active` guard surfaces the reminder once rather than looping on every turn a skill edit remains uncommitted.

Every hook resolves the repo root as `CLAUDE_PROJECT_DIR` → `REPO_ROOT` → the computed parent of `scripts/hooks/`, in that order. `CLAUDE_PROJECT_DIR` is set by Claude Code; set `REPO_ROOT` only when running a hook manually outside Claude Code against a non-default tree.

`.claude/skills/nitpicker` is a symlink to `../../skills/nitpicker` so Claude Code discovers the shipped public skill alongside the internal dev skills.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:

- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
