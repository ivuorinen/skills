#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — validate JSON syntax after Write or Edit."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import event_path, repo_root  # noqa: E402  # type: ignore[import-not-found]

REPO_ROOT = repo_root()


def main() -> None:
    path = event_path()
    if path is None:
        return

    if path.suffix != ".json":
        return

    # Only validate files inside the project; ignore anything resolving outside it.
    if not path.is_relative_to(REPO_ROOT.resolve()):
        return

    if not path.exists():
        return

    try:
        text = path.read_text(encoding="utf-8")
        json.loads(text)
    except json.JSONDecodeError as e:
        # PostToolUse surfaces only exit 2 + stderr back to the agent.
        print(f"  INVALID JSON  {path}: {e}", file=sys.stderr, flush=True)
        sys.exit(2)
    except OSError:
        # Unreadable path (dir named *.json, permission denied) — fail open,
        # matching the other hooks rather than crashing with a traceback.
        return


if __name__ == "__main__":
    main()
