#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — validate SKILL.md after Write or Edit."""

import json
import os
import subprocess
import sys
from pathlib import Path

_default = Path(__file__).parent.parent.parent
REPO_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.environ.get("REPO_ROOT", _default)))


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    file_path = data.get("file_path") or data.get("path") or ""
    path = Path(file_path)

    if not (path.name == "SKILL.md" and "skills" in path.parts):
        return

    validator = REPO_ROOT / "scripts" / "validate-skill.py"
    if not validator.exists():
        return

    result = subprocess.run(
        ["uv", "run", "--quiet", str(validator), str(path)],
        cwd=str(REPO_ROOT),
        capture_output=False,
    )
    if result.returncode != 0:
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
