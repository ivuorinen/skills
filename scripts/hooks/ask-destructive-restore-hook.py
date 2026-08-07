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

Decision is `ask`, not `deny`: the operation is legitimate and common, so a hard
block would be wrong. The value is that the discard is seen before it happens.
A restore over a clean path is allowed silently.

`ask` requires the JSON form — exit 2 means deny, which is not what this wants.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import load_event, repo_root  # type: ignore[import-not-found]

REPO_ROOT = repo_root()

# `\b` binds to `restore` only: `--` ends in a non-word char, so a trailing `\b`
# after the alternation never matches the `checkout --` branch (it silently
# matched nothing at all until this was caught by firing it on a dirty file).
_RESTORE = re.compile(r"\bgit\b(?:\s+-\S+)*\s+(?:checkout\s+--(?=\s)|restore\b)")
_FLAGS = re.compile(r"^-")


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


def _targets(command: str) -> list[str]:
    """Path operands after the restore verb, flags and the `--` separator dropped."""
    tail = _RESTORE.split(command, maxsplit=1)[-1]
    tail = re.split(r"[|;&]", tail)[0]
    return [t for t in tail.split() if not _FLAGS.match(t) and t != "--"]


def _dirty(paths: list[str]) -> list[str]:
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain", "--", *paths]
            if paths
            else ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return paths  # cannot prove clean — treat as dirty and ask
    if r.returncode != 0:
        return paths
    # Tracked modifications only: an untracked file is not destroyed by a restore.
    return [ln[3:] for ln in r.stdout.splitlines() if ln and not ln.startswith("??")]


def main() -> None:
    data = load_event()
    if data is None:
        return

    command = (data.get("tool_input") or {}).get("command") or ""
    if not command or not _RESTORE.search(command):
        return

    dirty = _dirty(_targets(command))
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
