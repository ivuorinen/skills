#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — warn on version mismatch after editing a version-bearing manifest.

Covers JSON manifests (package.json, plugin.json, marketplace.json,
.release-please-manifest.json) and pyproject.toml.
"""

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
    problems = [
        line for line in result.stdout.splitlines() if "MISMATCH" in line or "ERROR" in line
    ]
    if problems or result.returncode != 0:
        for line in problems:
            print(line, flush=True)
        if result.returncode != 0 and not problems:
            print((result.stdout.strip() or result.stderr.strip()), flush=True)
        print("Run ./scripts/bump-version.py to resync all version files.", flush=True)


if __name__ == "__main__":
    main()
