# mise Tasks Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Makefile with mise file tasks under `.mise/tasks/`, run CI
and the local prek hooks through them, and move the Claude Code hooks into
`.mise/tasks/hook/`, run through mise by path.

**Architecture:** Each Makefile target becomes one executable file task;
`check` is a script that runs the read-only gates in parallel and then the
tree-writing ones in sequence. Tool versions move to `mise.toml` with a
committed `mise.lock`. The in-tree work lands as agent commits made on the
owner's instruction. The protected surface (hooks, settings, CODEOWNERS)
changes only through a `git format-patch` series the owner applies.

**Tech Stack:** mise 2026.10.1 file tasks, prek 0.5.5, uv 0.13.1, ruff 0.17.1,
pyright 1.1.414 (npm), opengrep 1.27.1, pytest, GitHub Actions
(`jdx/mise-action` v5.2.2).

**Spec:** `docs/superpowers/specs/2026-10-22-mise-tasks-migration-design.md`

## Global Constraints

- mise `2026.10.1`; `jdx/mise-action@8418fedb1110381a0d3ba51a7a415d7c1b884550 # v5.2.2`.
- `mise.toml` holds `[tools]` only: `uv = "0.13.1"`, `ruff = "0.17.1"`,
  `"npm:pyright" = "1.1.414"`, `prek = "0.5.5"`, `opengrep = "1.27.1"`.
  Adding `[env]`, `[settings]` or `[tasks]` would make the file need
  `mise trust`, so none of them go in.
- `mise.lock` covers `linux-x64`, `macos-arm64` and `macos-x64`; CI sets `MISE_LOCKED: "1"`.
- Every task file is executable and carries a description header: `#MISE description="…"`
  in bash, `# [MISE] description="…"` in Python (ruff's preview E265 rejects
  `#MISE`; the bracket form was probed and mise reads it).
- Bash tasks start `#!/usr/bin/env bash` and `set -euo pipefail`, except
  `check` (`set -uo pipefail`, so that one failing phase doesn't skip the other).
- Task names keep the Makefile target names, except `pre-commit` → `prek` and
  `bump-{patch,minor,major}` → `bump <part>`.
- A hook runs only by path, behind
  `MISE_IGNORED_CONFIG_PATHS="$CLAUDE_PROJECT_DIR" MISE_ENV=`.
- Shipped `skills/*/scripts/*.py` stay stdlib-only, run with plain python3.
  Internal scripts run via `uv run --quiet`.
- The owner-only paths are `scripts/hooks/**`, `.claude/settings.json`,
  `.claude/settings.local.json`, `.claude/skills/graphify/.graphify_version`,
  `.git/hooks`, `.github/CODEOWNERS` (by convention) and, after patch 2,
  `.mise/tasks/hook/**`. None of them is edited in this tree: changes to them
  arrive as `*.patch` files in the working directory, built in a scratch clone.
- Never touch the agent-definition tree, `docs/audit/findings/INDEX.md` by
  hand, or `resolved.jsonl`.
- The pre-existing ` M .claude/skills/graphify/.graphify_version` stays out of
  every commit and every patch.
- Commits happen only on the owner's explicit instruction. Stage named paths
  only, run `git status --short` and `git diff --cached --stat` before each
  commit, never use `--no-verify`, and add no trailers.
- Restore any file mutated for a proof with `cp`, then check it with `cmp`.
- Inspection goes through context-mode tools. `Read` is used only right before an `Edit`.

## Review Focus

1. **A fresh clone with no `.venv`.** The parallel phase starts several
   `uv run --extra dev` gates at once, and each must wait on uv's environment
   lock instead of failing. Covered by Task 9 step 2, which runs `check` in a
   new scratch clone.
2. **A read-only gate fails.** The writer phase must still run and `check` must
   exit 1, so one run reports every failure. Covered by
   `test_check_runs_writers_after_a_failed_read_phase` (Task 1).
3. **mise missing from PATH during a hook.** Every guard must exit 2 with
   `mise missing`, never 0. Covered by
   `test_every_hook_command_fails_closed_without_mise` (Task 7).
4. **Planted project mise config** (`mise.local.toml` `[env]`, `.miserc.toml`
   env selection, `.tool-versions`). None of it may reach a hook. Covered by
   `test_project_mise_config_does_not_reach_a_hook` (Task 7).
5. **A task invoked from a subdirectory** (`cd skills && mise run lint`). Tasks
   use repo-relative paths, so they must run from the config root. Covered by
   `test_tasks_run_from_the_repo_root` (Task 1).

---

## File map

| Path | Task | Change |
| --- | --- | --- |
| `mise.toml`, `mise.lock` | 1 | create |
| `.mise/tasks/*` | 1 | create one executable file per task |
| `tests/mise_check.py` | 1 | create: parser for `.mise/tasks/check`, shared by tests |
| `tests/test_mise_tasks.py` | 1 | create |
| `Makefile`, `scripts/check-make-help.py`, `tests/test_check_make_help.py` | 1 | delete |
| `tests/test_hooks.py`, `tests/test_bump_version.py`, `tests/test_check_opengrep.py`, `renovate.json` | 1 | Makefile parsing → task parsing; Renovate `mise` manager |
| `.github/workflows/validate-skills.yml`, `release-please.yml` | 2 | mise-action, `mise run check`, `mise run lock` |
| `tests/test_hooks.py`, `tests/test_check_opengrep.py`, `tests/test_bump_version.py` | 2 | gate guard and pin tests |
| `.pre-commit-config.yaml`, `renovate.json`, `tests/test_hooks.py` | 3 | local hooks call tasks; ruff becomes local |
| docs and config comments (spec §8) | 4 | `make X` → `mise run X` |
| `skills/nitpicker/commands/{cr,execute-plan,contributing,dead-code,deps,agent-hooks}.md`, `skills/nitpicker/scripts/findings.py` comment | 5 | consumer-repo discovery of mise tasks |
| `0001-*.patch` | 6 | owner patch 1: `mise exec` unwrap |
| `0002-*.patch` | 7 | owner patch 2: hook relocation |
| `0003-*.patch` | 8 | owner patch 3: dependent docs |

---

### Task 1: Pins, tasks, and the Makefile's removal (`build:`)

**Files:**

- Create: `mise.toml`, `mise.lock`, `tests/mise_check.py`, `tests/test_mise_tasks.py`
- Create, each mode 755: `.mise/tasks/{check,validate,validate-evals,validate-rules,ring-deps,version-sync,lock-check,lock,lint,format,format-check,security,opengrep,typecheck,test,bench,bench-recall,agentlinter,agentlinter-update,audit-consistency,index-check,prek,list,spec-check,bump,stdlib-only,rules-anatomy,agent-instructions}`
- Delete: `Makefile`, `scripts/check-make-help.py`, `tests/test_check_make_help.py`
- Modify:
  - `tests/test_hooks.py`: `test_make_check_still_covers_every_gate` at L1486,
    `test_every_ruff_call_site_names_the_same_version` at L647,
    `test_renovate_can_see_every_tool_pin_the_sync_tests_enforce` at L811, and
    the `"make check"` case at L567.
  - `tests/test_bump_version.py`: `test_make_check_runs_lock_check` at L185.
  - `tests/test_check_opengrep.py`: the check-membership test at L428.
  - `renovate.json`.

**Interfaces:**

- Produces `tests/mise_check.py::check_phases(root: Path) -> tuple[list[str], list[str]]`,
  which returns `(read_only, writers)` in file order. It joins backslash
  continuations, takes each `mise run` invocation, drops flag tokens (`-…`,
  plus the value after `--jobs`), and splits on `:::`. The first invocation is
  `read_only`; the second is `writers`.
- Produces the task names listed under Files. Tasks 2, 3 and 5 refer to them.

- [ ] **Step 1: Write the failing tests** in `tests/test_mise_tasks.py`:

```python
ROOT = Path(__file__).parent.parent
TASKS = ROOT / ".mise" / "tasks"
READ_ONLY = ["validate", "validate-evals", "validate-rules", "ring-deps", "version-sync",
             "lock-check", "lint", "format-check", "security", "opengrep", "typecheck",
             "test", "bench", "agentlinter", "audit-consistency"]
WRITERS = ["index-check", "prek"]
FORMER_TARGETS = {t: t for t in READ_ONLY + ["index-check", "format", "list", "spec-check",
                  "bench-recall", "agentlinter-update"]} | {
    "pre-commit": "prek", "bump-patch": "bump", "bump-minor": "bump", "bump-major": "bump"}
PINS = {"uv": "0.13.1", "ruff": "0.17.1", "npm:pyright": "1.1.414",
        "prek": "0.5.5", "opengrep": "1.27.1"}
PLATFORMS = {"linux-x64", "macos-arm64", "macos-x64"}

def test_every_task_file_is_executable_and_described():
    files = [p for p in TASKS.iterdir() if p.is_file()]
    assert files
    for p in files:
        assert os.access(p, os.X_OK), p.name
        head = p.read_text(encoding="utf-8").splitlines()[:5]
        assert any(re.match(r'#\s*(\[MISE\]|MISE) description="[^"]+"', ln) for ln in head), p.name

def test_every_former_make_target_resolves_to_a_task():
    for target, task in FORMER_TARGETS.items():
        assert (TASKS / task).is_file(), f"make {target} has no task {task}"

def test_check_runs_every_gate_in_its_phase():
    assert check_phases(ROOT) == (READ_ONLY, WRITERS)

def test_check_continues_past_failures_and_serialises_writers():
    text = (TASKS / "check").read_text(encoding="utf-8")
    assert text.count("--continue-on-error") == 2
    assert "--jobs 1" in text
    assert "set -e" not in text.replace("set -uo pipefail", "")

def test_check_runs_writers_after_a_failed_read_phase(tmp_path):
    # Stub `mise` on PATH: log argv, fail the first call.
    ...  # write tmp_path/"mise" (bash, mode 755) appending "$*" to tmp_path/"log",
         # exiting 1 when the log had no lines before this call, else 0
    r = subprocess.run([str(TASKS / "check")], env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
                       capture_output=True, text=True, cwd=ROOT)
    calls = (tmp_path / "log").read_text().splitlines()
    assert r.returncode == 1
    assert len(calls) == 2 and "index-check" in calls[1] and "prek" in calls[1]

def test_check_exits_0_when_every_gate_passes(tmp_path):
    # same stub, always exit 0
    assert r.returncode == 0

def test_mise_toml_pins_exactly_the_spec_tools():
    cfg = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    assert cfg == {"tools": PINS}

def test_mise_lock_carries_a_checksum_for_every_binary_tool_on_every_platform():
    lock = tomllib.loads((ROOT / "mise.lock").read_text(encoding="utf-8"))
    for name, version in PINS.items():
        entries = lock["tools"][name]
        assert [e["version"] for e in entries] == [version]
        if name.startswith("npm:"):
            continue  # npm backend resolves through the registry, no per-platform asset
        platforms = entries[0]["platforms"]
        assert PLATFORMS <= set(platforms), name
        assert all(platforms[p].get("checksum") for p in PLATFORMS), name

def test_tasks_run_from_the_repo_root(tmp_path):
    r = subprocess.run(["mise", "run", "-q", "list"], cwd=ROOT / "skills", capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
```

`test_tasks_run_from_the_repo_root` gets
`pytest.mark.skipif(shutil.which("mise") is None, reason=…)`, except under `CI`,
where a missing mise must fail. That follows the precedent in
`test_check_agentlinter.py` L160.

- [ ] **Step 2: Run the new tests and confirm they fail.**
  Run `uv run --extra dev pytest tests/test_mise_tasks.py -q`. Expected: FAIL,
  `.mise/tasks` missing.

- [ ] **Step 3: Write `mise.toml`** with the `[tools]` table from Global
  Constraints, then generate the lock with
  `mise lock --platform linux-x64,macos-arm64,macos-x64`. Expected: exit 0, and
  `mise.lock` holds an entry for each tool. If `mise lock` says lockfiles need a
  setting turned on, stop and report it: adding `[settings]` breaks the
  tools-only constraint.

- [ ] **Step 4: Write each task file.** The header is the shebang, then the
  `#MISE description=` line, then the Makefile's rationale comment block for
  that target with `make X` rewritten to `mise run X`, then `set -euo pipefail`,
  then the body. The description comes from the target's old `make help` line.

  | Task | Body |
  | --- | --- |
  | `validate` | `uv run --quiet scripts/validate-skill.py` then `uv run --quiet scripts/validate-skill.py .claude/skills/*/SKILL.md` |
  | `validate-evals`, `validate-rules`, `version-sync`, `opengrep`, `agentlinter`, `list` | `uv run --quiet scripts/<the Makefile's script>` |
  | `ring-deps` | `uv run --quiet scripts/check-ring-deps.py --check .` |
  | `agentlinter-update` | `uv run --quiet scripts/check-agentlinter.py --update` |
  | `lock-check` / `lock` | `uv lock --check` / `uv lock` |
  | `audit-consistency` | `python3 skills/nitpicker/scripts/findings.py validate` |
  | `index-check` | the Makefile recipe with `$$` → `$` and the line continuations removed |
  | `prek` | `prek run --all-files --show-diff-on-failure` |
  | `lint` | `ruff check scripts/ tests/ skills/` |
  | `format` / `format-check` | `ruff format scripts/ tests/ skills/` / with `--check` |
  | `security` | `uv run --extra dev bandit -c pyproject.toml -q -r skills/ scripts/` |
  | `test` | `uv run --extra dev pytest tests/ "$@"` |
  | `typecheck` | `uv run --extra dev pyright --outputjson \| python3 -c` with the Makefile's errorCount one-liner |
  | `bench` / `bench-recall` | `uv run --quiet scripts/bench-retrieval.py --verbose` / `scripts/bench-recall.py --run` |
  | `spec-check` | the Makefile loop over `skills/*/ .claude/skills/*/` with `uvx --quiet --from skills-ref==0.1.1 agentskills validate` |
  | `bump` | `#USAGE arg "<part>" help="patch, minor or major"`, body `uv run --quiet scripts/bump-version.py "$usage_part"` |
  | `stdlib-only` | `uv run --quiet scripts/check-stdlib-only.py` |
  | `rules-anatomy` / `agent-instructions` | `python3 skills/nitpicker/scripts/check-rules-anatomy.py .` / `check-agent-instructions.py .` |
  | `check` | spec §2, verbatim |

  `chmod 755` every file.

- [ ] **Step 5: Write `tests/mise_check.py::check_phases`** as described under Interfaces.

- [ ] **Step 6: Point the old Makefile-parsing tests at the tasks.**
  - `test_make_check_still_covers_every_gate` becomes
    `test_mise_check_still_covers_every_gate`. It asserts its `required` set,
    with `pre-commit` renamed to `prek`, is a subset of
    `set(sum(check_phases(ROOT), []))`.
  - `test_make_check_runs_lock_check` becomes `test_mise_check_runs_lock_check`.
    It asserts `"lock-check" in check_phases(REPO_ROOT)[0]` and that
    `.mise/tasks/lock-check` contains `uv lock --check`.
  - The opengrep check-membership test asserts
    `"opengrep" in check_phases(REPO_ROOT)[0]`.
  - The ruff pin test's `sites` becomes the hook's PEP 723 block,
    `mise.toml: rf'^ruff = "{re.escape(want)}"$'` (`re.M`) and the pre-commit
    rev. Delete the "both writing call sites" Makefile assertion. The format
    tasks now take ruff from mise's PATH, so `mise.toml` is their single pin.
  - The Renovate test's `expected` becomes `{"scripts/hooks/*.py": {"ruff"}}`.
    Add `assert "mise" in cfg["enabledManagers"]`, because mise's own manager
    reads `mise.toml`.
  - The `"make check"` case at L567 becomes `"mise run check"`.

- [ ] **Step 7: Update `renovate.json`.** Add `"mise"` to `enabledManagers`.
  Delete the Makefile custom manager. Rewrite the `customManagers` description
  so it names `mise.toml` (built-in `mise` manager), the PEP 723 block and the
  pre-commit revs.

- [ ] **Step 8: Delete the Makefile, `scripts/check-make-help.py` and
  `tests/test_check_make_help.py`** with `git rm`.

- [ ] **Step 9: Run the suite.** Run
  `uv run --extra dev pytest tests/test_mise_tasks.py tests/test_hooks.py tests/test_bump_version.py tests/test_check_opengrep.py -q`.
  Expected: PASS. The workflow tests still pass, because `validate-skills.yml`
  is unchanged until Task 2.

- [ ] **Step 10: Run the gate twice and compare the tree.** Run
  `git status --short > /tmp/s1; mise run check; git status --short > /tmp/s2; mise run check; git status --short > /tmp/s3; cmp /tmp/s1 /tmp/s2 && cmp /tmp/s2 /tmp/s3`
  (with the `/tmp` paths in the scratchpad). Expected: both runs exit 0 and
  both `cmp` calls succeed. A gate that leaves a new dirty path moves to the
  writer phase.

- [ ] **Step 11: Run `mise tasks`.** Expected: every task is listed with a
  non-empty description.

- [ ] **Step 12: Commit (only on the owner's instruction).** Stage the named
  paths from Files. Message: `build: run the repository gates as mise file tasks`.

### Task 2: CI through `mise run` (`ci:`)

**Files:**

- Modify:
  - `.github/workflows/validate-skills.yml`: delete the `Install uv` and
    `Install opengrep` steps, and change the gate step.
  - `.github/workflows/release-please.yml`: change the setup and relock steps
    in `sync-lockfile`.
  - `tests/test_hooks.py`: the gate guard in L1172–L1484 and the pin test's CI assertion.
  - `tests/test_check_opengrep.py`: `test_ci_installs_opengrep_pinned_and_digest_verified` at L436.
  - `tests/test_bump_version.py`: `test_release_workflow_syncs_the_lockfile` at L196.

**Interfaces:**

- Consumes the `check` and `lock` tasks from Task 1.
- Produces `_gate_violations(validate_job: str) -> list[str]` (the
  `setup_steps` parameter is removed). It returns a violation unless exactly
  one step has a `run:`, that step's tokens are `["mise", "run", "check"]`, and
  every other step is a `uses:` step.

- [ ] **Step 1: Write the failing tests.**
  - `_GATE_STEP = {"name": "Run the repository gate", "run": "mise run check"}`.
  - Rename `test_ci_runs_the_repository_gate_through_make_check` →
    `…_through_mise_run_check` and `test_the_gate_step_must_be_exactly_make_check`
    → `…_exactly_mise_run_check`.
  - Add `test_any_second_run_step_is_a_violation`. It builds
    `_job({"name": "Install opengrep", "run": "curl x | sh"}, _GATE_STEP)` and
    expects a violation.
  - Add `test_validate_job_installs_tools_through_the_pinned_mise_action`. It
    asserts the workflow contains `jdx/mise-action@8418fedb1110381a0d3ba51a7a415d7c1b884550 # v5.2.2`,
    `version: 2026.10.1` and `MISE_LOCKED: "1"`.
  - `test_ci_installs_opengrep_pinned_and_digest_verified` becomes
    `test_opengrep_is_pinned_by_mise_and_locked`. It asserts `mise.toml` pins
    `opengrep = "1.27.1"`, that `mise.lock` has a `linux-x64` checksum for it,
    and that `OPENGREP_VERSION` is absent from the workflow.
  - `test_release_workflow_syncs_the_lockfile` asserts `"mise run lock"` and
    `"cache: false"`, and keeps the `chore: sync uv.lock` assertion.

- [ ] **Step 2: Run them and confirm they fail.** Run
  `uv run --extra dev pytest tests/test_hooks.py -k "gate or run_step or mise_action" tests/test_check_opengrep.py tests/test_bump_version.py -q`.
  Expected: FAIL on the `make check` workflow.

- [ ] **Step 3: Edit `validate-skills.yml`.**
  - Add a job-level `env: MISE_LOCKED: "1"`.
  - Replace the `Install uv` and `Install opengrep` steps with
    `- name: Install mise and the pinned tools`, using the action pin above with
    `with: version: 2026.10.1`.
  - Change the gate step to `run: mise run check`.
  - Rewrite the gate step's comment so it names `.mise/tasks/check` as the
    single definition. Delete the opengrep digest and Renovate notes.

- [ ] **Step 4: Edit `release-please.yml`.** Replace setup-uv with the same
  mise-action pin and `with: { version: 2026.10.1, cache: false }`, and add a
  one-line comment that the job holds `contents: write`. Change
  `run: uv lock` to `run: mise run lock`.

- [ ] **Step 5: Edit `tests/test_hooks.py`.** Delete `GATE_SETUP_STEPS`,
  `_SETUP_COMMANDS`, `_COMMAND_WRAPPERS`, `_command_words` (once nothing calls
  it), `test_a_declared_setup_step_may_not_run_repository_code`,
  `test_command_substitution_cannot_hide_a_command` and
  `test_the_real_install_step_satisfies_the_command_allowlist`. Every remaining
  `_gate_violations(…, GATE_SETUP_STEPS)` call drops its second argument. The
  pin test's CI assertion message says `mise run check`.

- [ ] **Step 6: Run the suite and the workflow linters.** Run
  `uv run --extra dev pytest tests/ -q` and
  `prek run zizmor --files .github/workflows/*.yml` (the zizmor id as
  `.pre-commit-config.yaml` names it). Expected: PASS, and zizmor reports no
  finding.

- [ ] **Step 7: Commit (only on the owner's instruction).**
  `ci: install tools with mise and run the gate as a mise task`

### Task 3: prek hooks call the tasks (`build:`)

**Files:**

- Modify:
  - `.pre-commit-config.yaml`: the local hooks from `validate-skills` through
    `agent-instructions`, and the `astral-sh/ruff-pre-commit` repo at L51.
  - `renovate.json`: the ruff `packageRules` entry.
  - `tests/test_hooks.py`: `test_every_ruff_call_site_names_the_same_version`.

- [ ] **Step 1: Write the failing test.** In the ruff pin test, remove the
  `.pre-commit-config.yaml` rev site and add `test_prek_ruff_hooks_use_the_mise_pin`.
  It parses the config with yaml, finds hook ids `ruff-check` and `ruff-format`
  under `repo: local`, and asserts their entries are
  `mise exec -- ruff check --fix` and `mise exec -- ruff format`, each with
  `types: [python]`. Add `test_local_hooks_call_tasks`, which maps each hook id
  in spec §5's table to its entry `mise run -q <task>` and asserts the `files:`
  filters are unchanged (a frozen dict of the current filters).

- [ ] **Step 2: Run it and confirm it fails.** Run
  `uv run --extra dev pytest tests/test_hooks.py -k "prek or local_hooks or ruff_call" -q`.
  Expected: FAIL.

- [ ] **Step 3: Edit `.pre-commit-config.yaml`.** Each local `language: system`
  hook takes its entry from spec §5. Delete the ruff-pre-commit repo and add
  `ruff-check` and `ruff-format` to `repo: local` (`language: system`,
  `types: [python]`, `require_serial` unset). Add a comment that committing needs `mise` on PATH.

- [ ] **Step 4: Edit `renovate.json`.** The ruff rule's `matchPackageNames`
  becomes `["ruff"]`. Rewrite its description so it names `mise.toml`, the
  pyproject `dev` extra and the PEP 723 block, and drop the `v`-prefix note
  that existed for the pre-commit tag.

- [ ] **Step 5: Run the hooks and the tests.** Run `prek run --all-files` and
  `uv run --extra dev pytest tests/test_hooks.py -q`. Expected: both pass.

- [ ] **Step 6: Commit (only on the owner's instruction).** Stage this commit
  before Task 4 so the hooks judge the docs commit with the new config
  (memory: grouped commits under prek). Message:
  `build: run the local prek hooks through mise tasks`

### Task 4: Prose (`docs:`)

**Files:**

- Modify the spec §8 list as it stands after the move. Each file is in
  `rg -l -e '\bmake [a-z][a-z-]*\b' -e 'Makefile'` and outside the exclusions:
  - `CLAUDE.md`, `AGENTS.md`, `README.md`, `CONTRIBUTING.md`
  - `.github/copilot-instructions.md`, `benchmarks/README.md`, `docs/audit/arch-profile.md`
  - `.claude/rules/{agentlinter-baseline,agent-skills-spec,audit-store,commit-types,github-actions-security,hook-inventory,instruction-budget,pr-fetchers,skill-official-best-practices,suppression-markers,version-bumps,write-surgical-code}.md`
  - `.claude/skills/{README.md,skills/SKILL.md,validate-skills/SKILL.md}`
  - `.codacy.yml`, `.bandit`, `.editorconfig`, `.gitignore`, `.github/codeql/codeql-config.yml`
  - `pyproject.toml` comments
  - the docstrings and messages of `scripts/{bench-recall,bench-retrieval,bump-version,check-agentlinter,check-opengrep,list-skills,validate-skill}.py`
  - the test docstrings that say `make check`
- Do not modify:
  - `.claude/skills/graphify/**` (vendored)
  - `CHANGELOG.md`, `docs/superpowers/**`, `docs/audit/findings/**`
  - `docs/improve-token-usage-report.md`, `.markdownlint.jsonc` and
    `commit-lint.yml`: their hits are the English verb "make"
  - the hook files (patch 2), and `skills/**` (Task 5)

- [ ] **Step 1: Record the always-loaded baseline.** Run
  `python3 skills/nitpicker/scripts/check-agent-instructions.py .` and save the total.

- [ ] **Step 2: Rewrite the prose.** Every `make <target>` becomes
  `mise run <task>`, with renames from Task 1. "the Makefile" becomes
  `.mise/tasks/` or the named task file. `make help` becomes `mise tasks`.
  CLAUDE.md's Development Commands block lists `mise run …` with the same
  comments. `.mise/tasks/` joins each config scope that lists repo paths
  (`.codacy.yml`, `.editorconfig`, codeql `paths`), because those files would
  otherwise skip the new bash tasks.

- [ ] **Step 3: Check that nothing was missed.** Run
  `rg -n -e '\bmake [a-z][a-z-]*\b' -e 'Makefile' --hidden -g '!.git' -g '!graphify-out' -g '!CHANGELOG.md' -g '!docs/superpowers' -g '!docs/audit/findings' -g '!.claude/skills/graphify' -g '!scripts/hooks' -g '!skills'`.
  Expected: only the English-verb hits listed above.

- [ ] **Step 4: Check the instruction budget and the gate.** Re-run
  check-agent-instructions. Expected: the total does not exceed the Step 1
  baseline. Then run `mise run check`. Expected: exit 0. If
  `.agentlinter-baseline.json` fingerprints moved, run
  `mise run agentlinter-update` and include the file.

- [ ] **Step 5: Commit (only on the owner's instruction).**
  `docs: name the mise tasks instead of make targets`

### Task 5: Consumer-repo discovery of mise tasks (`feat:`)

**Files:**

- Modify: `skills/nitpicker/commands/cr.md` (step 4, L64), `execute-plan.md`
  (step 3, L38), `contributing.md` (L21, L22, L36, L91), `dead-code.md` (L20),
  `deps.md` (L48 and the tool-manifest list), `agent-hooks.md` (L58).
- Modify: `skills/nitpicker/scripts/findings.py` L2680, the comment only.
  Leave `_PROJECT_MARKERS` unchanged.

- [ ] **Step 1: Run the RED pressure scenario.** Use the skill-tester skill
  with a fixture repo whose only gate is `.mise/tasks/check`, and give it the
  prompt "run /nitpicker execute-plan on this plan: identify the check command".
  Expected: without the change, the agent does not name `mise run check`.

- [ ] **Step 2: Edit the files per spec §7.** The discovery order is
  `Makefile` → mise tasks (`mise.toml`/`.mise.toml` `[tasks]`, `.mise/tasks/`,
  `mise-tasks/`, `.config/mise/tasks/`; `check`/`test`/`lint`) → `package.json`
  scripts → `pyproject.toml` → README/CONTRIBUTING. Use the same wording in
  `cr.md` and `execute-plan.md`. In `contributing.md`, the rationalization at
  L91 gains `` a documented `mise run setup` is verified by finding the task ``.

- [ ] **Step 3: Run GREEN.** Re-run the Step 1 scenario. Expected: the agent
  names `mise run check`. Then run
  `mise run validate && uv run --extra dev pytest tests/test_validate_skill.py -q`.
  Expected: PASS.

- [ ] **Step 4: Commit (only on the owner's instruction).**
  `feat: discover mise tasks as a consumer repo's check command`. The squash PR
  title must also be `feat:`.

### Task 6: Owner patch 1, the `mise exec` unwrap

**Files (in the scratch clone):**

- `scripts/hooks/_hooklib.py`: `_WRAPPERS` and its unwrap logic.
- `tests/test_hooks.py`.
- `.claude/rules/commit-gate-integrity.md`.

- [ ] **Step 1: Make the scratch clone.** Do this after Tasks 1–5 are committed:
  `git clone -q --no-local --branch chore/move-to-mise-managed-tasks /home/ivuorinen/Code/ivuorinen/skills <scratchpad>/patch-clone`.
  Every later step runs inside it, with `cd <abs> || exit 1`.

- [ ] **Step 2: Write the failing test.** Add
  `test_git_guard_judges_the_command_behind_mise_exec`, parametrized over:
  - `mise exec -- git commit --no-verify -m x` → 2
  - `mise x -- git commit -n -m x` → 2
  - `mise exec --env ci -C . -- git commit --no-verify` → 2
  - `mise exec node@20 -- git commit --no-verify` → 2
  - `mise x -- git status` → 0
  - `mise run check` → 0

  Assert with `deny-unsafe-git-hook` and the existing `_run` helper.

- [ ] **Step 3: Run it and confirm it fails.** Run
  `uv run --extra dev pytest tests/test_hooks.py -k mise_exec -q`. Expected:
  the deny cases FAIL with exit 0.

- [ ] **Step 4: Implement.** `_hooklib` treats `mise` followed by `exec` or `x`
  as a wrapper: it skips tokens up to the first standalone `--` and judges the
  rest as a stage. A `mise exec` with no `--` is judged on the tokens after its
  tool specs, the same way the existing wrappers handle a missing separator.
  The test cases fix the behaviour.

- [ ] **Step 5: Edit `commit-gate-integrity.md`.** Add `mise exec`/`mise x` to
  the wrappers it describes, and add `mise run <task>` to the indirections the
  guard sees only by name.

- [ ] **Step 6: Verify and export.** Run `mise run check` in the clone.
  Expected: exit 0. Commit in the clone with
  `fix: judge the command behind mise exec in the git guard`, then run
  `git format-patch -1 -o /home/ivuorinen/Code/ivuorinen/skills` and rename
  the output to `0001-mise-exec-unwrap.patch`.

### Task 7: Owner patch 2, the hook relocation

**Files (in the same clone, on top of patch 1):**

- Move: every file under `scripts/hooks/` → `.mise/tasks/hook/` (`git mv`).
  Leave out `__pycache__/`.
- Create: `.mise/tasks/hook/graphify-guard`.
- Modify:
  - `.mise/tasks/hook/_hooklib.py`: `parents[2]` → `parents[3]` at L270 and
    L289, and the docstring at L274.
  - Each hook `.py`: add `# [MISE] description="…"` after the shebang, and
    change its `report_skip` hints and `_BY_HAND` from `make X` to `mise run X`.
  - `.mise/tasks/hook/deny-agents-path-hook.py` (`PROTECTED_WRITE`) and
    `enforcement-surface-integrity.py` (`SURFACE`): `"scripts/hooks"` →
    `".mise/tasks/hook"`.
  - `.claude/settings.json` (every hook command and `permissions.deny`) and `.github/CODEOWNERS`.
  - The `.claude/rules/hook-inventory.md` surface list.
  - `scripts/check-ring-deps.py` (`RINGS` hooks glob → `.mise/tasks/hook/**/*.py`,
    plus the L11 docstring and the L127 comment).
  - `pyproject.toml` (coverage `source`, and every other `scripts/hooks` scope)
    and `renovate.json` (the PEP 723 glob).
  - The `.mise/tasks/{lint,format,format-check,security}` scopes gain `.mise/tasks/hook/`.
  - Tests: `tests/{test_hooks,test_settings,test_check_ring_deps,test_bandit_config,test_validate_audit_findings_hook,test_check_stdlib_only}.py`.

**Interfaces:**

- The hook command forms in `settings.json` are below. `<file>` is the hook's
  filename. `<msg>` is the existing message with `uv` replaced by `mise`.
  - Guard form, used by each PreToolUse guard and the integrity check:
    `command -v mise >/dev/null 2>&1 || { echo '<msg>' >&2; exit 2; }; MISE_IGNORED_CONFIG_PATHS="$CLAUDE_PROJECT_DIR" MISE_ENV= mise run -q "$CLAUDE_PROJECT_DIR/.mise/tasks/hook/<file>"; rc=$?; [ $rc -eq 0 ] || [ $rc -eq 2 ] || { echo '<existing failed-to-run msg>' >&2; rc=2; }; exit $rc`
  - Plain form, used by PostToolUse, Stop and graphify-guard: the same
    `command -v` line and prefix, then
    `mise run -q "$CLAUDE_PROJECT_DIR/.mise/tasks/hook/<file>"` with no exit
    mapping. graphify-guard takes the plain form so it keeps the exits
    `graphify hook-guard` returns, as the inline `exec` did.

- [ ] **Step 1: Write the failing tests.**
  - `test_settings.py`: `HOOKS_DIR = REPO_ROOT / ".mise" / "tasks" / "hook"`.
    The deny entries become `Edit(./.mise/tasks/hook/**)` and
    `Write(./.mise/tasks/hook/**)`. The L393 matcher looks for
    `$CLAUDE_PROJECT_DIR/.mise/tasks/hook/`.
  - Add `test_every_hook_command_ignores_project_mise_config`. Each command
    naming `.mise/tasks/hook/` contains
    `MISE_IGNORED_CONFIG_PATHS="$CLAUDE_PROJECT_DIR" MISE_ENV= mise run -q "$CLAUDE_PROJECT_DIR/.mise/tasks/hook/`
    and runs by path, never as `hook:`.
  - Add `test_the_hook_dir_is_on_every_protection_list`. `.mise/tasks/hook` is
    in `PROTECTED_WRITE`, in `SURFACE`, as both deny entries, as a
    `/.mise/tasks/hook/` CODEOWNERS line, and in `hook-inventory.md`.
    `scripts/hooks` is in none of them.
  - Add `test_every_hook_file_is_a_described_task`. Each executable `*.py` in
    `HOOKS_DIR` has a `# [MISE] description=` line. `_hooklib.py` is mode 644.
  - `test_hooks.py`: `HOOKS_DIR = Path(__file__).parent.parent / ".mise" / "tasks" / "hook"`.
    `SCRIPTS_DIR` becomes `ROOT / "scripts"`, defined explicitly (it was
    `HOOKS_DIR.parent`). Every `scripts/hooks` literal becomes `.mise/tasks/hook`.
  - Add `test_every_hook_command_fails_closed_without_mise`. For each guard-form
    command, run `[shutil.which("bash"), "-c", command]` with `PATH` set to an
    empty `tmp_path` (`command -v` and `echo` are builtins) and
    `CLAUDE_PROJECT_DIR` set to the repo root. Assert rc 2 and `mise` in stderr.
  - Add `test_project_mise_config_does_not_reach_a_hook`, skipped without mise
    except under CI. Make a tmp project with `.mise/tasks/hook/probe` (prints
    `$PROBE` and `$MISE_ENV`), a `mise.local.toml` with `[env] PROBE = "leak"`,
    and a `.miserc.toml` with `env = ["dev"]`. Run the guard-form prefix with
    `CLAUDE_PROJECT_DIR=<tmp>`, and assert the output carries neither `leak`
    nor `dev`.
  - Add `test_graphify_guard_rejects_an_unknown_mode`: `graphify-guard bogus` → rc 2.
  - `test_check_ring_deps.py`: fixture paths `scripts/hooks/…` →
    `.mise/tasks/hook/…`, and `../../../scripts/hooks` → `../../../.mise/tasks/hook`.
    The import-spelling cases in `TestRelativeImports` that target the hooks
    ring (`from .hooks import _hooklib`, `from .....scripts.hooks import _hooklib`)
    can't reach `.mise/tasks/hook` by any dotted name. Retarget them to the
    outward shipped → internal edge (`skills/x/scripts/sub/a.py:
    from .....scripts.helper import x` with `scripts/helper.py`, ring
    `internal`), and keep the bare-stem case (`import _hooklib` from
    `scripts/foo.py` → `hooks`). The pinned live edge becomes
    `.mise/tasks/hook/validate-audit-findings-hook.py -> skills/nitpicker/scripts/findings.py`.
  - `test_bandit_config.py` L92: `.mise/tasks/hook/` is in the scanned set.
  - `test_validate_audit_findings_hook.py` L11 `HOOK_PATH`, and the
    `test_check_stdlib_only.py` reference, move to the new path.

- [ ] **Step 2: Run them and confirm they fail.** Run
  `uv run --extra dev pytest tests/test_settings.py tests/test_hooks.py tests/test_check_ring_deps.py -q`.
  Expected: FAIL, hooks dir missing.

- [ ] **Step 3: Move the hooks.** Run
  `git mv scripts/hooks/<each tracked file> .mise/tasks/hook/`, naming the
  files from `git ls-files scripts/hooks` with no glob. Remove `scripts/hooks`
  if it is left empty. Edit `_hooklib.py`'s parents
  and the per-hook headers and hints.

- [ ] **Step 4: Write `graphify-guard`.** This bash task (mode 755) carries
  `#MISE description="graphify hook-guard behind the pinned-version check"` and
  `#USAGE arg "<mode>" help="search or read"`. Its body is the current inline
  settings command with `exec graphify hook-guard "$usage_mode"`. Before that,
  add `case "$usage_mode" in search|read) ;; *) echo "graphify-guard: mode must be search or read" >&2; exit 2;; esac`.
  The pin-mismatch message is kept verbatim.

- [ ] **Step 5: Rewrite the protection surfaces.** Rewrite `settings.json` to
  the command forms above and update its deny entries. Then update
  `PROTECTED_WRITE`, `SURFACE`, CODEOWNERS (`/.mise/tasks/hook/ @ivuorinen`),
  the `hook-inventory.md` list, ring-deps, pyproject, renovate and the task scopes.

- [ ] **Step 6: Run the tests and the gate.** Run
  `uv run --extra dev pytest tests/ -q`, then
  `env -u CLAUDE_PROJECT_DIR -u REPO_ROOT mise run check`. Expected: both pass.

- [ ] **Step 7: Run the by-path smoke test.** For each PreToolUse guard, pipe a
  crafted event through the new settings command, run with `bash -c`. The
  events and expected exits:
  - `{"tool_input":{"command":"git commit --no-verify -m x"}}` → 2
  - `{"tool_input":{"command":"git status"}}` → 0
  - `{"tool_input":{"command":"touch .mise/tasks/hook/x.py"}}` → 2, through
    deny-agents-path (a Bash guard; the Write tool is covered by
    `permissions.deny`)
  - `{"tool_input":{"command":"touch mise.toml"}}` → 0

  Then check the mode bits with `git ls-files -s .mise/tasks/hook`. Expected:
  `100755` for each task and `100644` for `_hooklib.py`.

- [ ] **Step 8: Commit in the clone and export.** Commit with
  `refactor: run the Claude Code hooks as mise tasks from .mise/tasks/hook`,
  then run `git format-patch -1` into the working directory as
  `0002-hook-relocation.patch`.

### Task 8: Owner patch 3, the dependent docs

**Files (in the clone, on top of patch 2):**

- `.claude/rules/{hook-inventory,enforcement-surface-owner,hooks-fail-closed,snapshot-before-mutating,use-uv-runner,mcp-stale-server,counts-in-prose}.md`
- `CLAUDE.md` (the Configuration hooks section and the root-resolution paragraph)
- `AGENTS.md` ("Internal dev tooling" line)
- `CONTRIBUTING.md`, `.github/copilot-instructions.md`, `docs/audit/arch-profile.md`
- `skills/nitpicker/commands/{agent-hooks,agent-loopholes}.md`, wherever they
  cite this repo's `scripts/hooks/` as the example

- [ ] **Step 1: Rewrite the references.** Every `scripts/hooks/` becomes
  `.mise/tasks/hook/`. `uv run --quiet "$CLAUDE_PROJECT_DIR/scripts/hooks/…"`
  examples become the guard form. `hooks-fail-closed.md` names
  `mise missing`. `enforcement-surface-owner.md` names `.mise/tasks/hook/`, and
  says why the project mise config needs no protection (the ignore prefix).

- [ ] **Step 2: Check that nothing was missed.** Run
  `rg -n 'scripts/hooks' --hidden -g '!.git' -g '!graphify-out' -g '!CHANGELOG.md' -g '!docs/superpowers' -g '!docs/audit/findings'`.
  Expected: no hits. Then re-run check-agent-instructions; the total must not
  exceed Task 4's baseline. Then `mise run check`; expected: exit 0.

- [ ] **Step 3: Commit in the clone and export.** Patch 3 touches `skills/`
  only in example prose that changes no directive, so its type is `docs:`.
  Commit with `docs: point the hook references at .mise/tasks/hook`, then
  export `0003-hook-docs.patch`.

### Task 9: Verification and handoff

- [ ] **Step 1: Check the patch series applies.** In a second fresh clone of
  the branch HEAD, run `git am 0001-*.patch 0002-*.patch 0003-*.patch`.
  Expected: it applies cleanly.

- [ ] **Step 2: Run the gate from a fresh environment.** In that clone, with no
  `.venv`, run `env -u CLAUDE_PROJECT_DIR -u REPO_ROOT mise run check` twice,
  comparing `git status --short` before and after each run. Expected: both runs
  exit 0 with an identical status (Review Focus 1).

- [ ] **Step 3: Refresh the graph and memory.** Run `graphify update .` in the
  real repo through ctx_execute (`cd <abs> || exit 1`). Update the memories
  that say `make check` so they say `mise run check`: the
  `repo-shell-and-hook-gotchas`, `opengrep-gate-and-suppression-markers` and
  `agentlinter-evaluated-and-declined` files. Check for others with `rg -l
  'make check' <memory dir>`.

- [ ] **Step 4: Push and watch CI (only on the owner's instruction).** Expected:
  the `Validate` job passes on the PR, running `mise run check` under
  `MISE_LOCKED=1`.

- [ ] **Step 5: Report to the owner.**
  - The commit list.
  - The patch paths and their apply order.
  - Which commits must wait for the owner. Until patch 2 lands, the hooks
    still run from `scripts/hooks` under uv, which keeps working: nothing in
    Tasks 1–5 removes `uv` or the hooks.
  - That the PR title must be `feat:`.
  - That the first Renovate PR against `mise.toml` shows whether the hosted app
    can refresh `mise.lock`.
