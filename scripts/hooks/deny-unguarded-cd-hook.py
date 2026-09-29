#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PreToolUse hook — deny a context-mode shell script that writes after a cd that can fail.

Shell code sent to ctx_execute runs against the real filesystem and carries on
after a failed `cd`. A probe script whose `cd` failed once ran `git init`,
`git config user.email` and `git add -A` in the real repository. The project
memory mandates `cd <dir> || exit 1` before any mutation in such a script, and
nothing checked it (agent-hooks-da747c0c).

A `cd` (or `pushd`) counts as guarded when `|| …` handles its failure, when it
heads an `&&` chain that reaches the write, or when `set -e`/`set -o errexit`
ran before it and no `set +e`/`set +o errexit` has cleared it since. What
counts as a write is `_hooklib.write_targets` — `find -delete`, `rsync`,
`tar -x` and the rest — shared with the protected-write guard. A `cd` inside a
`( … )` or `$( … )` subshell is forgotten when the subshell closes. Each
batch command is judged on its own, as each runs in its own shell. Bash is out
of scope: its working directory is the project.

Ceiling: `cd x || true` counts as guarded, a write performed by a script or an
interpreter the stage merely invokes is not recognised, and backticks do not
scope a `cd` the way a subshell does.
"""

import re
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import (
    _COMMENT,
    _CONTINUATION,
    _STAGE_SPLIT,
    _mask_quoted,
    _tool_input,
    _unmask,
    _wrapper_variants,
    load_event_strict,
    redirect_targets,
    skip_git_global_opts,
    strip_reserved,
    write_targets,
)

# _hooklib's stage separators, captured, so the separator after each stage is known.
# Built from the pattern rather than copied: the copy had drifted, and cut
# `>|` as a pipe exactly where _hooklib had to stop doing so
# (agent-loopholes-ff4a37fd).
_SPLIT = re.compile(f"({_STAGE_SPLIT.pattern})")
_CHDIR = frozenset({"cd", "pushd"})
_OPENERS = frozenset({"(", "$("})
# git subcommands that only read; every other one is treated as a write.
_GIT_READS = frozenset(
    {"status", "log", "diff", "show", "rev-parse", "ls-files", "ls-tree", "blame", "grep"}
)
_ERREXIT = re.compile(r"[-+][a-zA-Z]*e[a-zA-Z]*")


def _verb_writes(tokens: list[str]) -> bool:
    """True if this stage's own verb changes files or the repository.

    Which non-git verbs write is `_hooklib.write_targets`, the model the
    protected-write guard uses too. This guard kept its own list, which had
    drifted from that guard's in both directions (agent-loopholes-6bb5ff99).
    """
    if PurePosixPath(tokens[0]).name == "git":
        index = skip_git_global_opts(tokens, 1)
        return index < len(tokens) and tokens[index] not in _GIT_READS
    return write_targets(tokens) is not None


def _writes(tokens: list[str]) -> bool:
    """True if a stage, read past `NAME=value` prefixes and wrappers, writes."""
    while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
        tokens = tokens[1:]
    return bool(tokens) and any(_verb_writes(v) for _env, v in _wrapper_variants(tokens))


def _redirects(segment: str) -> bool:
    """True if a stage redirects output into a file other than /dev/null.

    Every operator `_hooklib.redirect_targets` knows counts: `>|` and `>&` wrote
    a file after a failed cd unseen (agent-loopholes-ff4a37fd).
    """
    return any(target != "/dev/null" for target in redirect_targets(segment))


def _errexit_after(tokens: list[str], errexit: bool) -> bool:
    """Whether errexit is on after this stage, given whether it was before.

    `set -e`, `-euo` and `-o errexit` turn it on; `set +e`, `+eu` and
    `+o errexit` turn it off again. It used to be a latch that only a set could
    move, so `set -e; set +e; cd /nope; rm -rf build` counted the cd as guarded
    by an errexit the script had already cleared (agent-loopholes-d707fb69).
    The last spelling on the line wins, as it does in the shell.
    """
    if tokens[0] != "set":
        return errexit
    args = tokens[1:]
    for index, arg in enumerate(args):
        if arg in ("-o", "+o") and args[index + 1 : index + 2] == ["errexit"]:
            errexit = arg == "-o"
        elif _ERREXIT.fullmatch(arg):
            errexit = arg[0] == "-"
    return errexit


def _unguarded_write(script: str) -> tuple[str, str] | None:
    """(the unguarded cd, the write it exposes) for the first such pair, else None."""
    masked, spans = _mask_quoted(script)
    parts = _SPLIT.split(_CONTINUATION.sub(" ", _COMMENT.sub("", masked)))
    exposed: str | None = None  # a cd whose failure reaches the stages after it
    chained: str | None = None  # a cd guarded only while its `&&` chain lasts
    errexit = False
    stack: list[tuple[str | None, str | None]] = []
    for index in range(0, len(parts), 2):
        # Reserved words first: `cd /nope; for f in *; do rm -rf "$f"; done`
        # put the delete behind `do`, a verb no write set names, and `then cd
        # /nope` hid the cd itself (see `_hooklib.strip_reserved`).
        tokens = strip_reserved([_unmask(token, spans) for token in parts[index].split()])
        sep = parts[index + 1] if index + 1 < len(parts) else ""
        if tokens:
            if exposed and (_writes(tokens) or _redirects(parts[index])):
                return exposed, " ".join(tokens)
            errexit = _errexit_after(tokens, errexit)
            if PurePosixPath(tokens[0]).name in _CHDIR and not errexit and sep != "||":
                chained, exposed = (
                    (" ".join(tokens), exposed) if sep == "&&" else (None, " ".join(tokens))
                )
        if chained and sep != "&&":
            exposed, chained = chained, None
        if sep in _OPENERS:
            stack.append((exposed, chained))
        elif sep == ")" and stack:
            exposed, chained = stack.pop()
    return None


def _scripts(data: dict) -> list[str]:
    """The shell scripts a context-mode call runs: its shell `code`, each batch command."""
    tool_input = _tool_input(data)
    code = tool_input.get("code")
    scripts = [code] if tool_input.get("language") == "shell" and isinstance(code, str) else []
    commands = tool_input.get("commands")
    if isinstance(commands, list):
        scripts += [
            c["command"]
            for c in commands
            if isinstance(c, dict) and isinstance(c.get("command"), str)
        ]
    return scripts


def main() -> None:
    """Deny the call when any script it runs writes after a cd that can fail."""
    data = load_event_strict()
    for script in _scripts(data):
        found = _unguarded_write(script)
        if found is not None:
            cd, write = found
            print(
                f"  DENIED  `{cd}` can fail, and the script carries on: `{write}`\n"
                "          would then run wherever the shell started — possibly the real\n"
                "          repository. Guard the cd: `cd <dir> || exit 1`, or `set -e` first.",
                file=sys.stderr,
                flush=True,
            )
            sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail closed — exit 1 would let the call through
        print(f"  DENIED  unguarded-cd guard failed internally: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)
