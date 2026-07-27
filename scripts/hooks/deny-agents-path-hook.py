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
# `.claude/agents/foo.md` alike. Arbitrary shell cannot be fully parsed in a hook,
# but _canonicalize folds the filesystem-equivalent spellings (escaped, quoted,
# repeated/`.` slashes, glob metacharacters) first, and _AGENTS_INDIRECT_RE
# catches the variable-built paths and any `.claude/a…` spelling the literal
# match misses.
_DENIED_RE = re.compile(r"\.claude/agents\b")
# Catch-all: the literal match misses shell-variable paths (`$D/agents/…`),
# assignments (`A=agents; … $A …`), and globs. Because _canonicalize strips glob
# metacharacters first, a truncated glob like `.claude/a*` or `.claude/a[g]ents`
# folds to `.claude/a…` / `.claude/agents`; the `\.claude/a` branch fires on the
# former and _DENIED_RE on the latter. `.claude/` has one `a*` child (`agents`),
# so any `.claude/a…` the shell would expand resolves there. Broad on purpose — a
# false positive costs one blocked Bash call; a false negative exposes the
# CODEOWNERS-gated agent definitions the Read/Edit/Write deny list cannot reach
# for the Bash tool.
_CLAUDE_RE = re.compile(r"\.claude\b")
_AGENTS_INDIRECT_RE = re.compile(r"[=/$]agents?\b|\.claude/a")
DENIED = ".claude/agents"


def _canonicalize(command: str) -> str:
    command = command.replace("\\/", "/")  # escaped separators: `.claude\/agents`
    command = re.sub(r"[\"'\\]", "", command)  # quotes/backslashes: `agent"s"`, `\agents`
    command = re.sub(r"[*?\[\]]", "", command)  # glob metachars: `.claude/a*`, `.claude/a[g]ents`
    command = re.sub(r"/{2,}", "/", command)  # repeated slashes: `.claude//agents`
    command = re.sub(r"/(?:\./)+", "/", command)  # `.` segments: `.claude/./agents`
    return command


def _references_agents(command: str) -> bool:
    """True if the command reaches .claude/agents/ by any spelling the shell would
    resolve there — literal, quoted, escaped, variable-built, or glob."""
    c = _canonicalize(command)
    return bool(_DENIED_RE.search(c) or (_CLAUDE_RE.search(c) and _AGENTS_INDIRECT_RE.search(c)))


def main() -> None:
    data = load_event()
    if data is None:
        return

    command = (data.get("tool_input") or {}).get("command") or ""
    if _references_agents(command):
        # PreToolUse: exit 2 blocks the call and surfaces stderr to the agent.
        print(f"  DENIED  Bash command references {DENIED}", file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
