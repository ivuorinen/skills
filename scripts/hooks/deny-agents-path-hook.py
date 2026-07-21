#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PreToolUse hook — block Bash commands that reach into .claude/agents/.

The `permissions.deny` list in .claude/settings.json covers Read/Edit/Write on
`./.claude/agents/**`, but not Bash — `head`, `sed -i`, or a redirection walks
straight past it. This hook closes that surface for the Bash tool.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import load_event  # type: ignore[import-not-found]

# Match the agents directory whether or not a trailing slash follows — `\b` after
# `agents` catches `cd .claude/agents`, a bare `.claude/agents` argument, and
# `.claude/agents/foo.md` alike. Repeated slashes are collapsed first so
# `.claude//agents` cannot slip past. Arbitrary shell cannot be fully parsed in a
# hook, but this closes the write-path bypasses of the old contiguous-substring
# test (`cd .claude/agents && …`, `.claude//agents/…`).
_DENIED_RE = re.compile(r"\.claude/agents\b")
DENIED = ".claude/agents"


def main() -> None:
    data = load_event()
    if data is None:
        return

    command = (data.get("tool_input") or {}).get("command") or ""
    normalized = re.sub(r"/{2,}", "/", command)
    if _DENIED_RE.search(normalized):
        # PreToolUse: exit 2 blocks the call and surfaces stderr to the agent.
        print(f"  DENIED  Bash command references {DENIED}", file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
