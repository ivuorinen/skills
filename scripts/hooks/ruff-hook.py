#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruff"]
# ///
"""PostToolUse hook — run ruff check --fix and ruff format on edited Python files."""

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
    raw = Path(file_path)
    path = raw if raw.is_absolute() else REPO_ROOT / raw

    if path.suffix != ".py" or not path.exists():
        return

    # auto-fix what ruff can, then format
    subprocess.run(["ruff", "check", "--fix", "--quiet", str(path)], check=False)
    subprocess.run(["ruff", "format", "--quiet", str(path)], check=False)

    # report any remaining lint errors
    result = subprocess.run(
        ["ruff", "check", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout, end="", flush=True)
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
