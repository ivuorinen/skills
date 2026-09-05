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
from _hooklib import (  # type: ignore[import-not-found]
    load_event,
    shell_stages,
    skip_git_global_opts,
)

# The hatch is a TRAILING comment, per the rule's "append `# ctx-ok`". Anchoring
# matters both ways: it must follow whitespace (so a quoted `'# ctx-ok'` being
# searched for as a literal is content, not a claim) and it must end the command
# (so the marker mid-command is not read as opting the whole line out).
_CTX_OK = re.compile(r"(?:^|\s)#\s*ctx-ok\s*$")

# Must-run-direct, from use-context-mode.md: state mutation, pass/fail runners,
# short fixed output, interactive/stateful commands.
#
# Shell builtins that navigate or mutate shell state belong here for the same
# reason `mkdir` does — the sandbox cannot carry the effect back. `cd` matters
# most: it prefixes a huge share of real commands, and because classification is
# per stage, `cd repo && git push` is judged on `cd` as well as on `git push`.
#
# BOTH script-runner classes belong here, per use-uv-runner.md. `uv` runs the
# internal dev tooling; `python3` runs the shipped stdlib-only tools under
# `skills/*/scripts/`, whose findings-store subcommands (`new`, `resolve`,
# `index`, `baseline`, `migrate`) are exactly the state mutations this hatch
# exists to permit. Omitting it deadlocked the two rules: once a session edits a
# shipped script, _conventions.md forbids the `np_*` MCP tools — the server
# holds the pre-edit modules in memory — leaving the CLI as the only sanctioned
# interface, and this guard denied it. An agent that hit that had no sanctioned
# way to file a finding at all, and nothing recorded the drop.
#
# This does widen the hatch to `python3 -c "print(open(f).read())"`. Accepted and
# consistent: `uv`, `make` and `npm` below already run arbitrary code under the
# same allowance, and this hook's docstring states it does NOT re-implement
# routing. Blocking the repo's own mandated mutation path to catch a
# hypothetical read trades a real failure for a speculative one.
_ALLOWED = frozenset(
    {
        "cd",
        "pushd",
        "popd",
        "export",
        "source",
        "unset",
        "set",
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
        "python3",
        "python",
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
    """One classification token per pipeline stage: the verb, or `git:<sub>`.

    Comment stripping lives in shell_stages, not here: the local `re.sub(r"#.*$")`
    this used to do lacked re.MULTILINE, so in a multi-line command a comment on
    any but the last line survived and became a stage whose verb was `#`.
    """
    out: list[str] = []
    for tokens in shell_stages(command):
        verb = Path(tokens[0]).name
        if verb != "git":
            out.append(verb)
            continue
        i = skip_git_global_opts(tokens, 1)
        out.append(f"git:{tokens[i]}" if i < len(tokens) else "git")
    return out


def _reject_reason(verb: str) -> str | None:
    """Why this stage may not wear the hatch, or None if it may."""
    if verb.startswith("git:"):
        subcommand = verb.removeprefix("git:")
        if subcommand in _GIT_READS:
            return f"'# ctx-ok' on a read command ('git {subcommand}')"
        return None
    if verb in _READ_VERBS:
        return f"'# ctx-ok' on a read/gather command ('{verb}')"
    if verb not in _ALLOWED:
        # Unknown verb: fail closed. An unrecognised command is exactly the
        # case the hatch should not silently cover.
        return f"'# ctx-ok' on an unrecognised command ('{verb}')"
    return None


def _deny(reason: str) -> None:
    """Block the call and name both the reason and the way out.

    The message states the alternative rather than only the refusal: a denial
    that does not say what to run instead invites the same command back with
    a different spelling.
    """
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
    """Validate a claimed `# ctx-ok` escape hatch.

    Only commands that claim the hatch are judged — an unmarked command is
    the routing guard's business, not this one's. Every verb in the command
    is checked, not just the first, so appending a mutation to a read does
    not launder the read past the hatch.
    """
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
        reason = _reject_reason(verb)
        if reason is not None:
            _deny(reason)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail closed
        print(f"  DENIED  ctx-ok guard failed internally: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)
