#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Stop hook — remind about staged skill changes before Claude hands back control.

Scoped to the git index (`git diff --cached`): the reminder fires only when
skill files are staged for commit, not on every turn a working-tree edit exists.
On a long-lived branch full of uncommitted skill edits, a working-tree scope
would block the stop once per turn forever; the index scope fires only at the
moment it matters — right before a commit.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import load_event, repo_root  # noqa: E402  # type: ignore[import-not-found]

REPO_ROOT = repo_root()


def main() -> None:
    # A Stop hook that exits 2 blocks the stop and re-invokes Claude. Without
    # this guard the reminder fires again on the forced continuation's own stop,
    # looping forever. `stop_hook_active` is true on that second pass — surface
    # the reminder once, then let Claude stop.
    if (load_event() or {}).get("stop_hook_active"):
        return

    # `git diff --cached --name-only -z` lists staged paths only, NUL-separated
    # and unquoted (safe for spaces). Renames report just the new path.
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return
    paths = [p for p in result.stdout.split("\0") if p]
    changed = [
        f
        for f in paths
        if "skills/" in f and (f.endswith("SKILL.md") or "/commands/" in f and f.endswith(".md"))
    ]
    if changed:
        # Stop hooks feed back to Claude only via exit 2 + stderr.
        print("Staged skill changes detected:", file=sys.stderr)
        for f in changed:
            print(f"  {f}", file=sys.stderr)
        print("Run /validate-skills before releasing.", file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
