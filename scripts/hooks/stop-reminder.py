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
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # No commits yet — fall back to porcelain status
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        lines = [line[3:] for line in result.stdout.splitlines()]
    else:
        lines = result.stdout.splitlines()
    changed = [f for f in lines if "skills/" in f and f.endswith("SKILL.md")]
    if changed:
        print("Modified skills detected:", flush=True)
        for f in changed:
            print(f"  {f}", flush=True)
        print("Run /validate-skills before releasing.", flush=True)


if __name__ == "__main__":
    main()
