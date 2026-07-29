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
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import load_event, repo_root  # type: ignore[import-not-found]

_REPO_ROOT = repo_root()

# A hook cannot fully parse shell, so two mechanisms cover the surface together:
#
# 1. Textual — _DENIED_RE matches the literal `.claude/agents`, and the
#    _CLAUDE_RE + _AGENTS_INDIRECT_RE pair catches variable-built paths
#    (`$D/agents`, `A=agents; … $A …`) and any `.claude/a…` spelling
#    (`.claude/a*`, `.claude/a[g]ents`) after _canonicalize folds escaped,
#    quoted, and repeated/`.`-slash forms.
# 2. Glob expansion — _glob_reaches_agents actually expands glob tokens against
#    the repo, so a metacharacter that obscures the `.claude` root itself
#    (`.?laude/agents`, `.cl*de/agents`) — leaving no literal substring for the
#    textual pass to match — is still caught by the shell's own semantics.
#    _canonicalize therefore must NOT delete glob metacharacters: stripping the
#    `?` in `.?laude` collapses it to `.laude` and hides the match.
#
# Broad on purpose — a false positive costs one blocked Bash call; a false
# negative exposes the CODEOWNERS-gated agent definitions the Read/Edit/Write
# deny list cannot reach for the Bash tool.
_DENIED_RE = re.compile(r"\.claude/agents\b")
_CLAUDE_RE = re.compile(r"\.claude\b")
_AGENTS_INDIRECT_RE = re.compile(r"[=/$]agents?\b|\.claude/a")
_GLOB_META_RE = re.compile(r"[*?\[]")
DENIED = ".claude/agents"


def _canonicalize(command: str) -> str:
    command = command.replace("\\/", "/")  # escaped separators: `.claude\/agents`
    command = re.sub(r"[\"'\\]", "", command)  # quotes/backslashes: `agent"s"`, `\agents`
    command = re.sub(r"/{2,}", "/", command)  # repeated slashes: `.claude//agents`
    command = re.sub(r"/(?:\./)+", "/", command)  # `.` segments: `.claude/./agents`
    return command


def _glob_reaches_agents(command: str) -> bool:
    """True if any glob token expands, under the shell's own semantics, to a path
    at or under .claude/agents/. Catches metacharacters that obscure the literal
    spelling (`.?laude/agents`, `.cl*de/agents`) which the textual pass cannot
    see. Best-effort: expands relative to the repo root. The token's parent is
    probed too, so a write to a not-yet-existing file under a glob-spelled agents
    directory (`> .?laude/agents/new.md`) still resolves the directory itself."""
    for token in re.split(r"[\s;&|<>()]+", command):
        if not token or not _GLOB_META_RE.search(token):
            continue
        for pattern in (token, str(PurePosixPath(token).parent)):
            if not pattern or pattern in (".", "/"):
                continue
            try:
                for hit in _REPO_ROOT.glob(pattern):
                    rel = hit.relative_to(_REPO_ROOT).as_posix()
                    if rel == DENIED or rel.startswith(DENIED + "/"):
                        return True
            except (OSError, ValueError):
                continue
    return False


def _references_agents(command: str) -> bool:
    """True if the command reaches .claude/agents/ by any spelling the shell would
    resolve there — literal, quoted, escaped, variable-built, or glob."""
    c = _canonicalize(command)
    if _DENIED_RE.search(c) or (_CLAUDE_RE.search(c) and _AGENTS_INDIRECT_RE.search(c)):
        return True
    return _glob_reaches_agents(c)


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
