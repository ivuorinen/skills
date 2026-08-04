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
#    the repo (from the root and from any `cd` target), so a metacharacter that
#    obscures the `.claude` root itself (`.?laude/agents`, `.cl*de/agents`) or a
#    `cd .claude && cat a*/…` that shifts the glob base — neither leaving a
#    literal substring for the textual pass — is still caught by the shell's own
#    semantics. _canonicalize therefore must NOT delete glob metacharacters:
#    stripping the `?` in `.?laude` collapses it to `.laude` and hides the match.
#
# Broad on purpose — a false positive costs one blocked Bash call; a false
# negative exposes the CODEOWNERS-gated agent definitions the Read/Edit/Write
# deny list cannot reach for the Bash tool.
_DENIED_RE = re.compile(r"\.claude/agents\b")
_CLAUDE_RE = re.compile(r"\.claude\b")
_AGENTS_INDIRECT_RE = re.compile(r"[=/$]agents?\b|\.claude/a")
_GLOB_META_RE = re.compile(r"[*?\[]")
DENIED = ".claude/agents"

# 3. Content-addressed reach — a command can locate a definition by its FILE
#    NAME without ever spelling the directory (`find . -name reviewer.md -exec
#    cat {} +`), so it carries no token the two mechanisms above can see: no
#    `.claude`, no `agents`, and no glob metacharacter. The bare filename is
#    the one token such a command must carry, so match on it.
#
#    Partial by construction: a command that finds the file by CONTENT rather
#    than name (`git ls-files | grep review | xargs cat`) carries neither the
#    path nor the filename, and the only token it does carry ('review') is a
#    nitpicker command name that appears in ordinary commands constantly —
#    matching it would block routine work. CODEOWNERS plus branch protection
#    remains the binding control; this hook raises the cost, it does not close
#    the surface. See CLAUDE.md's PreToolUse section.
_AGENT_FILES = tuple(sorted(p.name for p in (_REPO_ROOT / DENIED).glob("*.md")))


def _canonicalize(command: str) -> str:
    command = command.replace("\\/", "/")  # escaped separators: `.claude\/agents`
    command = re.sub(r"[\"'\\]", "", command)  # quotes/backslashes: `agent"s"`, `\agents`
    command = re.sub(r"/{2,}", "/", command)  # repeated slashes: `.claude//agents`
    command = re.sub(r"/(?:\./)+", "/", command)  # `.` segments: `.claude/./agents`
    return command


def _cd_bases(command: str) -> list[Path]:
    """Directories the command `cd`s into, each a base a later relative glob would
    resolve from. The repo root is always included. A glob-spelled `cd` target
    (`cd .?laude`) is itself expanded from the repo root, so `cd .?laude && …`
    resolves like `cd .claude && …`."""
    bases = [_REPO_ROOT]
    for match in re.finditer(r"(?:^|[\s;&|(])cd\s+([^\s;&|()<>]+)", command):
        raw = match.group(1)
        if _GLOB_META_RE.search(raw):
            try:
                bases.extend(_REPO_ROOT.glob(raw))
            except (OSError, ValueError, NotImplementedError):
                continue
        else:
            bases.append(_REPO_ROOT / raw)
    return bases


def _glob_reaches_agents(command: str) -> bool:
    """True if any glob token expands, under the shell's own semantics, to a path
    at or under .claude/agents/. Catches metacharacters that obscure the literal
    spelling (`.?laude/agents`, `.cl*de/agents`) which the textual pass cannot
    see. Globs are expanded both from the repo root and from any directory the
    command `cd`s into, so `cd .claude && cat a*/reviewer.md` still resolves
    there. The token's parent is probed too, so a write to a not-yet-existing
    file under a glob-spelled agents directory (`> .?laude/agents/new.md`) still
    resolves the directory itself. Absolute tokens are re-based onto the repo
    when they point into it and skipped otherwise — never crashing the hook."""
    agents_dir = (_REPO_ROOT / DENIED).resolve()
    bases = _cd_bases(command)
    for token in re.split(r"[\s;&|<>()]+", command):
        if not token or not _GLOB_META_RE.search(token):
            continue
        for pattern in (token, str(PurePosixPath(token).parent)):
            if not pattern or pattern in (".", "/"):
                continue
            rel = pattern
            if PurePosixPath(pattern).is_absolute():
                try:
                    rel = str(PurePosixPath(pattern).relative_to(_REPO_ROOT))
                except ValueError:
                    continue  # absolute but outside the repo — nothing to check
            for base in bases:
                try:
                    hits = list(base.glob(rel))
                except (OSError, ValueError, NotImplementedError):
                    continue  # unsupported pattern must not crash the guard open
                for hit in hits:
                    resolved = hit.resolve()
                    if resolved == agents_dir or agents_dir in resolved.parents:
                        return True
    return False


def _references_agents(command: str) -> bool:
    """True if the command reaches .claude/agents/ by any spelling the shell would
    resolve there — literal, quoted, escaped, variable-built, or glob."""
    c = _canonicalize(command)
    if _DENIED_RE.search(c) or (_CLAUDE_RE.search(c) and _AGENTS_INDIRECT_RE.search(c)):
        return True
    if any(name in c for name in _AGENT_FILES):
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
