#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PreToolUse hook — validate the `# ctx-ok` escape hatch.

.claude/rules/use-context-mode.md permits `# ctx-ok` only on a command
context-mode cannot do: a genuine state mutation, or a tiny fixed-output
command. The rule states that nothing validates this. That is the half the
context-mode plugin cannot cover — the plugin routes reads, but it does not know
this repo's must-run-direct allowlist, so a read command wearing `# ctx-ok`
passes it untouched.

Deliberately narrow: this hook does NOT re-implement routing. Where the plugin
is absent the mandate is unsatisfiable anyway (there is no ctx_* tool to route
to), so a second classifier would deny reads it cannot offer an alternative for.
This one only judges commands that already opted out.

Classification is per pipeline stage, and git is classified by SUBCOMMAND:
`git log --oneline | head -20` is a read even though its first token is `git`,
which is otherwise a mutation verb.

Blocks with exit 2 + stderr, matching the sibling guards. Fails closed.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import load_event  # type: ignore[import-not-found]

_CTX_OK = re.compile(r"#\s*ctx-ok\b")
_SPLIT = re.compile(r"\|\||&&|[|;&\n]")
_VALUE_OPTS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"})

# Must-run-direct, from use-context-mode.md: state mutation, pass/fail runners,
# short fixed output, interactive/stateful commands.
_ALLOWED = frozenset(
    {
        "git",
        "gh",
        "mkdir",
        "mv",
        "rm",
        "cp",
        "chmod",
        "chown",
        "ln",
        "touch",
        "patch",
        "npm",
        "npx",
        "uv",
        "pip",
        "pipx",
        "make",
        "pytest",
        "tox",
        "cargo",
        "go",
        "docker",
        "kubectl",
        "systemctl",
        "ssh",
        "scp",
        "install",
        "echo",
        "printf",
        "pwd",
        "whoami",
        "date",
        "true",
        "false",
        "exit",
        "ruff",
        "bandit",
        "pyright",
        "pre-commit",
    }
)
# Read/gather verbs that must never carry the hatch.
_READ_VERBS = frozenset(
    {
        "grep",
        "rg",
        "cat",
        "less",
        "more",
        "head",
        "tail",
        "find",
        "ls",
        "tree",
        "wc",
        "awk",
        "sed",
        "jq",
        "curl",
        "wget",
        "du",
        "df",
        "ps",
        "env",
        "stat",
        "diff",
    }
)
# git subcommands whose output is read, not a mutation. `status` is exempt by the
# rule itself (short fixed output), so it is deliberately absent.
_GIT_READS = frozenset(
    {
        "log",
        "diff",
        "show",
        "blame",
        "grep",
        "ls-files",
        "ls-tree",
        "cat-file",
        "describe",
        "shortlog",
        "whatchanged",
        "rev-list",
        "reflog",
    }
)


def _verbs(command: str) -> list[str]:
    """One classification token per pipeline stage: the verb, or `git:<sub>`."""
    out: list[str] = []
    for segment in _SPLIT.split(re.sub(r"#.*$", "", command)):
        tokens = segment.split()
        i = 0
        while i < len(tokens) and "=" in tokens[i] and not tokens[i].startswith("-"):
            i += 1  # VAR=value environment prefix
        if i >= len(tokens):
            continue
        verb = Path(tokens[i]).name
        if verb != "git":
            out.append(verb)
            continue
        i += 1
        while i < len(tokens):
            if tokens[i] in _VALUE_OPTS:
                i += 2
            elif tokens[i].startswith("-"):
                i += 1
            else:
                break
        out.append(f"git:{tokens[i]}" if i < len(tokens) else "git")
    return out


def _deny(reason: str) -> None:
    print(
        f"  DENIED  {reason}\n"
        "          '# ctx-ok' is for a state mutation or a tiny fixed-output command\n"
        "          only — see .claude/rules/use-context-mode.md. Route this through\n"
        "          ctx_execute / ctx_batch_execute and print just what you need.",
        file=sys.stderr,
        flush=True,
    )
    sys.exit(2)


def main() -> None:
    data = load_event()
    if data is None:
        return

    command = (data.get("tool_input") or {}).get("command") or ""
    if not command or not _CTX_OK.search(command):
        return  # no hatch claimed — the plugin's routing guard owns this case

    verbs = _verbs(command)
    if not verbs:
        _deny("'# ctx-ok' on an empty command")

    for verb in verbs:
        if verb.startswith("git:"):
            if verb.removeprefix("git:") in _GIT_READS:
                _deny(f"'# ctx-ok' on a read command ('{verb.replace(':', ' ')}')")
            continue
        if verb in _READ_VERBS:
            _deny(f"'# ctx-ok' on a read/gather command ('{verb}')")
        if verb not in _ALLOWED:
            # Unknown verb: fail closed. An unrecognised command is exactly the
            # case the hatch should not silently cover.
            _deny(f"'# ctx-ok' on an unrecognised command ('{verb}')")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail closed
        print(f"  DENIED  ctx-ok guard failed internally: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)
