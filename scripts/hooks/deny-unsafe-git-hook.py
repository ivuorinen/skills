#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PreToolUse hook — block the two git-write mandates the rules declare unenforced.

1. `git commit --no-verify` / `-n` skips the pre-commit validators that guard
   skill files, the version manifests, and the findings store
   (.claude/rules/commit-gate-integrity.md, which states no in-session hook
   enforces it).
2. `git push` onto a protected branch
   (skills/nitpicker/commands/cr.md Step 6: never push directly to main/master).
3. `git add -A` / `--all` / `.` — staging the whole tree is a recurring source
   of commits carrying files the change never touched: scratch output, local
   config, editor artifacts. Explicit pathspecs and `git add -u` (tracked files
   only) stay allowed.

Tokenising lives in _hooklib.git_calls, shared with the sibling guards.

Blocks with exit 2 + stderr, matching deny-agents-path-hook.py — for PreToolUse
that is a deny. Fails closed: malformed stdin or an internal error also exits 2,
because a guard that exits 0 on exception enforces nothing.
"""

import functools
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import git_calls, load_event, repo_root  # type: ignore[import-not-found]

REPO_ROOT = repo_root()
PROTECTED = frozenset({"main", "master"})
_NO_VERIFY = frozenset({"--no-verify", "-n"})
# Arguments that stage every change rather than a named path. `.` is included
# deliberately: from the repo root it stages the same set `-A` does, so blocking
# only the flags would move the hazard to `git add .` instead of removing it.
# `:/` is git's whole-repo pathspec magic — the same thing spelled differently.
_ADD_ALL = frozenset({"-A", "--all", "--no-ignore-removal", ".", ":/"})
# Push modes that name no refspec and update protected branches regardless of HEAD.
_ALL_REFS = frozenset({"--all", "--mirror"})

_COMMIT_DENIAL = (
    "  DENIED  git commit --no-verify skips the pre-commit validators that guard\n"
    "          skill files, version manifests, and the findings store.\n"
    "          See .claude/rules/commit-gate-integrity.md — commit without the\n"
    "          flag, or fix what pre-commit reports."
)
_PUSH_DENIAL = (
    "  DENIED  push targets a protected branch (HEAD is '{branch}').\n"
    "          Open a PR from a feature branch instead — see cr.md Step 6."
)
_ADD_DENIAL = (
    "  DENIED  `git add {arg}` stages the whole tree, including files this change\n"
    "          never touched — scratch output, local config, editor artifacts.\n"
    "          Stage what you actually changed: git add <path> [<path> ...]\n"
    "          `git add -u` restages tracked files only, if that is what you meant."
)


@functools.cache
def _current_branch() -> str | None:
    """HEAD's branch. Cached: a denial resolves it once to decide and again to
    name the branch in the message, and this hook runs on every Bash call."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _head_is_protected() -> bool:
    """HEAD decides when no refspec does. An unresolvable HEAD blocks — the guard
    cannot prove the push is safe."""
    branch = _current_branch()
    return branch is None or branch in PROTECTED


def _ref_target(ref: str) -> str:
    """Destination branch a refspec names: `+src:refs/heads/main` -> `main`."""
    return ref.split(":")[-1].lstrip("+").removeprefix("refs/heads/")


def _push_targets_protected(args: list[str]) -> bool:
    """True when the push could land on a protected branch.

    EVERY refspec is a target, not just the first: `git push origin feature main`
    reaches main through its second one, and `git push origin f:f main:main`
    through the second colon form. `--all`/`--mirror` push every matching ref, so
    they are protected whatever HEAD is. A bare `HEAD` refspec resolves through
    the current branch, as does a push with no refspec at all.
    """
    if any(a in _ALL_REFS for a in args):
        return True
    operands = [a for a in args if not a.startswith("-")]
    if len(operands) < 2:
        return _head_is_protected()
    targets = [_ref_target(ref) for ref in operands[1:]]
    if any(t in PROTECTED for t in targets):
        return True
    return "HEAD" in targets and _head_is_protected()


def _denial(subcommand: str, args: list[str]) -> str | None:
    """The message to block this git call with, or None to allow it."""
    if subcommand == "commit" and any(a in _NO_VERIFY for a in args):
        return _COMMIT_DENIAL
    if subcommand == "add":
        staged_all = [a for a in args if a in _ADD_ALL]
        if staged_all:
            return _ADD_DENIAL.format(arg=staged_all[0])
    if subcommand == "push" and _push_targets_protected(args):
        return _PUSH_DENIAL.format(branch=_current_branch() or "unknown")
    return None


def main() -> None:
    data = load_event()
    if data is None:
        return  # not a parseable event — nothing to judge

    command = (data.get("tool_input") or {}).get("command") or ""
    if not command:
        return

    for subcommand, args in git_calls(command):
        reason = _denial(subcommand, args)
        if reason is not None:
            print(reason, file=sys.stderr, flush=True)
            sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail closed — an internal error must not allow the call
        print(f"  DENIED  git guard failed internally: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)
