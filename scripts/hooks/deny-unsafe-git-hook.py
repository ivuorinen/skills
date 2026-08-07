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

The subcommand is found by tokenising, not by regex: `git -C dir commit
--no-verify` and `git -c k=v push` have a value-taking global option between
`git` and the subcommand, which a `(?:\\s+-\\S+)*` pattern walks straight past.

Blocks with exit 2 + stderr, matching deny-agents-path-hook.py — for PreToolUse
that is a deny. Fails closed: malformed stdin or an internal error also exits 2,
because a guard that exits 0 on exception enforces nothing.
"""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import load_event, repo_root  # type: ignore[import-not-found]

REPO_ROOT = repo_root()
PROTECTED = frozenset({"main", "master"})

# git global options that consume the NEXT token as their value. Without these
# the token after them is mistaken for the subcommand (or the scan stops early).
_VALUE_OPTS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"})
_SPLIT = re.compile(r"\|\||&&|[|;&\n]")


def _git_calls(command: str) -> list[tuple[str, list[str]]]:
    """(subcommand, args) for every git invocation across the command's stages."""
    calls: list[tuple[str, list[str]]] = []
    for segment in _SPLIT.split(command):
        tokens = segment.split()
        i = 0
        while i < len(tokens) and "=" in tokens[i] and not tokens[i].startswith("-"):
            i += 1  # VAR=value environment prefix
        if i >= len(tokens) or Path(tokens[i]).name != "git":
            continue
        i += 1
        while i < len(tokens):
            token = tokens[i]
            if token in _VALUE_OPTS:
                i += 2
            elif token.startswith("-"):
                i += 1  # valueless global flag, or --opt=value
            else:
                break
        if i < len(tokens):
            calls.append((tokens[i], tokens[i + 1 :]))
    return calls


def _current_branch() -> str | None:
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


def _push_targets_protected(args: list[str]) -> bool:
    """True when the push would land on a protected branch.

    An explicit `<remote> <ref>` refspec names its own target; otherwise the push
    follows HEAD's upstream and HEAD decides. An unresolvable HEAD blocks — the
    guard cannot prove the push is safe.
    """
    operands = [a for a in args if not a.startswith("-")]
    if len(operands) >= 2:
        return operands[1].split(":")[-1].removeprefix("refs/heads/") in PROTECTED
    branch = _current_branch()
    return branch is None or branch in PROTECTED


def main() -> None:
    data = load_event()
    if data is None:
        return  # not a parseable event — nothing to judge

    command = (data.get("tool_input") or {}).get("command") or ""
    if not command:
        return

    for subcommand, args in _git_calls(command):
        if subcommand == "commit" and any(a in ("--no-verify", "-n") for a in args):
            print(
                "  DENIED  git commit --no-verify skips the pre-commit validators that guard\n"
                "          skill files, version manifests, and the findings store.\n"
                "          See .claude/rules/commit-gate-integrity.md — commit without the\n"
                "          flag, or fix what pre-commit reports.",
                file=sys.stderr,
                flush=True,
            )
            sys.exit(2)
        if subcommand == "push" and _push_targets_protected(args):
            branch = _current_branch() or "unknown"
            print(
                f"  DENIED  push targets a protected branch (HEAD is '{branch}').\n"
                "          Open a PR from a feature branch instead — see cr.md Step 6.",
                file=sys.stderr,
                flush=True,
            )
            sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail closed — an internal error must not allow the call
        print(f"  DENIED  git guard failed internally: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)
