"""Shared preamble for the PreToolUse / PostToolUse / Stop hooks in scripts/hooks/.

Library module — imported by the hook scripts, never run directly, so no
shebang and no `# /// script` block. Pure stdlib. Mirrors the sibling-import
precedent in scripts/validate-skill.py (`sys.path.insert(0, __file__ dir)`).
"""

import json
import os
import re
import sys
from pathlib import Path

# `&&` and a backgrounding `&` separate stages; the `&` of a redirection does not.
# A bare `[|;&\n]` class split `make check 2>&1` into a second stage `1`, whose
# verb the ctx-ok guard then denied as unrecognised.
_STAGE_SPLIT = re.compile(r"\|\||&&|[|;\n]|(?<![<>])&(?!>)")
# A comment runs to end of LINE, not end of string: without re.MULTILINE only the
# final line's comment is stripped, and an earlier `#` survives to become a stage
# whose first token is `#`.
_COMMENT = re.compile(r"#.*$", re.MULTILINE)
# Single-quoted spans are literal; double-quoted spans honour backslash escapes.
_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
_MASK = re.compile("\x00(\\d+)\x00")

# git global options that consume the NEXT token as their value. Without these
# the token after them is mistaken for the subcommand, or the scan stops early.
_VALUE_OPTS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"})


def repo_root() -> Path:
    """Repo root: CLAUDE_PROJECT_DIR, else REPO_ROOT, else parents[2] of this dir.

    An empty value counts as absent — `dict.get` would return a present-but-empty
    `CLAUDE_PROJECT_DIR=""`, and `Path("")` is `Path(".")`, silently moving every
    hook's containment boundary to the current working directory.

    An env value that does not point at *this* checkout counts as absent too:
    Claude Code sets CLAUDE_PROJECT_DIR to the session's launch directory, so a
    session opened in the parent of this checkout would otherwise aim every gate
    at a tree with no scripts in it and pass by finding nothing.
    """
    for var in ("CLAUDE_PROJECT_DIR", "REPO_ROOT"):
        val = os.environ.get(var)
        if val and (Path(val) / "scripts" / "hooks" / "_hooklib.py").exists():
            return Path(val)
    return Path(__file__).parents[2]


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


def _edited_path(data: dict) -> Path | None:
    """Resolved absolute path of the file a Write/Edit touched, or None if absent."""
    tool_input = data.get("tool_input") or {}
    raw = tool_input.get("file_path") or data.get("file_path") or data.get("path")
    if not raw:
        return None
    raw = Path(raw)
    return (raw if raw.is_absolute() else repo_root() / raw).resolve()


def event_path() -> Path | None:
    """The path a Write/Edit touched, read straight from the stdin event.

    Collapses the load-event + _edited_path + None-guard preamble the PostToolUse
    hooks all share into one call.
    """
    data = load_event()
    return _edited_path(data) if data is not None else None


def _mask_quoted(command: str) -> tuple[str, list[str]]:
    """Replace each quoted span with an opaque placeholder, keeping the originals.

    Splitting on operators and comments before this step reads shell *syntax*
    inside what is really one argument: `-m "fix: a|b"` became a second stage
    beginning `b"`, and `grep '# ctx-ok'` looked like a trailing comment.
    Masking is enough to fix both without a full shell parser — notably it leaves
    newlines, redirections and subshells splitting exactly as they did.
    """
    spans: list[str] = []

    def take(match: re.Match[str]) -> str:
        spans.append(match.group(0))
        return f"\x00{len(spans) - 1}\x00"

    return _QUOTED.sub(take, command), spans


def _unmask(token: str, spans: list[str]) -> str:
    """Restore masked spans in one token, dropping the surrounding quote marks."""
    return _MASK.sub(lambda m: spans[int(m.group(1))][1:-1], token)


def shell_stages(command: str) -> list[list[str]]:
    """Tokens for each pipeline/list stage, comments and `VAR=value` prefixes stripped.

    A guard that reads only the first stage misses `echo hi && git push origin
    main`, and one that ignores the environment prefix misses `FOO=1 git ...`.
    Empty stages are dropped, so every returned list has at least one token.

    Quoting is honoured (see _mask_quoted) and comments are removed here rather
    than by each caller, so `git_calls` and the ctx-ok guard agree on what a
    command says: a trailing `# push to main later` used to put `main` in the
    push guard's operand list.
    """
    masked, spans = _mask_quoted(command)
    stages: list[list[str]] = []
    for segment in _STAGE_SPLIT.split(_COMMENT.sub("", masked)):
        tokens = [_unmask(t, spans) for t in segment.split()]
        i = 0
        while i < len(tokens) and "=" in tokens[i] and not tokens[i].startswith("-"):
            i += 1
        if i < len(tokens):
            stages.append(tokens[i:])
    return stages


def skip_git_global_opts(tokens: list[str], i: int) -> int:
    """Index of the first non-option token at or after `i`, value-opts consumed.

    `-C dir` and `-c k=v` take the following token as a value; a scan that does
    not consume it reads that value as the subcommand.
    """
    while i < len(tokens):
        if tokens[i] in _VALUE_OPTS:
            i += 2
        elif tokens[i].startswith("-"):
            i += 1  # valueless global flag, or --opt=value
        else:
            break
    return i


def git_calls(command: str) -> list[tuple[str, list[str]]]:
    """(subcommand, args) for every git invocation across the command's stages.

    The subcommand is found by tokenising, not by regex: `git -C dir commit
    --no-verify` and `git -c k=v push` have a value-taking global option between
    `git` and the subcommand, which a `(?:\\s+-\\S+)*` pattern walks straight past.
    """
    calls: list[tuple[str, list[str]]] = []
    for tokens in shell_stages(command):
        if Path(tokens[0]).name != "git":
            continue
        i = skip_git_global_opts(tokens, 1)
        if i < len(tokens):
            calls.append((tokens[i], tokens[i + 1 :]))
    return calls
