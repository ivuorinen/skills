#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Stop hook — remind about pending skill changes before Claude hands back control.

Scoped to the union of the git index and the working tree. An index-only scope
missed `git commit -am`, which stages and commits inside a single Bash call, so
no stop ever observed a staged state. The `stop_hook_active` guard below — not
the narrowness of the scope — is what keeps a long-lived branch full of
uncommitted skill edits from blocking the stop once per turn forever.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import (  # type: ignore[import-not-found]
    HOOK_TIMEOUT,
    load_event,
    repo_root,
)

REPO_ROOT = repo_root()


def main() -> None:
    """Remind about uncommitted skill files before Claude hands back control.

    Reads the index, the working tree and the untracked set: a brand-new
    SKILL.md or command file appears in neither diff form, yet is the most
    common pending change. Exit 2 blocks the stop, which is why the
    `stop_hook_active` guard is needed to keep the reminder from firing again
    on its own forced continuation.
    """
    # A Stop hook that exits 2 blocks the stop and re-invokes Claude. Without
    # this guard the reminder fires again on the forced continuation's own stop,
    # looping forever. `stop_hook_active` is true on that second pass — surface
    # the reminder once, then let Claude stop.
    if (load_event() or {}).get("stop_hook_active"):
        return

    # `--name-only -z` lists paths NUL-separated and unquoted (safe for spaces).
    # Renames report just the new path. `--cached` is the index, the bare `diff` is
    # the working tree, and `ls-files --others --exclude-standard` is the untracked
    # set — a brand-new SKILL.md/command file shows up in neither diff form (git
    # diff never lists untracked) yet is the most common pending-skill change. A
    # path can appear in more than one, so dedupe while keeping order.
    paths: list[str] = []
    for cmd in (
        ["git", "diff", "--cached", "--name-only", "-z"],
        ["git", "diff", "--name-only", "-z"],
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
    ):
        try:
            # argv is one of the three literal git read commands in the loop above.
            result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
                cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=HOOK_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return  # git absent or hung — no reminder is better than a frozen stop
        if result.returncode != 0:
            return
        paths += [p for p in result.stdout.split("\0") if p and p not in paths]
    changed = [
        f
        for f in paths
        if "skills/" in f and (f.endswith("SKILL.md") or ("/commands/" in f and f.endswith(".md")))
    ]
    if changed:
        # Stop hooks feed back to Claude only via exit 2 + stderr.
        print("Pending skill changes detected:", file=sys.stderr)
        for f in changed:
            print(f"  {f}", file=sys.stderr)
        print("Run /validate-skills before releasing.", file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
