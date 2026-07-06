#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — validate JSON syntax after Write or Edit."""

import json
import os
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
