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
from _hooklib import (  # type: ignore[import-not-found]
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
    """Path operands of the first destructive restore, or None if there is none.

    `git checkout` counts only with an explicit `--`; without it the command is a
    branch switch or creation, which destroys nothing.
    """
    for subcommand, args in git_calls(command):
        if subcommand == "restore":
            return [a for a in args if not a.startswith("-")]
        if subcommand == "checkout" and "--" in args:
            tail = args[args.index("--") + 1 :]
            return [a for a in tail if not a.startswith("-")]
    return None


def _covers(target: str, entry: str) -> bool:
    """Whether restoring `target` would touch the repo-relative `entry`."""
    t = target.strip("\"'").rstrip("/")
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

    command = (data.get("tool_input") or {}).get("command") or ""
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
