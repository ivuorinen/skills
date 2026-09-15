#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PreToolUse hook — confirm before discarding uncommitted work.

`git checkout -- <path>` and `git restore <path>` overwrite the working tree from
the index, discarding unstaged changes irrecoverably: that content never reached
the object store, so there is no reflog or stash to recover from. The idiom is
standard inside mutation/verification scripts, where the intent is "undo my
temporary edit" but the effect is "discard everything unstaged at that path".

The restore call is found by tokenising (_hooklib.git_calls), not by regex: the
first version used `\\bgit\\b(?:\\s+-\\S+)*`, which cannot step over a
value-taking global option, so `git -C . checkout -- README.md` slipped past it.

Decision is `ask`, not `deny`: the operation is legitimate and common, so a hard
block would be wrong. The value is that the discard is seen before it happens.
A restore over a clean path is allowed silently.

`ask` requires the JSON form — exit 2 means deny, which is not what this wants.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import (
    event_command,
    git_calls,
    load_event,
    repo_root,
    shell_stages,
)

REPO_ROOT = repo_root()
# A stage that moves the shell breaks the one assumption path matching rests on.
_CHDIR = frozenset({"cd", "pushd", "popd"})


def _decide(decision: str, reason: str) -> None:
    """Emit a PreToolUse permission decision on stdout and exit.

    This hook asks rather than denies, so it speaks the structured
    `hookSpecificOutput` protocol instead of the exit-2 channel its sibling
    guards use. Exits 0: a non-zero exit here would be read as a hook failure
    rather than as the decision it carries.
    """
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    sys.stdout.flush()
    sys.exit(0)


def _targets(command: str) -> list[str] | None:
    """Path operands of the first destructive restore, or None if there is none."""
    for subcommand, args in git_calls(command):
        if subcommand == "restore":
            return [a for a in args if not a.startswith("-")]
        if subcommand == "checkout" and (targets := _checkout_targets(args)) is not None:
            return targets
    return None


# Options that make `git checkout` create a branch, which never restores a path.
_BRANCH_CREATION = frozenset({"-b", "-B", "--orphan"})


def _checkout_targets(args: list[str]) -> list[str] | None:
    """The paths a `git checkout` restores, or None when it only switches branches.

    Counting a checkout only when it carried `--` missed `git checkout f.txt`,
    which overwrites the unstaged content from the index just the same
    (agent-loopholes-152e6d90). Without `--` git reads a leading operand that
    names a commit as the source and everything after it as paths, and an
    operand that names no commit as a path; this follows the same rule.
    """
    if "--" in args:
        tail = args[args.index("--") + 1 :]
        return [a for a in tail if not a.startswith("-")]
    if any(a in _BRANCH_CREATION for a in args):
        return None
    operands = [a for a in args if not a.startswith("-")]
    if operands and _is_commit(operands[0]):
        operands = operands[1:]
    return operands or None


def _is_commit(operand: str) -> bool:
    """True when git resolves `operand` to a commit in this repository.

    `--end-of-options` keeps the caller-derived operand from being read as an
    option. When git cannot answer, the operand counts as a path: the guard then
    asks rather than staying silent over a possible discard.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "rev-parse",
                "--verify",
                "--quiet",
                "--end-of-options",
                f"{operand}^{{commit}}",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _covers(target: str, entry: str) -> bool:
    """Whether restoring `target` would touch the repo-relative `entry`.

    Pathspec magic (`:/`, `:(top)`, …) and a glob reach entries no prefix test can
    match, so they cover every entry: `_covers(":/", "src/a.py")` was False, and a
    whole-tree restore over dirty files passed silently (agent-loopholes-152e6d90).
    Over-asking on a narrow glob is the cheap direction for an `ask` hook.
    """
    t = target.strip("\"'").rstrip("/")
    if t.startswith(":") or any(char in t for char in "*?["):
        return True
    if t.startswith("/"):
        try:
            t = str(Path(t).resolve().relative_to(Path(REPO_ROOT).resolve()))
        except ValueError:
            return False  # outside the repo — git status can never list it
    t = t.removeprefix("./")
    return t in ("", ".") or entry == t or entry.startswith(f"{t}/")


def _changes_directory(command: str) -> bool:
    """Whether any stage moves the shell before the restore runs.

    Targets come from the command text and are relative to the shell's working
    directory; `git status` entries are relative to the repo root. `cd src && git
    checkout -- a.py` compares `a.py` against `src/a.py`, matches nothing, and the
    guard stays silent while the restore discards the file. Path matching cannot
    be trusted here, so the filter is skipped rather than trusted.
    """
    return any(Path(tokens[0]).name in _CHDIR for tokens in shell_stages(command))


def _tracked_dirty() -> list[str] | None:
    """Tracked, uncommitted paths in the repo; None if git could not be asked.

    `-z` rather than plain `--porcelain`: the default format quotes paths holding
    unusual characters and renders a rename as `old -> new`, both of which the
    naive `line[3:]` slice turned into a path that matches nothing. NUL-separated
    records need no quoting, and a rename's source arrives as its own record.

    argv is fixed. Handing tokenised operands to git as a pathspec risks a
    non-zero exit on a token that is not a valid pathspec — which would make the
    guard ask on every restore — and keeps caller-derived strings out of argv.
    """
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain", "-z"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    entries: list[str] = []
    records = iter(r.stdout.split("\0"))
    for record in records:
        if len(record) < 4 or record.startswith("??"):
            continue  # untracked files are not destroyed by a restore
        if record[0] in "RC":
            next(records, None)  # rename/copy source follows as its own record
        entries.append(record[3:])
    return entries


def _dirty(targets: list[str], unfiltered: bool) -> list[str]:
    """Tracked, uncommitted paths the restore would discard."""
    entries = _tracked_dirty()
    if entries is None:
        return targets  # cannot prove clean — treat as dirty and ask
    if unfiltered:
        return entries
    return [e for e in entries if any(_covers(t, e) for t in targets)]


def main() -> None:
    """Ask before a git restore discards uncommitted work.

    Stays silent when the target is clean, so ordinary reverts are not
    interrupted — the prompt is reserved for the case where the discarded
    content exists nowhere else: `git checkout --` overwrites the working
    tree from the index, leaving no reflog entry and no stash to recover
    from. The listed paths are truncated because the prompt has to stay
    readable to be read at all.
    """
    data = load_event()
    if data is None:
        return

    command = event_command(data)
    targets = _targets(command) if command else None
    if targets is None:
        return

    dirty = _dirty(targets, unfiltered=_changes_directory(command))
    if not dirty:
        return  # nothing uncommitted at the target — ordinary use, stay quiet

    listed = ", ".join(dirty[:5]) + (f" (+{len(dirty) - 5} more)" if len(dirty) > 5 else "")
    _decide(
        "ask",
        "This discards UNCOMMITTED changes irrecoverably — no reflog, no stash.\n"
        f"Uncommitted at the target: {listed}\n"
        "If this is a verification script restoring a mutation, snapshot with `cp` "
        "first: `git checkout --` overwrites the working tree from the index, which "
        "deletes work that was never staged rather than just the mutation.",
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail closed — ask rather than silently allow
        _decide("ask", f"restore guard failed internally ({exc}); confirm manually")
