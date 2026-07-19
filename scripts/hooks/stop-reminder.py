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
from _hooklib import load_event, repo_root  # type: ignore[import-not-found]

REPO_ROOT = repo_root()


def main() -> None:
    # A Stop hook that exits 2 blocks the stop and re-invokes Claude. Without
    # this guard the reminder fires again on the forced continuation's own stop,
    # looping forever. `stop_hook_active` is true on that second pass — surface
    # the reminder once, then let Claude stop.
    if (load_event() or {}).get("stop_hook_active"):
        return

    # `--name-only -z` lists paths NUL-separated and unquoted (safe for spaces).
    # Renames report just the new path. `--cached` is the index, the bare form is
    # the working tree; a path can appear in both, so dedupe while keeping order.
    paths: list[str] = []
    for scope in (["--cached"], []):
        result = subprocess.run(
            ["git", "diff", *scope, "--name-only", "-z"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
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
