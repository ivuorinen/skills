#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruff"]
# ///
"""PostToolUse hook — run ruff check --fix and ruff format on edited Python files."""

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    file_path = data.get("file_path") or data.get("path") or ""
    path = Path(file_path)

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
