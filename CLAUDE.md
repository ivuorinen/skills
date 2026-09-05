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
make opengrep     # opengrep scan (the rules Codacy reports) + stale-suppression check
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

One file per **open** finding under `docs/audit/findings/<auditor>/open/<id>.md`; resolving one appends a record to the append-only `docs/audit/findings/resolved.jsonl` ledger and deletes the open file (so the tree never accumulates hundreds of resolved files). `INDEX.md` is generated, and an in-store `.gitattributes` (self-written by findings.py) marks the store `linguist-generated` so audit runs don't flood PR diffs. Managed through the `np_*` MCP tools where the session exposes them, else the shipped, stdlib-only CLI; `baseline`, `migrate` and `migrate-resolved` are CLI-only:

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
tests. A field a platform cannot supply is present and empty or null rather than
absent, so a caller reads every key unconditionally instead of branching on key
existence to learn which platform answered. And a credential is only ever sent
to the host it was declared for:
the redirect handler is built per-request with that host, every paginated URL is
re-validated before it is followed (both `Link` headers and body `next` fields
are server-controlled), and a token reaches only its platform's own public host
unless `GH_HOST`/`GITLAB_HOST` names the self-hosted one. Withheld by default,
declared by exception — the reverse, gating on a *mismatch*, cannot express it,
because the common case never sets the variable and so mismatches nothing. Platform detection refuses an unrecognised host rather
than guessing, since a wrong guess is a credential handed to a third party.

The MCP (Model Context Protocol) tools `np_pr_comments` and `np_pr_status` wrap
the same providers. They are the only tools on the server carrying
`openWorldHint: true`, and the only ones whose results are wrapped in an
`<untrusted-data source="pull-request">` envelope — PR bodies are written by
anyone who can comment on the PR.

## Editing a shipped tool mid-session

The MCP server imports every shipped module it depends on once at startup and
holds them for the life of the process. `_LOADED` in `mcp_server.py` is the
authoritative list; it includes the hyphen-named `process-sarif.py` and
`check-rules-anatomy.py`, which reach it through `_load_bundled` rather than a
plain import and are easy to overlook. **Editing any module on that list does
not change what the running server executes.** Worse, two servers are
registered: `.mcp.json` starts one from the working tree, and
`.claude-plugin/plugin.json` starts one from `${CLAUDE_PLUGIN_ROOT}` — the
installed copy under `~/.claude/plugins/cache/`, which reflects only the
installed version, at any age.

So after editing anything under `skills/*/scripts/`, drive the findings store
through `python3 skills/nitpicker/scripts/findings.py` for the rest of the
session; it loads fresh every invocation. Restarting the session picks up the
new code.

`mcp_server.py` records each module's mtime at import and prefixes a `[warn]`
line to the result of every tool that writes (`np_new_finding`,
`np_resolve_finding`, `np_write_index`) when the file has since changed, or
when it is serving a different copy than the project has on disk. The read
tools carry no such prefix, so an edit to `process-sarif.py` or
`check-rules-anatomy.py` reaches you through the rule above and through nothing
else: `np_process_sarif` will consolidate a security scan with code that is not
on disk and say nothing. This is a backstop, not the control: the rule above is.

This is not hypothetical. A stale `redact()` wrote an unredacted credential into
`resolved.jsonl` during the audit that added the redaction, and only a
`detect-private-key` commit hook caught it — see `audit-9bc6eb39`.

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

## Suppression Markers

Two scanners run over `skills/` and `scripts/`, and each has its own marker:
`# nosec` for bandit, `# nosemgrep` for opengrep. `make opengrep` gates the
second, and `scripts/check-opengrep.py` is the tool.

opengrep is the scanner Codacy reports from, and its ruleset lived only in the
Codacy UI — so a finding was invisible from a checkout and reproducible only by
pushing. Two commits went to configuring bandit before the owner pointed out
which engine was actually reporting. `make opengrep` runs
`r/python.lang.security.audit`, the namespace that reproduces those findings
(`p/python` returns nothing here; it omits the `-audit` rule variants).

**A `# nosemgrep` marker only counts on the finding's own line or the line
directly above it.** One line further up is ignored silently — no warning, no
diff, the finding just quietly comes back. A reason comment therefore belongs
*above* the marker: one placed between the marker and the code separates the
two, and the suppression stops applying.

So the gate also runs a second pass with `--disable-nosem` and fails on any
marker that lines up with no revealed finding. That catches the misplaced marker
and the leftover one that outlived its call. Nothing else checks this; Codacy
does not.

Two things worth knowing before trusting a clean run:

- Staleness is judged only against the configured namespace, so suppressing a
  rule outside it means widening `CONFIG` first, or the marker reads as stale.
- Markers outside the scanned roots are judged neither way; the count is printed
  rather than passed over silently.

A scan error fails the gate. opengrep skips a file it cannot parse, so a parse
error means unscanned code, and reporting the remainder as clean would hide it.
This is also why the gate runs opengrep rather than semgrep: semgrep 1.172.0
cannot parse a `match` statement and drops the whole file, and this repo uses
them.

Locally the target skips when opengrep is absent; under CI it fails instead,
because a gate that skips silently is not a gate. The `Validate` workflow
installs a version-pinned, digest-verified binary before `make check`.

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
- `counts-in-prose.md` (author discipline for counts; the neighbouring
  reference drift — stale paths, dead anchors, stale dates, placeholders — is
  gated by `check-rules-anatomy.py`)
- `instruction-budget.md` (gated by `check-agent-instructions.py`: every file a
  session loads each turn draws on one shared budget; the rule file names the
  command that reports the current total)
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

`uv.lock` carries one more copy in its root `[[package]]` entry.
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
- `check-version-sync-hook.py` — warns when a version file edit desyncs the version manifests
- `ruff-hook.py` — auto-fixes and lints any edited `.py` file
- `validate-audit-findings-hook.py` — validates files under `docs/audit/findings/` and regenerates `INDEX.md`
- `validate-rules-hook.py` — validates any edited `.claude/rules/*.md` file (`validate-rules.py` + `check-rules-anatomy.py`)
- `validate-evals-hook.py` — validates the eval set of any edited `skills/*/evals/*.json`

Plus a **Bash** PostToolUse hook, `post-bash-revalidate.py`: Write/Edit matchers
never see a Bash-mediated edit (`sed -i`, redirection, `git mv`), so this one
re-runs the whole-tree gates when `git status` shows a governed path dirty.

Plus the **PreToolUse** hooks below, which can *block* a tool call before it
runs — the most behaviour-changing entries in the file. `.claude/settings.json`
holds the authoritative list; `tests/test_settings.py` fails when one of them is
configured and unnamed here:

- matcher `Bash` — `deny-agents-path-hook.py`, which blocks a Bash command whose
  text names `.claude/agents/` **or a full protected agent filename** —
  literally, quoted, escaped, variable-built, or glob-spelled (the
  `permissions.deny` block binds file tools only, not Bash — it names `Read`,
  `Edit` **and** `Write` rules explicitly, rather than assuming an `Edit` rule
  also binds Write, which is undocumented client behaviour no in-repo gate can
  observe. `tests/test_settings.py` pins the exact list). So
  `find . -name release-readiness-reviewer.md -exec cat {} +` is blocked too.
  It raises the cost of reaching that tree; it does not close it. The guard
  matches tokens, so a command that locates the files by **content** rather than
  by path or name (`git ls-files | grep review | xargs cat`) carries neither
  token and passes — the one token it does carry, `review`, is a nitpicker
  command name that appears in ordinary commands constantly, so matching it
  would block routine work. Treat `.github/CODEOWNERS` plus branch protection as
  the binding control, not this hook. The same hook also blocks a Bash **write**
  to `scripts/hooks/` or `.claude/settings.json` (`PROTECTED_WRITE`), where
  reading stays allowed — so the enforcement surface cannot be edited around via
  `sed -i` or a redirect. Hand those edits to the owner rather than reaching for
  another spelling.
- matcher `Bash` — `deny-unsafe-git-hook.py`, which blocks `git` with
  `--no-verify` and a push to a protected branch. Per
  `.claude/rules/commit-gate-integrity.md` the pre-commit validators are not
  optional; commit without the flag and fix what fails.
- matcher `Bash` — `guard-ctx-ok-hook.py`, which validates the `# ctx-ok`
  escape hatch from `.claude/rules/use-context-mode.md` and denies it on any
  verb outside its allowlist, including every read verb. Fails closed on an
  unrecognised verb, so a denial usually means route the command through
  context-mode instead — not that the marker was spelled wrong.
- matcher `Bash` — `ask-destructive-restore-hook.py`, which asks before a
  `git checkout --` or `git restore` that would discard uncommitted tracked
  changes. See `.claude/rules/snapshot-before-mutating.md`: snapshot with `cp`
  instead.
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
