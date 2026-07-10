"""Shared preamble for the PostToolUse / Stop hooks in scripts/hooks/.

Library module — imported by the hook scripts, never run directly, so no
shebang and no `# /// script` block. Pure stdlib. Mirrors the sibling-import
precedent in scripts/validate-skill.py (`sys.path.insert(0, __file__ dir)`).
"""

import json
import os
import sys
from pathlib import Path


def repo_root() -> Path:
    """Repo root: CLAUDE_PROJECT_DIR, else REPO_ROOT, else parents[2] of this dir."""
    default = Path(__file__).parents[2]
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.environ.get("REPO_ROOT", default)))


def load_event() -> dict | None:
    """Parse the hook's stdin JSON event; None if empty, malformed, or not an object.

    Every hook opens by reading its event this way — the shared no-op path for
    empty stdin / a non-dict payload lives here rather than in each hook.
    """
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return None
    return data if isinstance(data, dict) else None


def edited_path(data: dict) -> Path | None:
    """Resolved absolute path of the file a Write/Edit touched, or None if absent."""
    tool_input = data.get("tool_input") or {}
    raw = tool_input.get("file_path") or data.get("file_path") or data.get("path")
    if not raw:
        return None
    raw = Path(raw)
    return (raw if raw.is_absolute() else repo_root() / raw).resolve()


def event_path() -> Path | None:
    """The path a Write/Edit touched, read straight from the stdin event.

    Collapses the load-event + edited_path + None-guard preamble the PostToolUse
    hooks all share into one call.
    """
    data = load_event()
    return edited_path(data) if data is not None else None
