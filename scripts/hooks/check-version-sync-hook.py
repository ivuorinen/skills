#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — warn on version mismatch after editing a version-bearing JSON."""

import json
import os
import subprocess
import sys
from pathlib import Path

_default = Path(__file__).parent.parent.parent
REPO_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.environ.get("REPO_ROOT", _default)))

VERSION_FILES = {
    "package.json",
    "plugin.json",
    "marketplace.json",
    ".release-please-manifest.json",
    "pyproject.toml",
}


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    file_path = data.get("file_path") or data.get("path") or ""
    path = Path(file_path)

    if path.name not in VERSION_FILES:
        return

    checker = REPO_ROOT / "scripts" / "check-version-sync.py"
    if not checker.exists():
        return

    result = subprocess.run(
        ["uv", "run", "--quiet", str(checker)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    mismatches = [line for line in result.stdout.splitlines() if "MISMATCH" in line]
    if mismatches:
        for line in mismatches:
            print(line, flush=True)
        print("Run ./scripts/bump-version.py to resync all version files.", flush=True)


if __name__ == "__main__":
    main()
