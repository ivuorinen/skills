#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Stop hook — remind about modified skills before Claude hands back control."""

import os
import subprocess
from pathlib import Path

_default = Path(__file__).parent.parent.parent
REPO_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.environ.get("REPO_ROOT", _default)))


def main() -> None:
    # Use `git status --porcelain -uall` so the hook also sees individual
    # untracked SKILL.md files — without `-uall`, an untracked directory shows
    # as just `?? skills/` (trailing slash) and the SKILL.md filter misses it.
    result = subprocess.run(
        ["git", "status", "--porcelain", "-uall"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        # Renames look like "R  old -> new"; keep only the new path.
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    changed = [f for f in paths if "skills/" in f and f.endswith("SKILL.md")]
    if changed:
        print("Modified skills detected:", flush=True)
        for f in changed:
            print(f"  {f}", flush=True)
        print("Run /validate-skills before releasing.", flush=True)


if __name__ == "__main__":
    main()
