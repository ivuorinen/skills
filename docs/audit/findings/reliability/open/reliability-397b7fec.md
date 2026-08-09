---
id: reliability-397b7fec
auditor: reliability
severity: medium
category: reliability
area: scripts/hooks/post-bash-revalidate.py
status: open
found: 2026-08-09
---

# PostToolUse and Stop hooks shell out with no timeout and no tool preflight, so a slow or absent uv hangs or crashes the session

## Problem

Eleven of the seventeen `subprocess.run` call sites in the repo pass no `timeout=`, and all eleven are in `scripts/hooks/`. `post-bash-revalidate.py` is the worst case: it runs six gate subprocesses, four of them `uv run`, unbounded, on every Bash command that dirties a governed path. It also never preflights that `uv` exists, so an absent binary raises an uncaught `FileNotFoundError`.

## Evidence

AST scan of every `subprocess.run` in `scripts/` and `skills/`:

```text
scripts/hooks/ask-destructive-restore-hook.py:110  timeout=True
scripts/hooks/deny-unsafe-git-hook.py:52           timeout=True
scripts/hooks/check-version-sync-hook.py:43        timeout=False
scripts/hooks/post-bash-revalidate.py:60           timeout=False
scripts/hooks/post-bash-revalidate.py:78           timeout=False
scripts/hooks/ruff-hook.py:34,37,40                timeout=False
scripts/hooks/stop-reminder.py:44                  timeout=False
scripts/hooks/validate-audit-findings-hook.py:57,69,79  timeout=False
scripts/hooks/validate-rules-hook.py:42            timeout=False
scripts/hooks/validate-skill-hook.py:39            timeout=False
```

The omission is inconsistent, not principled: `deny-unsafe-git-hook.py:57`
passes `timeout=10` for a single `git rev-parse`, which is far cheaper than
what `post-bash-revalidate.py` runs unbounded.

`post-bash-revalidate.py:46-53` — four of the six gates are `uv run`:

```python
GATES = (
    ("scripts/validate-skill.py", ["uv", "run", "--quiet", "scripts/validate-skill.py"]),
    ...
)
...
result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
```

Failing scenario A (hang): on a fresh clone or after a cleared cache, `uv run`
resolves and downloads an environment. With a slow or unreachable package
index that call blocks indefinitely. The hook produces no output while
blocked, so the agent session freezes on an ordinary Bash command with no
indication of why.

Failing scenario B (crash): the existence guard at line 73 checks only that the
*gate script* is present — `if not (REPO_ROOT / script).exists()`. It never
checks the binary. On a checkout without `uv` on PATH, `subprocess.run(["uv",
...])` raises `FileNotFoundError`, which nothing catches, and the hook exits
with a traceback instead of the diagnosable gate message line 76 exists to
provide. `commands/_conventions.md` requires preflighting every external binary
with `command -v` for exactly this reason.

Line 60's `git status` shares both gaps.

## Not applied — blocked by design

Left open deliberately. Every file the fix touches (`scripts/hooks/_hooklib.py`
and the eleven hook scripts) is under `permissions.deny` for `Edit`, `Write`
and `NotebookEdit` in `.claude/settings.json`, so an agent cannot apply it. That
protection is working as intended: the enforcement surface is owner-owned.
Applying this needs the repo owner.

The `post-bash-revalidate.py` half is prepared as an anchored patch at
`docs/audit/apply-open-findings.py` — it adds `GATE_TIMEOUT`, bounds both
`subprocess.run` calls, and preflights the gate binary with `shutil.which`.
Its anchors were verified to match the current file exactly once each and the
patched result parses as valid Python. Run it with `--check` first. The
remaining nine call sites still need the shared `_hooklib` runner.

## Impact

A PostToolUse hook that blocks has no user-visible recovery short of interrupting the session, and it fires on every Bash command touching `skills/`, `.claude/rules/`, the version manifests, or the findings store — the hot path of ordinary work in this repo. The `FileNotFoundError` path turns a supportable "gate skipped" message into an unexplained traceback, which is the failure mode line 74-77 was written to avoid for the sibling case.

## Fix

Add a shared runner to `scripts/hooks/_hooklib.py` that wraps `subprocess.run` with a default `timeout` and catches `OSError`/`subprocess.SubprocessError`, returning a sentinel the caller reports as a skipped gate — mirroring the existing `except (OSError, subprocess.SubprocessError)` in `deny-unsafe-git-hook.py:59`. Route all eleven untimed call sites through it. In `post-bash-revalidate.py`, extend the line 73 guard with a `shutil.which(cmd[0])` check so a missing `uv` prints the same "gate skipped" line as a missing script. Cover both paths with tests in `tests/test_hooks.py`, which already has the hook-loading harness.
