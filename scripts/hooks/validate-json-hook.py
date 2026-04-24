#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — validate JSON syntax after Write or Edit."""

import json
import sys
from pathlib import Path


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    file_path = data.get("file_path") or data.get("path") or ""
    path = Path(file_path)

    if path.suffix != ".json":
        return

    if not path.exists():
        return

    try:
        text = path.read_text(encoding="utf-8")
        json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  INVALID JSON  {path}: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
