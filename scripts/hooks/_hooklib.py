"""Shared preamble for the PreToolUse / PostToolUse / Stop hooks in scripts/hooks/.

Library module — imported by the hook scripts, never run directly, so no
shebang and no `# /// script` block. Pure stdlib. Mirrors the sibling-import
precedent in scripts/validate-skill.py (`sys.path.insert(0, __file__ dir)`).
"""

import json
import os
import re
import shlex
import sys
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
_STAGE_SPLIT = re.compile(r"\|\||&&|\$\(|[|;\n`()]|(?<![<>])&(?!>)")

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
    """
    tool_input = _tool_input(data)
    code = tool_input.get("code")
    if tool_input.get("language") in (None, "shell") or not isinstance(code, str):
        return ""
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


def _wrapper_variants(tokens: list[str]) -> list[tuple[dict[str, str], list[str]]]:
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
    """
    if Path(tokens[0]).name not in _WRAPPERS:
        return [({}, tokens)]
    # The scan runs over the `-S`-expanded form so a payload-carried call is
    # reachable, while the original stage is kept unexpanded: it is what the
    # ctx-ok guard and the unrecognised-verb path must still judge.
    expanded = _split_string_payload(tokens)
    return [({}, tokens)] + [
        (_assignments(expanded[:i]), expanded[i:])
        for i in range(1, len(expanded))
        if not expanded[i].startswith("-") and "=" not in expanded[i]
    ]


def shell_stages_with_env(command: str) -> list[tuple[dict[str, str], list[str]]]:
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
    """
    masked, spans = _mask_quoted(command)
    # Comments first, then continuations: `foo # bar \` is comment to end of line,
    # so the trailing backslash continues nothing and must not join the next line.
    joined = _CONTINUATION.sub(" ", _COMMENT.sub("", masked))
    stages: list[tuple[dict[str, str], list[str]]] = []
    for segment in _STAGE_SPLIT.split(joined):
        tokens = [_unmask(t, spans) for t in segment.split()]
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
                (env | extra, variant) for extra, variant in _wrapper_variants(tokens[i:])
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
