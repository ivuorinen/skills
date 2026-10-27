# Design: move the Makefile, CI, prek hooks and agent hooks to mise file tasks

**Date:** 2026-10-22
**Branch:** `chore/move-to-mise-managed-tasks`
**Status:** Spec approved 2026-10-23. §6's protected-config list was amended at
plan time (see Evidence) and needs the owner's review.

## Goal

One task runner for every way this repository is checked. Every Makefile target
becomes a mise file task under `.mise/tasks/`, the Makefile is deleted, CI and
the local prek hooks call those tasks, and the Claude Code hooks move into
`.mise/tasks/hook/` and run through mise.

## Decisions made with the owner

| Fork | Decision |
| --- | --- |
| Hook layout | Relocate the hook scripts into `.mise/tasks/hook/` (not thin wrappers around `scripts/hooks/`) |
| `check` semantics | Read-only gates in parallel, then the tree-writing gates sequentially; report every failure |
| Task directory | `.mise/tasks/` |
| Tool pins | `mise.toml` `[tools]` with a committed `mise.lock` |
| Hook runner | prek, not pre-commit |
| Shipped commands | Teach consumer-repo discovery about mise tasks in this change |
| Delivery | One branch: in-tree commits by the agent, plus an owner-applied patch series for the protected surface |

## Evidence gathered during design

Probes ran in throwaway directories under the session scratchpad with mise
2026.10.1.

- `mise run` forwards stdin, keeps the task's stdout clean, and preserves exit
  code 2. It adds one `[task] ERROR task failed` line on stderr.
- Cost: about 180 ms per `mise run`, against about 38 ms for `uv run` of an
  empty PEP 723 script.
- Only executable files in a task directory become tasks. A mode-644
  `_hooklib.py` and `__pycache__/` are ignored, and a hook task can import a
  sibling module from its own directory.
- `mise run --continue-on-error a ::: b` runs every task and exits non-zero
  when any failed.
- `deny-unsafe-git-hook.py` allows `mise exec -- git commit --no-verify` and
  `mise x -- git commit -n` today (exit 0). Plain `git commit --no-verify` is
  denied (exit 2).
- Config can change a task without touching its file:

  | Agent-writable change | `mise run hook:g` (by name) | `mise run ./.mise/tasks/hook/g` (by path) |
  | --- | --- | --- |
  | `mise.toml` `[env]`, including `CLAUDE_PROJECT_DIR` | injected | injected |
  | `mise.local.toml` `[env]` | injected | injected |
  | `mise.toml` `[tasks."hook:g"] run = …` | task replaced | real task runs |
  | `mise.toml` `[task_config] includes = ["evil"]` | task replaced | real task runs |

- (Added at plan time.) The project config files mise 2026.10.1 loads go well
  past `mise.toml`: `mise.local.toml`, `.mise.toml`, `.mise.local.toml`,
  `mise/config{,.local}.toml`, `.mise/config{,.local}.toml`,
  `.config/mise{,.local}.toml`, `.config/mise/config{,.local}.toml` and
  `.config/mise/conf.d/*.toml`. On top of those, `.tool-versions` and idiomatic
  files (`.node-version` switched `node` on PATH) load too. A project
  `.miserc.toml` holding `env = ["dev"]` selects an env with `MISE_ENV` unset,
  so `mise.dev.toml`, `.mise.dev.toml` and `.mise/config.dev.toml` load as well.
  The prefix matcher behind `PROTECTED_WRITE` can't name an open-ended set like
  `mise.<env>.toml`.
- `MISE_IGNORED_CONFIG_PATHS="<project dir>" MISE_ENV= mise run -q <path>` loads
  none of them: every `[env]` value drops away, and `jq` and `node` resolve to
  the user-level versions. The by-path task still runs with exit 0. A
  `.miserc.toml` that sets `ignored_config_paths = []` and `ceiling_paths = []`
  does not undo it.
- A `mise.toml` holding only plain `[tools]` versions needs no `mise trust`, and
  `mise run`/`mise install` trust their active config automatically.
- Renovate's `mise` manager updates `mise.toml` and can refresh `mise.lock`, but
  refreshing the lock is an "unsafe execution" a self-hosted instance must
  allowlist. Whether the hosted app does is unknown.
- prek reads `.pre-commit-config.yaml` unchanged and is already the installed
  git hook in this checkout.

## §1 Task layout

One executable file per task under `.mise/tasks/`, each carrying
`#MISE description="…"`. Bash tasks start with `set -euo pipefail`. The
rationale comments now above each Makefile recipe move into the task file they
describe. Task names keep the Makefile target names.

| Makefile target | Task | In `check` |
| --- | --- | --- |
| `validate`, `validate-evals`, `validate-rules`, `ring-deps`, `version-sync`, `lock-check`, `lint`, `format-check`, `security`, `opengrep`, `typecheck`, `test`, `bench`, `agentlinter`, `audit-consistency` | same name | read-only phase |
| `index-check` | same name | writer phase |
| `pre-commit` | `prek` | writer phase |
| `format`, `list`, `spec-check`, `bench-recall`, `agentlinter-update` | same name | no |
| `bump-patch`, `bump-minor`, `bump-major` | `bump` with `#USAGE arg "<part>"` | no |
| (none) | `lock` (`uv lock`), `stdlib-only`, `rules-anatomy`, `agent-instructions` | no; all but `lock` reach `check` through `prek` |
| `help`, `make-help`, `all` | deleted | — |

`scripts/check-make-help.py` and `tests/test_check_make_help.py` are deleted:
`mise tasks` lists every task from its own description, so there is no second
copy of the target list to keep in step.

## §2 `check`

`.mise/tasks/check` is a script, not a `depends` list: a failing dependency
stops a `depends` run, and `--continue-on-error` is a CLI flag no task header
can set.

```bash
#!/usr/bin/env bash
#MISE description="The full gate: read-only checks in parallel, then the tree-writing ones"
set -uo pipefail
rc=0
mise run --continue-on-error \
  validate ::: validate-evals ::: validate-rules ::: ring-deps ::: version-sync \
  ::: lock-check ::: lint ::: format-check ::: security ::: opengrep \
  ::: typecheck ::: test ::: bench ::: agentlinter ::: audit-consistency || rc=1
# Writers last and one at a time: prek's fixers and the INDEX.md regeneration
# rewrite files the gates above read.
mise run --jobs 1 --continue-on-error index-check ::: prek || rc=1
exit "$rc"
```

The writer phase runs even when the read-only phase failed, so one run reports
every failing gate. This file is the single definition of the gate; the test
that parsed the Makefile's `check:` rule parses it instead.

Some gates now run concurrently for the first time. Verification runs `check`
twice and compares `git status` before and after; a gate that writes moves to
the writer phase.

## §3 Tool pins

```toml
[tools]
uv = "0.13.1"
ruff = "0.17.1"
"npm:pyright" = "1.1.414"
prek = "0.5.5"
opengrep = "1.27.1"
```

- `mise.lock` is committed, generated for `linux-x64`, `macos-arm64` and
  `macos-x64`, and carries URLs and checksums. CI installs with
  `MISE_LOCKED=1`, so an incomplete lock fails the job.
- Tasks call tools by name (`ruff format`, `prek run`, `opengrep`); `mise run`
  puts the pinned versions on PATH. `typecheck` runs
  `uv run --extra dev pyright --outputjson | …` so uv syncs the venv pyright
  reads, then executes mise's pyright from PATH.
- `npm:pyright` uses the node the runner already provides for agentlinter.
- Unchanged pins: bandit and pytest in pyproject's `dev` extra (bandit is not in
  mise's registry), ruff in the `dev` extra (`ruff-hook.py`'s tests execute the
  real binary), the hooks' PEP 723 blocks, `skills-ref==0.1.1` in `spec-check`,
  and the agentlinter npx pin in `scripts/check-agentlinter.py`.
- The `uv run --with pre-commit==4.7.0`, `--with pyright==…` and
  `--with ruff==…` invocations are removed.
- Renovate: `mise` joins `enabledManagers`; the `Makefile` custom manager is
  removed; the PEP 723 manager glob follows the hooks to
  `.mise/tasks/hook/*.py` (§6).

Risk: if Renovate cannot refresh `mise.lock`, its bump PRs fail
`MISE_LOCKED=1` in CI and need a manual `mise lock`. That failure is loud,
matching the existing rule that half an update cannot merge. The first Renovate
PR against `mise.toml` settles it.

## §4 CI

`validate-skills.yml`, Validate job:

- `Install uv` and `Install opengrep` are replaced by
  `jdx/mise-action@8418fedb1110381a0d3ba51a7a415d7c1b884550 # v5.2.2` with
  `version: 2026.10.1` and env `MISE_LOCKED: "1"`.
- The gate step is `run: mise run check`.
- The opengrep version/sha256 block and its Renovate note are deleted.
- `tests/test_hooks.py`: `GATE_SETUP_STEPS`, `_SETUP_COMMANDS`,
  `_COMMAND_WRAPPERS` and the tests that exercise the setup-step allowlist are
  deleted, since no setup step runs a `run:` body any more. The gate guard
  asserts exactly one `run:` step whose tokens are `["mise", "run", "check"]`;
  its smuggling tests switch their fixtures from `make check` to
  `mise run check`.

`release-please.yml`, lock-sync job: `setup-uv` is replaced by `mise-action`
with `cache: false` (the job holds `contents: write`), and `run: uv lock`
becomes `run: mise run lock`.

Unchanged: `commit-lint.yml` and `pr-title.yml` judge PR metadata with inline
Python that reads its regex from the base SHA. A task file comes from the PR's
own tree, so moving that logic into a task would let a PR rewrite the check that
judges it. `codeql.yml` has no `run:` steps.

## §5 The prek hooks

Local `language: system` hooks call tasks; their `files:` filters are unchanged.

| Hook id | New entry |
| --- | --- |
| `validate-skills` | `mise run -q validate` (now also covers `.claude/skills/*/SKILL.md`, as `make validate` did) |
| `validate-evals` | `mise run -q validate-evals` |
| `validate-rules` | `mise run -q validate-rules` |
| `version-sync` | `mise run -q version-sync` |
| `findings-store` | `mise run -q audit-consistency` |
| `stdlib-only-tools` | `mise run -q stdlib-only` |
| `rules-anatomy` | `mise run -q rules-anatomy` |
| `agent-instructions` | `mise run -q agent-instructions` |

`ruff-check` and `ruff-format` move from the `astral-sh/ruff-pre-commit` repo
to local `language: system` hooks with `entry: mise exec -- ruff check --fix`
and `entry: mise exec -- ruff format`, `types: [python]`. This drops the
pre-commit `rev:` copy of the ruff pin; the pin-consistency test now covers
`mise.toml`, the pyproject `dev` extra and the hook's PEP 723 block.

Unchanged: pre-commit-hooks (prek runs its built-in Rust versions),
markdownlint-cli2, yamllint, bandit, check-jsonschema, zizmor and gitleaks are
pinned only by their `rev:` and run in prek-managed environments, so moving them
adds a pin without removing one. The `pygrep` commit-msg
hooks have no command to wrap. Committing requires `mise` on PATH.

## §6 Hook relocation (owner patch 2)

One commit, built in a scratch clone, so the protection never covers only the
old path:

- `git mv scripts/hooks/* .mise/tasks/hook/`, filenames kept. Executable
  `*.py` become tasks; `_hooklib.py` stays mode 644 and is not one.
  `SHIPPED_ROOT` and the root fallback in `_hooklib.py` move from `parents[2]`
  to `parents[3]`.
- `.claude/settings.json` runs every hook by path:
  `command -v mise >/dev/null 2>&1 || { echo '<hook>: mise missing' >&2; exit 2; }; MISE_IGNORED_CONFIG_PATHS="$CLAUDE_PROJECT_DIR" MISE_ENV= mise run -q "$CLAUDE_PROJECT_DIR/.mise/tasks/hook/<file>"; rc=$?; [ $rc -eq 0 ] || [ $rc -eq 2 ] || rc=2; exit $rc`
  for each PreToolUse guard and the integrity check; PostToolUse and Stop hooks
  keep the `mise missing` line and the ignore prefix without the exit-code
  mapping, as their `uv` form does today. The prefix stays inline because it
  handles mise itself being absent or crashing.
- The two variables make a hook run ignore all project mise config: the by-path
  run sidesteps `[tasks]` overrides, and this sidesteps `[env]`, `[tools]` and
  version files. The protected surface therefore grows by `.mise/tasks/hook/`
  alone, added to `PROTECTED_WRITE`, `permissions.deny`, `.github/CODEOWNERS`,
  `enforcement-surface-integrity.SURFACE` and `hook-inventory.md`. `mise.toml`
  and `mise.lock` stay agent-writable, the same as the Makefile pins they
  replace. (This replaces an earlier list of mise config names to protect,
  which the plan-time probe showed was incomplete and could not be written
  for `mise.<env>.toml`.)
- The inline graphify pin check moves to `.mise/tasks/hook/graphify-guard`, a
  bash task taking `search` or `read`.
- New tests: `.mise/tasks/hook` appears in each of those lists, and every
  settings.json command that runs a hook task carries the ignore prefix.
- Moving with them: `tests/test_hooks.py`, `tests/test_settings.py`,
  `tests/test_check_ring_deps.py`, `scripts/check-ring-deps.py` ring roots, the
  pyproject bandit and ruff scopes, the Renovate PEP 723 glob, and the
  `report_skip` hints (`make validate` → `mise run validate`, and so on).

Patch 1, applied first and independent of the rest: `_hooklib` treats
`mise exec|x [options] -- <cmd>` as a wrapper and judges `<cmd>`, closing the
`--no-verify` bypass above. `commit-gate-integrity.md` adds `mise run <task>`
to the indirections the guard sees only by name.

Patch 3: the documentation that depends on patches 1 and 2
(`hook-inventory.md`, `enforcement-surface-owner.md`, `hooks-fail-closed.md`,
`snapshot-before-mutating.md` examples, the CLAUDE.md hooks section).

Cost: each guard adds about 180 ms of mise ahead of the `uv` its shebang
already invokes. A by-path run gains nothing from mise beyond tools on PATH,
which the hooks do not need.

## §7 Shipped command files

Discovery of a consumer repo's commands learns mise tasks: `mise.toml` and
`.mise.toml` `[tasks]`, and the file-task directories `.mise/tasks/`,
`mise-tasks/` and `.config/mise/tasks/`.

| File | Change |
| --- | --- |
| `commands/cr.md` step 4, `commands/execute-plan.md` step 3 | Order: `Makefile` → mise tasks (`check`/`test`/`lint`) → `package.json` scripts → `pyproject.toml` → README/CONTRIBUTING |
| `commands/contributing.md` | Setup and build tables and the verify-each-claim step name mise tasks; the rationalization example gains a mise counterpart |
| `commands/dead-code.md` | Entry points include a mise task |
| `commands/deps.md` | The Python row's invocation list adds mise tasks; `mise.toml` `[tools]` counts as a tool manifest |
| `commands/agent-hooks.md` | The pass/fail runner list adds `mise run check` |

`findings.py` `_PROJECT_MARKERS` is unchanged: `.git` already locates the root.
This is the only change under `skills/`, so it is a `feat:` commit and the
squash PR title must be `feat:`.

## §8 Docs, tests, verification

Docs: every `make X` becomes `mise run X` and every Makefile reference is
rewritten in `CLAUDE.md`, `AGENTS.md`, `README.md`, `CONTRIBUTING.md`,
`.github/copilot-instructions.md`, `benchmarks/README.md`,
`docs/audit/arch-profile.md`, the `.claude/rules/` files that name a target, the
internal skills under `.claude/skills/` (vendored `graphify` excepted), the
config comments in `pyproject.toml`, `renovate.json`, `.codacy.yml`, `.bandit`,
`.editorconfig`, `.gitignore` and `.github/codeql/codeql-config.yml`, and the
docstrings and messages of `scripts/*.py`. `.mise/tasks/` joins every scope that
lists paths. `.agentlinter-baseline.json` is re-recorded only if fingerprints
move. Dated design records, `CHANGELOG.md` and vendored content stay as written.
The always-loaded files change wording only, and
`check-agent-instructions.py` confirms no directive was added.

Tests: deleted as listed in §1 and §4; rewritten where they parsed the Makefile
or matched `make check`; new ones assert every `.mise/tasks/*` file is
executable and carries a `#MISE description=`, and that each former target
name resolves to a task.

Verification:

1. `mise run check` passes twice with identical `git status` before and after.
2. `mise tasks` lists every task with a description; `prek run --all-files`
   passes.
3. Patches: a scratch clone holding the branch HEAD plus the current
   uncommitted tree, `git am` patches 1–3, `mise run check` with
   `CLAUDE_PROJECT_DIR` and `REPO_ROOT` unset; a crafted event piped to each
   relocated guard by path returns the same exit as before; a write under
   `.mise/tasks/hook/` is denied; a planted `mise.local.toml` `[env]` value
   does not reach a hook; new task files carry their mode bit.
4. CI passes on the PR; `graphify update .` after code changes.

Commits, each staging explicit paths and made only on the owner's instruction:
`build:` pins and tasks, `ci:` the workflows, `build:` prek hooks, `docs:` the
prose, `feat:` discovering mise tasks, with the Makefile removed once the tasks
replace it. Patches 1–3 are written to the working directory as `*.patch`.
