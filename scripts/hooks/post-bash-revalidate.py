#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — revalidate the governed trees after a shell tool call.

The Write|Edit validators never see a shell-mediated mutation (`sed -i`,
`>` redirection, `git mv`, `cp`, `patch`), so those edits bypassed the whole
enforcement surface. A shell event carries no file_path, so this hook asks git
what is dirty instead, and runs the whole-tree gates only when a porcelain entry
names a governed path. On a clean tree a read-only call costs one `git status`:
the ignored entries every checkout carries — bytecode caches, the store lock —
do not count (perf-74e03db5). While a governed path stays dirty the gates re-run
on each call. That over-validation is deliberate and fail-safe: a `git status`
snapshot cannot distinguish a fresh mutation from a pre-existing dirty file
without per-file content hashing, so the hook prefers redundant work over
missing an edit.
"""

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import (
    HOOK_TIMEOUT,
    SHIPPED_ROOT,
    repo_root,
    report_skip,
)

REPO_ROOT = repo_root()

# Substring markers — a porcelain entry whose path mentions any of these is
# governed, subject to the per-entry rules in `_governed`. A substring match
# keeps rename entries (`old -> new`) covered on either side.
# `.claude/agents/` is deliberately absent: no gate here validates agent-definition
# content, so listing it would imply a re-check that does not happen. Bash edits to
# that tree are blocked upstream by deny-agents-path-hook.py instead.
GOVERNED = (
    "skills/",
    # The enforcement surface itself. permissions.deny stops Edit/Write on
    # scripts/hooks/ and .claude/settings.json but never reaches Bash, and no
    # PreToolUse guard matches them either — deny-agents-path-hook.py covers
    # .claude/agents/ only. Without these two entries a `sed -i` disabling a
    # guard, or unregistering every hook at once, ran the gates zero times.
    # "scripts/" also covers the validators the gates below invoke.
    "scripts/",
    ".claude/settings.json",
    # Merged over settings.json and able to set `disableAllHooks`
    # (agent-loopholes-bbe241dd). It is gitignored here, so it surfaces only
    # where a checkout tracks it; no ignored entry re-runs the gates.
    ".claude/settings.local.json",
    ".claude/rules/",
    "docs/audit/findings/",
    "package.json",
    "pyproject.toml",
    ".release-please-manifest.json",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
)

FINDINGS = "skills/nitpicker/scripts/findings.py"

# The same bound every other hook uses; HOOK_TIMEOUT in _hooklib.py carries the
# rationale. Aliased rather than re-stated so a change to the shared constant
# reaches the hook that shells out most, while the failure messages below still
# read as a gate timeout.
GATE_TIMEOUT = HOOK_TIMEOUT
_UV = ["uv", "run", "--quiet"]
# (script it needs on disk, argv) — a missing script is skipped, not a traceback.
# The script in argv is an absolute path under SHIPPED_ROOT: repo-relative argv
# under cwd=REPO_ROOT ran whichever gates the environment's tree held
# (audit-1e48d360). REPO_ROOT stays the `cwd`, the tree the gates judge.
GATES = tuple(
    (script, [*prefix, str(SHIPPED_ROOT / script), *suffix])
    for script, prefix, suffix in (
        ("scripts/validate-skill.py", _UV, []),
        ("scripts/validate-rules.py", _UV, []),
        ("scripts/check-version-sync.py", _UV, []),
        ("scripts/check-stdlib-only.py", _UV, []),
        # Eval sets are validated on Write|Edit only; without this a Bash edit to
        # one reached no in-session gate (audit-38801f60).
        ("scripts/validate-evals.py", _UV, []),
        (FINDINGS, ["python3"], ["validate"]),
        (FINDINGS, ["python3"], ["index"]),
    )
)

_STORE = "docs/audit/findings/"


def _governed(entry: str) -> bool:
    """True when one `git status --porcelain --ignored` entry names a governed path.

    Matching GOVERNED against the whole output ran every gate after every call on
    a clean tree: `!! docs/audit/findings/.lock` and each `__pycache__/` directory
    contain a governed substring and exist on every checkout. That cost 1.21 s per
    call against 0.08 s, plus a store-lock take and an INDEX.md rewrite
    (perf-74e03db5).

    A bytecode cache never counts. An ignored entry counts only inside the
    findings store, which may be gitignored, and not for its lock or temp files.
    Ceiling: a fully ignored store is listed as one `!! docs/audit/findings/`
    entry, which still re-runs the gates on each call.
    """
    path = entry[3:]
    if "__pycache__/" in path:
        return False
    if entry.startswith("!!"):
        return path.startswith(_STORE) and not path.endswith((".lock", ".tmp"))
    return any(marker in path for marker in GOVERNED)


def main() -> None:  # noqa: C901
    """Re-run the whole-tree gates when a Bash call dirtied a governed path.

    A Bash event carries no `file_path`, so this asks git what is dirty
    instead of reading the event — that is the whole reason the hook exists,
    since the Write/Edit validators never see a `sed -i` or a redirection.
    Returns silently on a clean tree; exits 2 with the failing gate's output.
    """
    # --ignored so a Bash edit to a gitignored findings store still shows up:
    # plain --porcelain omits ignored paths, and the store supports being
    # gitignored, so without this those edits skipped the findings gates.
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--ignored"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=GATE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        # git absent, or a tree slow enough that status timed out. A PostToolUse
        # hook that blocks has no user-visible recovery, so bound it and skip —
        # out loud, since a silent skip reads as every gate passing.
        report_skip("post-bash-revalidate", f"{type(exc).__name__}: {exc}", "make check")
    if status.returncode != 0:
        return  # not a git tree — nothing to scope against
    if not any(_governed(entry) for entry in status.stdout.splitlines()):
        return

    failures = []
    for script, cmd in GATES:
        if not (SHIPPED_ROOT / script).exists():
            # gate script absent (partial checkout) — CI remains the gate, but a
            # silently skipped gate is indistinguishable from a passing one.
            print(f"  post-bash-revalidate: gate skipped, {script} not found", file=sys.stderr)
            continue
        if shutil.which(cmd[0]) is None:
            # Same reasoning as the missing-script arm above: that check covered
            # the gate script but never the interpreter, so an absent `uv` raised
            # an uncaught FileNotFoundError instead of this message.
            print(
                f"  post-bash-revalidate: gate skipped, {cmd[0]} not on PATH",
                file=sys.stderr,
            )
            continue
        try:
            # argv is a GATES entry: a module-constant literal list, never input.
            result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
                cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=GATE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            # `uv run` resolves and downloads an environment on a cold cache; an
            # unreachable index made that block forever with no output.
            #
            # Stop the run rather than continuing to the next gate. GATE_TIMEOUT
            # bounds each gate on its own, so continuing let every hung gate hold
            # this PostToolUse hook for len(GATES) * GATE_TIMEOUT of silence, the
            # exact failure the per-gate bound exists to prevent.
            # Whatever wedges one `uv run` wedges the rest, so the remaining
            # gates buy no coverage and cost a full GATE_TIMEOUT each.
            failures.append(
                f"{' '.join(cmd)} timed out after {GATE_TIMEOUT}s; remaining gates skipped"
            )
            break
        except OSError as exc:
            failures.append(f"{' '.join(cmd)} could not run: {exc}")
            continue
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).rstrip()
            # A gate that exits non-zero with no output would otherwise block the
            # call with an empty message; name the gate so the block is diagnosable.
            failures.append(detail or f"{' '.join(cmd)} failed (exit {result.returncode})")

    if failures:
        # PostToolUse surfaces only exit 2 + stderr back to the agent.
        print("\n".join(f for f in failures if f), file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
