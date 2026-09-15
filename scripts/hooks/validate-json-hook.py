#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — validate JSON syntax after Write or Edit."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import event_path, repo_root, report_skip

REPO_ROOT = repo_root()


def main() -> None:
    """Reject malformed JSON the moment it is written.

    A broken manifest or settings file otherwise surfaces far from the edit
    that caused it — as a plugin that fails to load, or a hook that silently
    stops running. An unreadable file does not block the edit, but it is
    reported as unvalidated rather than passed in silence.
    """
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
    except OSError as exc:
        # Unreadable path (dir named *.json, permission denied): no traceback and
        # no block, but no silent pass either (observability-879596c7).
        report_skip("validate-json-hook", f"cannot read: {exc}", f"python3 -m json.tool {path}")


if __name__ == "__main__":
    main()
