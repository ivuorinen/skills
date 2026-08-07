#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PreToolUse hook — confirm before discarding uncommitted work.

`git checkout -- <path>` and `git restore <path>` delete uncommitted changes
irrecoverably: nothing reaches the object store, so there is no reflog or stash
to recover from. The idiom is standard inside mutation/verification scripts,
where the intent is "undo my temporary edit" but the effect is "discard
everything uncommitted at that path".

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
from _hooklib import git_calls, load_event, repo_root  # type: ignore[import-not-found]

REPO_ROOT = repo_root()


def _decide(decision: str, reason: str) -> None:
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


def _dirty(targets: list[str]) -> list[str]:
    """Tracked, uncommitted paths the restore would discard.

    `git status` runs with a fixed argv and the pathspec filtering happens here.
    Handing tokenised operands to git risks a non-zero exit on a token that is not
    a valid pathspec, which would make the guard ask on every restore — and keeps
    caller-derived strings out of the subprocess argv entirely.
    """
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return targets  # cannot prove clean — treat as dirty and ask
    if r.returncode != 0:
        return targets
    # Tracked modifications only: an untracked file is not destroyed by a restore.
    entries = [ln[3:] for ln in r.stdout.splitlines() if ln and not ln.startswith("??")]
    return [e for e in entries if any(_covers(t, e) for t in targets)]


def main() -> None:
    data = load_event()
    if data is None:
        return

    command = (data.get("tool_input") or {}).get("command") or ""
    targets = _targets(command) if command else None
    if targets is None:
        return

    dirty = _dirty(targets)
    if not dirty:
        return  # nothing uncommitted at the target — ordinary use, stay quiet

    listed = ", ".join(dirty[:5]) + (f" (+{len(dirty) - 5} more)" if len(dirty) > 5 else "")
    _decide(
        "ask",
        "This discards UNCOMMITTED changes irrecoverably — no reflog, no stash.\n"
        f"Uncommitted at the target: {listed}\n"
        "If this is a verification script restoring a mutation, snapshot with `cp` "
        "first: `git checkout --` reverts to HEAD, which deletes work that was never "
        "committed rather than just the mutation.",
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail closed — ask rather than silently allow
        _decide("ask", f"restore guard failed internally ({exc}); confirm manually")
