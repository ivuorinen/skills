"""Shared preamble for the PreToolUse / PostToolUse / Stop hooks in scripts/hooks/.

Library module — imported by the hook scripts, never run directly, so no
shebang and no `# /// script` block. Pure stdlib. Mirrors the sibling-import
precedent in scripts/validate-skill.py (`sys.path.insert(0, __file__ dir)`).
"""

import itertools
import json
import os
import re
import shlex
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NoReturn

# `&&` and a backgrounding `&` separate stages; the `&` of a redirection does not.
# A bare `[|;&\n]` class split `make check 2>&1` into a second stage `1`, whose
# verb the ctx-ok guard then denied as unrecognised.
#
# `$(`, a backtick and a bare `(` are stage boundaries for the same reason `|`
# is: each one starts a command that the shell EXECUTES. Without them
# `echo $(git push origin main)` is a single stage whose first token is `echo`,
# and every guard built on this function — the git guard, the protected-write
# half of the agents guard, the ctx-ok hatch — judged the wrapper and never saw
# the nested call. Splitting on the delimiters rather than parsing them keeps
# nesting free: `$(a $(b))` yields `a` and `b` as separate stages.
#
# `\$\(` precedes the character class so the `$` is consumed with its paren
# rather than left behind as a one-token stage. The closing `)` splits too —
# what follows it is back in the outer command.
#
# A `|` straight after `>` is the clobber redirection `>|`, not a pipe. Cutting
# there left `echo x >` as one stage and the target as the verb of the next, so
# no guard saw what `echo x >| scripts/hooks/ruff-hook.py` wrote
# (agent-loopholes-ff4a37fd).
_STAGE_SPLIT = re.compile(r"\|\||&&|\$\(|(?<!>)\||[;\n`()]|(?<![<>])&(?!>)")

# Every redirection operator that opens a file for writing, and its target:
# `>`, `>>`, `>|` (clobber past noclobber), `>&`/`&>`/`&>>` (stdout and stderr),
# `<>` (read-write, writable through the descriptor) and any of them behind a
# descriptor number (`2>`, `1>|`). The first version matched `>{1,2}` alone, so
# `>|` and `>&` each wrote the enforcement surface past both write guards
# (agent-loopholes-ff4a37fd). A `&` or digit prefix needs no alternative of its
# own: the operator after it is matched anyway.
_REDIRECT = re.compile(r"(>>|>\||>&|<>|>)\s*([^\s;&|<>()]+)")
# `>&1`, `2>&-`: after `>&`, a descriptor number or `-` duplicates or closes a
# descriptor and names no file. After any other operator it is a file name.
_FD_TARGET = re.compile(r"\d+-?|-")


def redirect_targets(text: str) -> list[str]:
    """Every file a redirection in `text` writes, in order.

    Shared by the protected-write guard and the unguarded-cd guard, whose
    private copies had drifted to the same blind spot. Ceiling: a target the
    shell builds at runtime is returned as spelled, for the caller to judge.
    """
    return [
        target
        for op, target in _REDIRECT.findall(text)
        if not (op == ">&" and _FD_TARGET.fullmatch(target))
    ]


# Command wrappers: the token that runs is the one AFTER these, so a guard
# reading `tokens[0]` sees the wrapper and skips the stage. `env git commit
# --no-verify` was the whole bypass — one word, and every rule in the git guard
# became unreachable.
_WRAPPERS = frozenset(
    {
        "env",
        "command",
        "builtin",
        "exec",
        "sudo",
        "doas",
        "nice",
        "ionice",
        "nohup",
        "setsid",
        "stdbuf",
        "time",
        "timeout",
        "xargs",
    }
)
# Shells: `bash -c '<string>'` runs a whole command line that arrives here as ONE
# quoted token, so every guard judged the wrapper and never the git call, the
# protected write or the restore inside it (agent-loopholes-015b8134). `busybox`
# is here because `busybox sh -c …` is the same shape one word further in.
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "mksh", "fish", "busybox"})
# Shell options whose value is the NEXT token, so that token is not the operand.
_SHELL_VALUE_OPTS = frozenset({"-o", "+o", "-O", "+O", "--rcfile", "--init-file"})
# Reserved words that may open a stage before the command it runs. A guard
# reading `tokens[0]` saw `then` in `if true; then git commit --no-verify; fi`
# and judged nothing — every shell guard passed a command behind `if`, `then`,
# `do`, `{` or `!`. `strip_reserved` drops them.
_RESERVED = frozenset({"if", "then", "elif", "else", "do", "while", "until", "!", "{"})
# How many nested `sh -c` payloads are unwrapped precisely; past it, the payload
# is split coarsely (see `_coarse_stages`), never left folded.
_MAX_SHELL_DEPTH = 4
# A comment runs to end of LINE, not end of string: without re.MULTILINE only the
# final line's comment is stripped, and an earlier `#` survives to become a stage
# whose first token is `#`.
# `#[^\n]*` rather than `#.*$` with re.MULTILINE. Identical meaning — `.` never
# matches a newline, so `.*$` already stopped at the line end — but `$` is an
# anchor the engine can retry, and `re.sub` restarts a match attempt at every
# position, which is the polynomial blow-up CodeQL reports (py/polynomial-redos)
# on a hook payload. The character class cannot retry.
#
# The lookbehind makes `#` a comment only where bash starts one: at the start of
# a word. Cutting at every `#` turned `git commit -m issue#12 --no-verify` into
# `git commit -m issue` and allowed it (agent-loopholes-0c18e6b9). A quoted span
# is masked before this runs, so its placeholder's NUL is what precedes `#` in
# `'a'#b`, which bash also reads as one word. Still a character class, no retry.
_COMMENT = re.compile(r"(?<![^\s;&|()])#[^\n]*")
# Single-quoted spans are literal; double-quoted spans honour backslash escapes.
# Possessive quantifiers (`*+`, Python 3.11+). The two inner alternatives are
# already disjoint, so a *terminated* quote never backtracks — but an
# unterminated one makes the engine unwind the whole span one character at a
# time, once per starting position. A hook payload is attacker-influenced, and
# an unterminated quote is exactly what a hostile one would carry. Possessive
# matching forbids that unwind; the match simply fails, which is the correct
# answer for an unterminated span.
_QUOTED = re.compile(r"'[^']*+'|\"(?:\\.|[^\"\\])*+\"")
_MASK = re.compile("\x00(\\d+)\x00")
# The escapes bash removes before a command sees its argv. A guard comparing
# tokens that still carry them read `\-\-no-verify` and `$'--no-verify'` as
# something other than the option git receives (agent-loopholes-0c18e6b9).
_UNQUOTED_ESCAPE = re.compile(r"\\(.)", re.DOTALL)
_DOUBLE_QUOTED_ESCAPE = re.compile(r"\\([$`\"\\\n])")
_ANSI_C_ESCAPE = re.compile(
    r"\\(x[0-9a-fA-F]{1,2}|u[0-9a-fA-F]{1,4}|U[0-9a-fA-F]{1,8}|[0-7]{1,3}|.)", re.DOTALL
)
_ANSI_C_SIMPLE = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n"}
_ANSI_C_SIMPLE |= {"r": "\r", "t": "\t", "v": "\v"}
# A backslash-newline is a line continuation, not a stage boundary. Splitting on
# it made `git push \<newline> origin main` parse as ('push', ['\\']) — no second
# operand, so the push guard fell through to HEAD and allowed a push to main from
# a feature branch. Same for `git commit \<newline> --no-verify`.
_CONTINUATION = re.compile(r"\\\n")

# git global options that consume the NEXT token as their value. Without these
# the token after them is mistaken for the subcommand, or the scan stops early.
_VALUE_OPTS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"})

# How many nested `env -S` payloads `_split_string_payload` unwraps. Four is far
# past any legible command and keeps a hostile payload from making the guard the
# slow part of every Bash call.
_MAX_SPLIT_STRING_DEPTH = 4


# Seconds, shared by every hook that shells out. An unbounded call is
# unrecoverable from the user's side: a PostToolUse hook that blocks freezes the
# session with no output and no signal, and `uv run` resolves an environment
# from the network on a cold cache. Generous enough for that resolve, short
# enough that a hung gate surfaces as a failure instead of a frozen session.
# deny-unsafe-git-hook.py uses 10 for a bare `git rev-parse`.
HOOK_TIMEOUT = 120


def report_skip(hook: str, reason: str, command: str) -> NoReturn:
    """Say that a hook's validation did not run, and how to run it by hand; exit 1.

    A validator that was missing, hung or could not start used to end its hook
    with exit 0 and no output — the same signal as a pass, so an agent kept
    building on a file nothing had judged (observability-879596c7). Exit 1 is
    Claude Code's non-blocking error: the tool call stands and the line is shown,
    so the skip is visible without blocking an edit the gate never saw. CI
    remains the binding gate.
    """
    print(
        f"  {hook}: validation did not run ({reason}); run `{command}` by hand",
        file=sys.stderr,
        flush=True,
    )
    sys.exit(1)


def stop_feedback(text: str) -> None:
    """Hand a Stop hook's reminder to the agent as `additionalContext`, exit 0.

    The hooks reference recommends this over exit 2 for a Stop hook that is
    working as designed and giving guidance: it continues the conversation under
    the same loop protections (`stop_hook_active`, the consecutive-continuation
    cap) but carries no hook-error notification, where exit 2 reports the
    reminder as a failed hook. Exit 0 is required, not incidental: exit 2's
    block is the one outcome JSON cannot override. stdout must hold this object
    and nothing else, or Claude Code reads it as plain text and drops it.
    """
    payload = {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": text}}
    print(json.dumps(payload), flush=True)


# The checkout these hooks ship in, derived from `__file__`. Every validator a
# hook EXECUTES comes from here; `repo_root()` is only the tree being validated
# and the subprocess `cwd`. Deriving executed paths from the environment let a
# CLAUDE_PROJECT_DIR naming another checkout that carries `_hooklib.py` choose
# which validators ran, and was reported as py/command-line-injection
# (audit-1e48d360). A path built from `__file__` no environment can move.
SHIPPED_ROOT = Path(__file__).resolve().parents[2]


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


def load_event_strict() -> dict:
    """Parse the hook's stdin JSON event; raise ValueError if it cannot be judged.

    The PreToolUse guards' loader. `load_event` maps an empty, truncated or
    non-object event to None, and each guard returned on None — exit 0, an
    allow — so a harness fault that handed over a broken event let through
    `--no-verify`, a write to scripts/hooks and a push to a protected branch
    alike (errors-4a2d2f34). A guard that cannot read the call must not allow
    it: raising sends it to the guard's fail-closed arm, which denies (or, for
    the restore guard, asks). PostToolUse and Stop hooks keep the lenient
    loader, because an event they cannot read gives them nothing to report on.
    """
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError) as exc:
        raise ValueError(f"unreadable hook event: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"hook event is a {type(data).__name__}, not an object")
    return data


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


def _tool_input(data: dict) -> dict:
    """The event's `tool_input`, or an empty dict when it is absent or not an object."""
    tool_input = data.get("tool_input")
    return tool_input if isinstance(tool_input, dict) else {}


def event_command(data: dict) -> str:
    """The shell text a tool call will run, whichever tool carries it.

    Bash carries it in `command`. The context-mode tools carry it in `code` when
    `language` is `shell`, and a batch in each `commands[].command`. Every shell
    guard read `command` alone, so none of them saw a context-mode call — the
    very tool `.claude/rules/use-context-mode.md` sends shell work to, and the
    one whose failed `cd` once staged 61 paths with `git add -A`
    (agent-loopholes-41c1b2f3).

    A `cwd` is rendered as a leading `cd`, so a guard resolving paths against a
    `cd` target resolves from it. Batch commands are joined as separate lines;
    a `cd` in one then seems to carry into the next, which only adds a base a
    path is checked from. A value that is not a string is ignored, not raised on.
    """
    tool_input = _tool_input(data)
    parts = [tool_input.get("command")]
    if tool_input.get("language") == "shell":
        parts.append(tool_input.get("code"))
    commands = tool_input.get("commands")
    if isinstance(commands, list):
        parts += [c.get("command") for c in commands if isinstance(c, dict)]
    text = "\n".join(p for p in parts if isinstance(p, str) and p)
    cwd = tool_input.get("cwd")
    if text and isinstance(cwd, str) and cwd:
        text = f"cd {shlex.quote(cwd)}\n{text}"
    return text


def foreign_code(data: dict) -> str:
    """Code a context-mode call runs in a language other than shell, else "".

    It cannot be tokenized as shell, so no guard can tell which command it runs.
    Each guard therefore refuses it wherever it merely names what that guard
    protects. Ceiling: a name assembled at runtime (`'.cla' + 'ude'`) carries no
    such token and passes.

    Shell text that feeds a shell on stdin (`echo 'git push origin main' | bash`,
    `curl … | sh`) is returned too. The command the inner shell runs is data on
    the outer command line, not a stage, so no tokenizing guard can judge it
    either (agent-loopholes-015b8134); it gets the same name-based refusal.
    """
    tool_input = _tool_input(data)
    code = tool_input.get("code")
    if tool_input.get("language") in (None, "shell") or not isinstance(code, str):
        command = event_command(data)
        return command if command and feeds_a_shell(command) else ""
    return code


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
        """Record one quoted span and return its opaque placeholder.

        The placeholder carries the span's index in `spans`, so `_unmask`
        restores the exact original text rather than a re-quoted approximation.
        The NUL delimiters keep it from colliding with anything a real shell
        command can contain.
        """
        spans.append(match.group(0))
        return f"\x00{len(spans) - 1}\x00"

    return _QUOTED.sub(take, command), spans


def _ansi_c(match: re.Match[str]) -> str:
    """Decode one `$'...'` escape the way bash does.

    `$'\\x2d\\x2dno-verify'` reaches git as `--no-verify`, so leaving the escape
    in the token let the option past every membership test. Code points past
    Unicode's range clamp rather than raise: a guard that crashes on a hostile
    escape allows the call. `\\cX` control escapes are not decoded — the ceiling.
    """
    esc = match.group(1)
    if len(esc) > 1 and esc[0] in "xuU":
        code = int(esc[1:], 16)
    elif esc[0] in "01234567":
        code = int(esc, 8)
    else:
        return _ANSI_C_SIMPLE.get(esc, esc)
    return chr(min(code, 0x10FFFF))


def _unmask(token: str, spans: list[str]) -> str:
    """Restore one token to the word bash passes on: quotes dropped, escapes removed.

    Outside quotes a backslash escapes any character; inside double quotes only
    the characters bash lists; inside single quotes none. A `$` directly before a
    quoted span is quoting, not content — `$'...'` additionally decodes its
    escapes. Before agent-loopholes-0c18e6b9 the escapes stayed in the token, so
    `\\-\\-no-verify` never compared equal to the option git actually receives.
    """
    out: list[str] = []
    pos = 0
    for match in _MASK.finditer(token):
        lead, span = token[pos : match.start()], spans[int(match.group(1))]
        body = span[1:-1]
        ansi = lead.endswith("$")
        lead = lead.removesuffix("$")
        if span[0] == '"':
            body = _DOUBLE_QUOTED_ESCAPE.sub(r"\1", body)
        elif ansi:
            body = _ANSI_C_ESCAPE.sub(_ansi_c, body)
        out += [_UNQUOTED_ESCAPE.sub(r"\1", lead), body]
        pos = match.end()
    out.append(_UNQUOTED_ESCAPE.sub(r"\1", token[pos:]))
    return "".join(out)


def _split_string_payload(tokens: list[str], depth: int = 0) -> list[str]:
    """`tokens` with every `env -S` payload expanded into the tokens it carries.

    `env -S 'GIT_CONFIG_COUNT=1 … git commit -m x'` is one shell word, so the
    scan below saw no `git` token and emitted no inner variant — the whole
    command the guard exists to judge sat inside a single operand. GNU `env`
    splits that payload itself at execution time, so the guard has to split it
    too or the wrapper it already knows about becomes a way through it.

    All four spellings `env` accepts are handled: `-S X`, `-SX`,
    `--split-string X` and `--split-string=X`. A payload that does not tokenize
    falls back to whitespace splitting rather than being dropped — refusing to
    look is how the operand became invisible in the first place, and an
    over-split payload can only add candidate stages, never remove one.

    An expanded payload is expanded again, because a payload may carry another
    `env -S`. `env -S 'env -S "git push origin main"'` splits once into `env`,
    `-S`, `git push origin main`, leaving the git call one opaque token that no
    later scan matches — the same invisible operand this expansion exists to
    remove, reinstated one level down. GNU `env` keeps unwrapping it at
    execution time, so the guard has to as well.

    `_MAX_SPLIT_STRING_DEPTH` bounds the recursion, because "strictly shorter"
    is not the same as "shallow": a token spelled `-S-S-S-S…` re-enters at two
    characters a level, so a few kilobytes of operand would exhaust the stack of
    a guard that runs before every Bash call.

    Reaching that bound stops the *precise* expansion, never the looking. The
    remaining tokens are whitespace-split and stripped of shell quoting instead,
    which is what the depth-1 fallback above already does for a payload `shlex`
    refuses, and for the same reason: coarser only ever adds candidate stages,
    so a nest too deep to parse exactly is judged rather than waved through.
    Stopping at the bound with the payload still folded would have made
    `env -S` nested past the cap the one spelling that reaches git untouched.
    """
    out: list[str] = []
    i = 0
    while i < len(tokens):
        token, payload = tokens[i], None
        if token in ("-S", "--split-string") and i + 1 < len(tokens):
            payload, i = tokens[i + 1], i + 2
        elif token.startswith("-S") and len(token) > 2:
            payload, i = token[2:], i + 1
        elif token.startswith("--split-string="):
            payload, i = token.split("=", 1)[1], i + 1
        else:
            out.append(token)
            i += 1
            continue
        try:
            expanded = shlex.split(payload)
        except ValueError:
            expanded = payload.split()
        if depth < _MAX_SPLIT_STRING_DEPTH:
            expanded = _split_string_payload(expanded, depth + 1)
        else:
            expanded = [word.strip("'\"\\") for tok in expanded for word in tok.split()]
        out.extend(expanded)
    return out


def strip_reserved(tokens: list[str]) -> list[str]:
    """`tokens` without the leading reserved words that only open a construct.

    `if true; then git push origin main; fi` splits into stages `if true`,
    `then git push origin main` and `fi`, and the git call sat behind `then`,
    where no guard looked for it. The same held for `do` in a loop body, `{`
    in a group, `!` in a negation, and `while`/`until` conditions. Only the
    leading words are dropped: an operand spelled `then` is still an operand.
    """
    i = 0
    while i < len(tokens) and tokens[i] in _RESERVED:
        i += 1
    return tokens[i:]


def _assignments(tokens: list[str]) -> dict[str, str]:
    """Every `NAME=value` operand in `tokens`, in order.

    Shared by the stage prefix and the wrapper prefix, which differ only in
    where the assignments sit: a stage's lead it, while `env`'s follow the
    wrapper name and may be interleaved with its own options
    (`env -u FOO A=1 git …`). Matching the shape rather than a position covers
    both without modelling either grammar.
    """
    out: dict[str, str] = {}
    for token in tokens:
        if "=" in token and not token.startswith("-"):
            name, _, value = token.partition("=")
            out[name] = value
    return out


def _wrapper_variants(tokens: list[str], depth: int = 0) -> list[tuple[dict[str, str], list[str]]]:
    """The stage, plus every git call a leading wrapper hides, with its assignments.

    The assignments matter as much as the call. `env GIT_CONFIG_COUNT=1
    GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x`
    puts them *after* the wrapper, where the stage-level prefix scan in
    `shell_stages_with_env` never reaches — it stops at the `env` token. The
    emitted variant therefore carried an empty environment map and
    `_global_denial` missed the hook-disabling route that the same assignments
    written without `env` are denied for. Each variant now carries what the
    prefix it skipped applies.

    Each wrapper has its own option grammar — `nice -n 10 git push` puts two
    tokens between the wrapper and the command, `env -u FOO git push` two more —
    so stripping a fixed prefix models one spelling and misses the rest. Emitting
    every suffix that begins at a word which is neither an option nor an
    assignment models none of them and misses no spelling. Bounded by the
    stage's own length.

    Every such word, not only `git`: the first version emitted a suffix only at
    a `git` token, so `env rm -f scripts/hooks/ruff-hook.py` reached the
    protected-write guard as a stage whose verb was `env`, and one wrapper word
    deleted a guard (agent-loopholes-77938d26). An option's value (`10` in
    `nice -n 10`) also starts a suffix; its verb matches nothing, so every
    caller ignores it.

    The original stage is kept as well, never replaced: `env` alone is a read
    command the ctx-ok guard must still judge, and an unrecognised wrapped verb
    must still fail closed. That guard already denies every wrapper verb, so
    the extra suffixes cannot turn one of its denials into an allow.

    The residual false positive — a wrapper-led stage whose operands literally
    read `git push` or `rm scripts/hooks/x` as data — blocks one command rather
    than admitting one, which is the direction a guard should err in.

    A variant that is itself a shell given `-c` adds the stages of its command
    string, so `bash -c '…'` and `env sudo sh -c '…'` are judged by what they
    run (agent-loopholes-015b8134); see `_shell_c_stages`.
    """
    variants = [({}, tokens)]
    if Path(tokens[0]).name in _WRAPPERS:
        # The scan runs over the `-S`-expanded form so a payload-carried call is
        # reachable, while the original stage is kept unexpanded: it is what the
        # ctx-ok guard and the unrecognised-verb path must still judge.
        expanded = _split_string_payload(tokens)
        variants += [
            (_assignments(expanded[:i]), expanded[i:])
            for i in range(1, len(expanded))
            if not expanded[i].startswith("-") and "=" not in expanded[i]
        ]
    return variants + [
        (env | inner_env, inner)
        for env, variant in variants
        for inner_env, inner in _shell_c_stages(variant, depth)
    ]


def _shell_verb_end(tokens: list[str]) -> int | None:
    """Index just past the shell's own name, or None when the stage is no shell.

    `busybox sh` names the shell one word late, so it ends at 2.
    """
    name = Path(tokens[0]).name
    if name == "busybox":
        return 2 if len(tokens) > 1 and Path(tokens[1]).name in _SHELLS else None
    return 1 if name in _SHELLS else None


def _shell_invocation(tokens: list[str]) -> tuple[str, str | None] | None:
    """How a shell stage gets its commands: ("c", string), ("stdin", None) or ("file", path).

    None when the stage's verb is not a shell. Bash reads `-c`'s command string
    from the first NON-OPTION argument, not from the token after `-c`, so
    `bash -c -x 'git push'` runs `git push`; the scan therefore records the flag
    (alone or in a cluster such as `-lc`) and takes the first operand. `fish`
    spells it `--command`. With no `-c` and no operand, or with `-s`, the shell
    reads its commands from stdin — the `… | bash` shape. An operand without
    `-c` is a script file, whose contents no text guard can see.
    """
    i = _shell_verb_end(tokens)
    if i is None:
        return None
    command_flag = stdin_flag = False
    while i < len(tokens):
        # `word`, not `token`: bandit reads `token == "--"` as a hardcoded
        # password comparison (B105).
        word = tokens[i]
        if word.startswith("--command="):
            return ("c", word.split("=", 1)[1])
        if word in _SHELL_VALUE_OPTS or word == "--":
            i += 1
            if word == "--":
                break
        elif len(word) > 1 and word[0] in "-+":
            short = word[0] == "-" and not word.startswith("--")
            command_flag |= word == "--command" or (short and "c" in word[1:])
            stdin_flag |= short and "s" in word[1:]
        else:
            break
        i += 1
    if command_flag:
        return ("c", tokens[i]) if i < len(tokens) else None
    if stdin_flag or i >= len(tokens) or tokens[i] == "-":
        return ("stdin", None)
    return ("file", tokens[i])


def _coarse_stages(payload: str) -> list[tuple[dict[str, str], list[str]]]:
    """Every word-initial suffix of every segment of `payload`, quoting ignored.

    The fallback past `_MAX_SHELL_DEPTH`, for the reason `_split_string_payload`
    gives for its own cap: a nest too deep to unwrap exactly is judged coarsely
    rather than waved through, and a coarse split only ever adds candidate
    stages. Quote characters become spaces, so whatever the nesting, `git` and
    `rm` still start a candidate.
    """
    flat = re.sub(r"[\"'\\`$()]", " ", payload)
    stages: list[tuple[dict[str, str], list[str]]] = []
    for segment in re.split(r"[|;&\n]+", flat):
        words = segment.split()
        stages += [({}, words[i:]) for i in range(len(words))]
    return stages


def _shell_c_stages(tokens: list[str], depth: int) -> list[tuple[dict[str, str], list[str]]]:
    """The stages a `sh -c '<string>'` stage runs, parsed as a command of their own.

    Empty unless `tokens` is a shell given a command string. The string is one
    token by the time it gets here, and before agent-loopholes-015b8134 nothing
    opened it: `bash -c 'git commit --no-verify -m x'` and
    `bash -c 'rm scripts/hooks/ruff-hook.py'` passed every guard. Parsing it with
    `shell_stages_with_env` gives the inner command the same treatment as a
    top-level one — quoting, wrappers, and a further `-c` — bounded by
    `_MAX_SHELL_DEPTH`.
    """
    invocation = _shell_invocation(tokens)
    if invocation is None or invocation[0] != "c" or not invocation[1]:
        return []
    if depth >= _MAX_SHELL_DEPTH:
        return _coarse_stages(invocation[1])
    return shell_stages_with_env(invocation[1], _depth=depth + 1)


def feeds_a_shell(command: str) -> bool:
    """True if any stage is a shell that reads its commands from stdin.

    `echo 'git push origin main' | bash` runs a command that is data on the
    outer command line, so no stage carries it (agent-loopholes-015b8134).
    Callers treat such a command the way they treat code in another language.
    """
    return any(
        (invocation := _shell_invocation(tokens)) is not None and invocation[0] == "stdin"
        for tokens in shell_stages(command)
    )


def shell_stages_with_env(command: str, _depth: int = 0) -> list[tuple[dict[str, str], list[str]]]:
    """(env assignments, tokens) per stage — the full result `shell_stages` trims.

    The `VAR=value` prefix is stripped so the command can be found, and used to
    be discarded with it. `core.hooksPath` can be assigned through the
    environment as readily as through `-c`, so
    `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath … git commit` reached real
    git with no token the guard inspected. Returning the prefix rather than
    dropping it is what lets the git guard judge that route.

    A separate function rather than a wider return type from `shell_stages`:
    every other caller wants tokens alone, and changing that signature would
    touch each of them for a question only one of them asks.

    `_depth` counts the `sh -c` payloads already opened to reach `command`; it
    is internal, and bounds the recursion through `_shell_c_stages`.
    """
    masked, spans = _mask_quoted(command)
    # Comments first, then continuations: `foo # bar \` is comment to end of line,
    # so the trailing backslash continues nothing and must not join the next line.
    joined = _CONTINUATION.sub(" ", _COMMENT.sub("", masked))
    stages: list[tuple[dict[str, str], list[str]]] = []
    for segment in _STAGE_SPLIT.split(joined):
        tokens = strip_reserved([_unmask(t, spans) for t in segment.split()])
        env: dict[str, str] = {}
        i = 0
        while i < len(tokens) and "=" in tokens[i] and not tokens[i].startswith("-"):
            name, _, value = tokens[i].partition("=")
            env[name] = value
            i += 1
        if i < len(tokens):
            # The wrapper's assignments are layered over the stage's, not merged
            # blindly: `A=1 env A=2 git …` is what real `env` does, and the
            # closer one is what reaches git.
            stages.extend(
                (env | extra, variant) for extra, variant in _wrapper_variants(tokens[i:], _depth)
            )
    return stages


def shell_stages(command: str) -> list[list[str]]:
    """Tokens for each pipeline/list stage, comments and `VAR=value` prefixes stripped.

    A guard that reads only the first stage misses `echo hi && git push origin
    main`, and one that ignores the environment prefix misses `FOO=1 git ...`.
    Empty stages are dropped, so every returned list has at least one token.

    Quoting is honoured (see _mask_quoted) and comments are removed here rather
    than by each caller, so `git_calls` and the ctx-ok guard agree on what a
    command says: a trailing `# push to main later` used to put `main` in the
    push guard's operand list.

    A command nested in `$(...)`, backticks or a subshell is its own stage, and a
    stage behind a wrapper yields the wrapped git call as another — see
    `_STAGE_SPLIT` and `_wrapper_variants`.
    """
    return [tokens for _env, tokens in shell_stages_with_env(command)]


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


# ── What a stage writes: one model for every write guard ─────────────────────
#
# The protected-write guard and the unguarded-cd guard each kept a verb list,
# and the two had drifted: the cd guard counted rsync and `find -delete`, the
# protected-write guard did not, and neither knew `unlink`, `tar -x`,
# `awk -i inplace` or `curl -o` (agent-loopholes-6bb5ff99). Both now ask
# `write_targets`. Git is left to each guard, because the two ask different
# questions of it: the cd guard treats every non-read subcommand as a write,
# the protected-write guard needs the paths a subcommand touches.
#
# Ceiling: a closed list cannot name every program that writes a file. A write
# made by an interpreter (`python -c`), by a script, or by a program listed
# nowhere here is not recognised.

# Verbs that write, or remove, every path operand they are given — or, for the
# `_DEST_LAST` ones, the last. Verbs that write only in some modes (a
# compressor, `sed -i`, `tar -x`) are in `_WRITE_HANDLERS` instead.
WRITE_VERBS = frozenset(
    {
        *("cp", "mv", "rm", "rmdir", "unlink", "install", "ln", "link", "truncate"),
        *("dd", "tee", "patch", "chmod", "chown", "chgrp", "chattr", "setfacl"),
        *("shred", "touch", "ed", "ex", "sponge", "mkdir", "mkfifo", "mknod"),
        *("rename", "rsync", "scp"),
    }
)
# Verbs whose leading operands are sources and whose last is the destination.
# Scanning every operand as a destination denied `cp scripts/hooks/_hooklib.py
# /tmp/x`, a read. `mv` is NOT here: it removes its sources, so `mv scripts
# /tmp/s` writes the tree it names (agent-loopholes-0426afd8). `ln` is: its
# leading operands are link targets, which it only reads.
_DEST_LAST = frozenset({"cp", "install", "ln", "link", "scp", "rsync"})
# Stream editors write only in place; a bare `sed`/`perl` reads and prints.
_IN_PLACE_EDITORS = frozenset({"sed", "perl", "ruby"})
_IN_PLACE_RE = re.compile(r"^-[a-zA-Z]*i|^--in-place")
# gawk's in-place extension, loaded as `-i inplace`, `--include=inplace` or
# by its file name.
_AWK_INPLACE_LIB = re.compile(r"(?:\S*/)?inplace(?:\.awk)?")
# `find` writes through these actions; `-exec`'s command runs once per match.
_FIND_EXEC = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
_FIND_OUTPUTS = frozenset({"-fprint", "-fprint0", "-fprintf", "-fls"})
# Commands `find -exec` runs that only read. Any other command is taken to
# write: which file it writes is `{}`, and `{}` is every match.
_READERS = frozenset(
    {
        *("cat", "grep", "egrep", "fgrep", "rg", "ls", "stat", "file", "head", "tail"),
        *("wc", "md5sum", "sha1sum", "sha256sum", "sha512sum", "echo", "printf"),
        *("test", "[", "basename", "dirname", "readlink", "realpath", "du", "diff"),
        *("cmp", "less", "more", "jq", "true", "false"),
    }
)


def write_targets(tokens: list[str]) -> tuple[list[str], list[str]] | None:
    """What a non-git stage writes: (paths, trees), or None when it writes nothing.

    `paths` are operands written as named. `trees` are directories the command
    writes *below*, at paths its input chooses rather than its command line: an
    archive's members, `find`'s matches. A caller judges a tree as reaching
    everything under it, the checkout root included.
    """
    verb = Path(tokens[0]).name
    args = tokens[1:]
    handler = _WRITE_HANDLERS.get(verb)
    if handler is not None:
        return handler(args)
    if verb in WRITE_VERBS:
        return _plain_operands(verb, args), []
    return None


def _plain_operands(verb: str, args: list[str]) -> list[str]:
    """The operands a plain writer writes: all of them, or the destination.

    `-t DIR` / `--target-directory` puts the destination first, and rsync's
    `--remove-source-files` deletes the sources too; either falls back to every
    operand, since over-blocking an unusual spelling costs one command and the
    other direction is a write nothing sees.
    """
    if verb not in _DEST_LAST:
        return args
    if any(a.startswith(("-t", "--target-directory", "--remove-source")) for a in args):
        return args
    operands = [a for a in args if not a.startswith("-")]
    return operands[-1:] if len(operands) > 1 else args


def _in_place_targets(args: list[str]) -> tuple[list[str], list[str]] | None:
    """`sed -i`, `perl -pi`, `ruby -i`: every operand, when editing in place."""
    return (args, []) if any(_IN_PLACE_RE.match(a) for a in args) else None


def _with_next(words: list[str]) -> Iterator[tuple[str, str]]:
    """Each word with the one after it, the last with "" — empty for no words.

    Not `zip(words, [*words[1:], ""], strict=True)`: for an empty list that
    pairs nothing with one "", raises, and a bare `sort` in a pipeline sent the
    guard to its fail-closed arm.
    """
    return itertools.zip_longest(words, words[1:], fillvalue="")


def _awk_targets(args: list[str]) -> tuple[list[str], list[str]] | None:
    """`awk -i inplace` / `gawk --include=inplace`: every operand is rewritten."""
    for arg, following in _with_next(args):
        if arg in ("-i", "--include"):
            library = following
        elif arg.startswith(("-i", "--include=")):
            library = arg.removeprefix("--include=").removeprefix("-i")
        else:
            continue
        if _AWK_INPLACE_LIB.fullmatch(library):
            return args, []
    return None


def _find_targets(args: list[str]) -> tuple[list[str], list[str]] | None:
    """`find`: its `-fprint`/`-fls` files, and its start points when it deletes.

    `-delete`, or an `-exec`/`-ok` running anything but a reader, writes every
    match, so the start points are trees. No start point means `.`.
    """
    starts: list[str] = []
    for arg in args:
        if arg.startswith(("-", "(", "!")):
            break
        starts.append(arg)
    outputs = [b for a, b in itertools.pairwise(args) if a in _FIND_OUTPUTS]
    runs = [args[i + 1 : i + 2] for i, a in enumerate(args) if a in _FIND_EXEC]
    writes = "-delete" in args or any(r and Path(r[0]).name not in _READERS for r in runs)
    if writes:
        return outputs, starts or ["."]
    return (outputs, []) if outputs else None


def option_values(args: list[str], short: str, long: str) -> list[str]:
    """Every value given to an option: `-X v`, `-Xv`, `--long v`, `--long=v`, or
    the letter inside a short cluster (`-sSLo v`, `-cvf v`), whose value is the
    rest of the cluster or the next word."""
    out: list[str] = []
    letter = short[1:]
    for arg, following in _with_next(args):
        if arg in (short, long):
            out.append(following)
        elif arg.startswith(long + "="):
            out.append(arg.split("=", 1)[1])
        elif arg.startswith("-") and not arg.startswith("--") and letter in arg[1:]:
            out.append(arg[arg.index(letter, 1) + 1 :] or following)
    return out


def _short_flags(args: list[str]) -> str:
    """Every letter of every short-option cluster, plus tar's dashless first word."""
    letters = [a[1:] for a in args if a.startswith("-") and not a.startswith("--")]
    if args and not args[0].startswith("-"):
        letters.append(args[0])
    return "".join(letters)


def _tar_targets(args: list[str]) -> tuple[list[str], list[str]] | None:
    """`tar`: extraction writes below its `-C` directory; creation writes `-f`.

    Extraction is unscoped the way `git apply` is: the archive's member names,
    not the command line, decide what is written, so the destination is a tree.
    `-P`/`--absolute-names` lets members name any path, which is the root `/`.
    """
    flags = _short_flags(args)
    if "x" in flags or "--extract" in args or "--get" in args:
        if "P" in flags or "--absolute-names" in args:
            return [], ["/"]
        return [], option_values(args, "-C", "--directory") or ["."]
    if any(m in flags for m in "cruA") or "--create" in args or "--append" in args:
        return _tar_archive(args), []
    return None


def _tar_archive(args: list[str]) -> list[str]:
    """The archive a creating `tar` writes: `-f X`, `--file=X`, `-cvf X`, or the
    word after a dashless first word that names `f` (`tar cvf X`)."""
    found = option_values(args, "-f", "--file")
    if args and not args[0].startswith("-") and "f" in args[0]:
        found += args[1:2]
    return found


def _unzip_targets(args: list[str]) -> tuple[list[str], list[str]] | None:
    """`unzip` extracts below `-d DIR` (default `.`) unless it only lists or pipes."""
    listing = [a for a in args if a.startswith("-") and not a.startswith("-d")]
    if any(set(a[1:]) & set("ltvpcZz") for a in listing):
        return None
    return [], option_values(args, "-d", "--dest") or ["."]


def _cpio_targets(args: list[str]) -> tuple[list[str], list[str]] | None:
    """`cpio -i` extracts below `-D DIR`; `cpio -p DIR` copies into DIR."""
    flags = _short_flags(args)
    if "i" in flags or "--extract" in args:
        return [], option_values(args, "-D", "--directory") or ["."]
    if "p" in flags or "--pass-through" in args:
        return [], [a for a in args if not a.startswith("-")][-1:] or ["."]
    return None


# A URL operand. `:/` rather than `://`: a guard that folds repeated slashes
# before asking (the protected-write guard does) turns one into the other.
_URL = re.compile(r"[A-Za-z][\w+.-]*:/")


def _url_names(args: list[str]) -> list[str]:
    """The file name a download of each URL operand is saved under."""
    return [Path(a.split("?", 1)[0]).name for a in args if _URL.match(a)]


def _curl_targets(args: list[str]) -> tuple[list[str], list[str]] | None:
    """`curl -o FILE`, and `-O`, which saves under the URL's own file name."""
    outs = option_values(args, "-o", "--output")
    if "-O" in args or "--remote-name" in args or "--remote-name-all" in args:
        outs += _url_names(args)
    return (outs, []) if outs else None


def _wget_targets(args: list[str]) -> tuple[list[str], list[str]] | None:
    """`wget` always saves: `-O FILE`, else the URL's name under `-P DIR`."""
    outs = option_values(args, "-O", "--output-document")
    if outs:
        return outs, []
    prefix = (option_values(args, "-P", "--directory-prefix") or [""])[-1]
    return [f"{prefix}/{n}" if prefix else n for n in _url_names(args)] or ["."], []


_COMPRESSORS = (
    *("gzip", "gunzip", "bzip2", "bunzip2", "xz", "unxz", "lzma", "unlzma"),
    *("zstd", "unzstd", "compress", "uncompress"),
)
# Compressor options that print, test or list rather than replace a file.
_COMPRESSOR_READS = frozenset({"--stdout", "--to-stdout", "--test", "--list"})


def _compressor_targets(args: list[str]) -> tuple[list[str], list[str]] | None:
    """A compressor replaces each operand with its (de)compressed file, unless it
    only writes to stdout (`-c`), tests (`-t`) or lists (`-l`)."""
    short = "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--"))
    if set(short) & set("ctl") or _COMPRESSOR_READS.intersection(args):
        return None
    return args, []


def _sort_targets(args: list[str]) -> tuple[list[str], list[str]] | None:
    """`sort -o FILE` writes FILE; a bare `sort` prints."""
    outs = option_values(args, "-o", "--output")
    return (outs, []) if outs else None


_WRITE_HANDLERS = {
    **dict.fromkeys(_IN_PLACE_EDITORS, _in_place_targets),
    **dict.fromkeys(("awk", "gawk"), _awk_targets),
    **dict.fromkeys(("tar", "bsdtar"), _tar_targets),
    **dict.fromkeys(_COMPRESSORS, _compressor_targets),
    "find": _find_targets,
    "unzip": _unzip_targets,
    "cpio": _cpio_targets,
    "curl": _curl_targets,
    "wget": _wget_targets,
    "sort": _sort_targets,
}
