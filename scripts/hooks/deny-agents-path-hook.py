#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PreToolUse hook — block Bash commands that reach the protected trees.

The `permissions.deny` list in .claude/settings.json names `Edit` and `Write`
rules only, and binds the file tools, never Bash — `head`, `sed -i`, or a
redirection walks straight past it. This hook covers the shell surface, in two
different shapes:

- `.claude/agents/**`: ANY shell reference is blocked (see
  `_references_agents`). This is broader than the deny list, which no longer
  names `Read` for that tree — 561e285 removed it so agent definitions can be
  audited in-session through the Read tool (docs-8bf4642c corrected this
  docstring, which still claimed a Read deny).
- `scripts/hooks/**`, `.claude/settings.json`, `.claude/settings.local.json` and
  the graphify pin (`PROTECTED_WRITE`): only a WRITE is blocked (see
  `_writes_protected`). Denying `cat scripts/hooks/ruff-hook.py` would
  contradict the permission model and break ordinary work.
"""

import functools
import re
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import (
    _VALUE_OPTS,
    event_command,
    foreign_code,
    load_event_strict,
    repo_root,
    shell_stages,
    skip_git_global_opts,
)

_REPO_ROOT = repo_root()

# A hook cannot fully parse shell, so two mechanisms cover the surface together:
#
# 1. Textual — per shell word (see `_textual_reference`), _DENIED_RE matches
#    the literal `.claude/agents`, and the _CLAUDE_RE + _AGENTS_INDIRECT_RE
#    pair catches any `.claude/a…` spelling (`.claude/a*`, `.claude/a[g]ents`)
#    after _canonicalize folds escaped, quoted, and repeated/`.`-slash forms.
#    Variable-built paths (`$D/agents`, `A=agents; … $A …`) are expanded from
#    the command's own assignments first.
# 2. Glob expansion — _glob_reaches_agents actually expands glob tokens against
#    the repo (from the root and from any `cd` target), so a metacharacter that
#    obscures the `.claude` root itself (`.?laude/agents`, `.cl*de/agents`) or a
#    `cd .claude && cat a*/…` that shifts the glob base — neither leaving a
#    literal substring for the textual pass — is still caught by the shell's own
#    semantics. _canonicalize therefore must NOT delete glob metacharacters:
#    stripping the `?` in `.?laude` collapses it to `.laude` and hides the match.
#
# Broad on purpose — a false positive costs one blocked Bash call; a false
# negative exposes the CODEOWNERS-gated agent definitions to a shell the
# Edit/Write deny list never reaches.
_DENIED_RE = re.compile(r"\.claude/agents\b")
_CLAUDE_RE = re.compile(r"\.claude\b")
_AGENTS_INDIRECT_RE = re.compile(r"[=/$]agents?\b|\.claude/a")
# Claude Code names isolation worktrees `.claude/worktrees/agent-<id>`, and
# `/agent-` meets `[=/$]agents?\b` (the hyphen is a word boundary), so every
# command naming a worktree was denied as a reference to the agents tree
# (agent-loopholes-c7170a25). The textual pass drops that one segment first.
# Deliberately exact: a name may not start with `.`, so `.claude/worktrees/..`
# is never dropped, and a name followed by `/..` is kept so an escape back out
# of the worktree still reads as `.claude` plus `agents`. The possessive
# quantifier stops the lookahead from being satisfied by a shorter name.
_WORKTREE_RE = re.compile(r"\.claude/worktrees/[^./\s;&|<>()][^/\s;&|<>()]*+(?!/\.\.)")
_GLOB_META_RE = re.compile(r"[*?\[]")
# A directory change: `cd` or `pushd`, past `-L`/`-P`/`-e`/`-@`, to its target.
_CD_RE = re.compile(r"(?:^|[\s;&|(])(?:cd|pushd)\s+(?:-[LPe@]+\s+)*([^\s;&|()<>]+)")
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
#    the surface. See `.claude/rules/hook-inventory.md`.
_AGENT_FILES = tuple(sorted(p.name for p in (_REPO_ROOT / DENIED).glob("*.md")))


# ── protected-write paths ─────────────────────────────────────────────────────
#
# permissions.deny also names Edit and Write on `scripts/hooks/**` and
# `.claude/settings.json` — the enforcement surface itself — and Bash walks past
# those exactly as it does for the agents tree. Reading them is allowed, so this
# half matches a MUTATION only.
#
# Ceiling, stated rather than implied: this matches redirection targets, a fixed
# set of mutating verbs, in-place stream editors, and the `git` subcommands that
# write the working tree. A write performed *inside* an interpreter
# (`python -c "open(p, 'w')"`), by a script that takes the path as data, or
# through a symlink is not matched, and neither is an operation on the whole
# checkout spelled as its root (`rm -rf .`) — an ancestor of a protected root
# counts, the root itself does not (see `_touches_protected`). As with the
# agents half, CODEOWNERS plus branch protection remains the binding control;
# this raises the cost of the bypass, it does not close it.
#
# `.claude/settings.local.json` is merged over the project settings and can set
# `disableAllHooks`, so one redirect there turned off every hook
# (agent-loopholes-bbe241dd). The graphify pin decides which installed binary the
# Bash/Read/Glob guards trust, so rewriting it re-trusts any binary
# (agent-loopholes-8c3cdf74).
PROTECTED_WRITE = (
    "scripts/hooks",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/skills/graphify/.graphify_version",
)

_REDIR_RE = re.compile(r">{1,2}\s*([^\s;&|<>()]+)")
_WRITE_VERBS = frozenset(
    {
        "cp",
        "mv",
        "rm",
        "rmdir",
        "install",
        "truncate",
        "dd",
        "tee",
        "patch",
        "chmod",
        "chown",
        "chgrp",
        "ln",
        "shred",
        "touch",
        "ed",
        "ex",
        "sponge",
    }
)
# Only in-place invocations write; a bare `sed`/`perl` reads and prints.
_STREAM_EDITORS = frozenset({"sed", "perl", "ruby"})
_INPLACE_RE = re.compile(r"^-[a-zA-Z]*i|^--in-place")
_GIT_WRITE_SUBCMDS = frozenset(
    {"checkout", "restore", "apply", "mv", "rm", "clean", "stash", "reset"}
)

# Git subcommands that rewrite tracked files across the WHOLE worktree while
# naming no path — so they reach scripts/hooks/ carrying no protected token for
# `_token_writes_protected` to match. `git reset --hard` is the plain case.
#
# Deliberately narrow, because over-blocking git makes the guard something to
# route around:
#   * `reset` counts only with a mode flag that touches the worktree; plain
#     `reset` and `--soft` move refs and leave files alone.
#   * `checkout`/`restore` count only with a whole-tree pathspec. Switching
#     branches also rewrites files, but that is ordinary work, and
#     ask-destructive-restore-hook.py already prompts when it would discard
#     uncommitted content.
#   * `apply` counts always: the patch decides what it touches, so it is
#     unscoped by construction.
#   * `clean` is absent on purpose — it removes untracked files only, and every
#     file under scripts/hooks/ is tracked.
#   * `stash` is absent on purpose — it is recoverable by `stash pop`, unlike
#     the others here.
_RESET_WORKTREE_MODES = frozenset({"--hard", "--merge", "--keep"})
_WHOLE_TREE = frozenset({".", "./", ":/", ":/.", "*"})


def _git_rewrites_worktree(tokens: list[str]) -> bool:
    """True if this git stage rewrites tracked files without naming a path."""
    i = skip_git_global_opts(tokens, 1)
    if i >= len(tokens):
        return False
    sub, args = tokens[i], tokens[i + 1 :]
    if sub == "apply":
        return True
    if sub == "reset":
        return any(a in _RESET_WORKTREE_MODES for a in args)
    if sub in ("checkout", "restore"):
        return any(a in _WHOLE_TREE for a in args)
    return False


def _under_protected(rel: str) -> bool:
    """True if a repo-relative POSIX path sits at or under a protected-write root.

    Its callers hand it a normalised path: `_protected_path` a resolved one,
    `_touches_protected` one with `./` and trailing slashes already stripped.
    """
    return any(rel == root or rel.startswith(root + "/") for root in PROTECTED_WRITE)


def _touches_protected(rel: str) -> bool:
    """True if writing `rel` writes a protected root: at, under, or ABOVE one.

    Moving, deleting or overwriting a directory acts on everything in it, so
    `mv scripts /tmp/s`, `rm -rf .claude` and `git rm -r scripts` each remove the
    enforcement surface while naming only its ancestor, which `_under_protected`
    never matched. One call could move the tree out, edit it at an absolute path
    and move it back (agent-loopholes-0426afd8). The repository root itself is
    excluded: every protected root is under it, so counting it would deny
    `cp /tmp/x .`. Ceiling: an operation on the whole checkout, spelled as the
    root, is not matched.
    """
    rel = rel.strip().rstrip("/")
    while rel.startswith("./"):
        rel = rel[2:]
    if _under_protected(rel):
        return True
    return rel not in ("", ".") and any(root.startswith(rel + "/") for root in PROTECTED_WRITE)


def _protected_path(path: Path, *, ancestors: bool = False) -> bool:
    """True if a filesystem path resolves inside a protected-write root.

    With `ancestors`, a path above a protected root counts too — the rule for a
    written operand (see `_touches_protected`); a `cd` base keeps the narrower
    test, since standing in `scripts/` writes nothing by itself.

    A path that cannot be resolved at all (a symlink loop on 3.11/3.12) counts
    as protected rather than outside: the error used to escape and exit 1, which
    Claude Code treats as an allow (agent-loopholes-02f83e02).
    """
    try:
        rel = path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
    except RuntimeError:
        return True
    except (OSError, ValueError):
        return False
    return _touches_protected(rel) if ancestors else _under_protected(rel)


def _token_writes_protected(token: str, command: str, bases: list[Path] | None = None) -> bool:
    """True if `token`, read as a path, lands under a protected-write root.

    `--file=path` and `dd of=path` carry the path after an `=`, so the tail is
    taken. Glob tokens are expanded through the same machinery the agents half
    uses, so `scripts/ho*ks/*.py` resolves rather than being read literally.

    A relative token is resolved from EVERY base the command can be standing in
    — the repo root, each `cd`/`pushd` target, a context-mode `cwd` (rendered as
    a leading `cd`), and a git stage's `-C`/`--work-tree` — not from the repo
    root alone. Only globs used to get the bases, so `cd .claude && echo '{}' >
    settings.local.json`, `cd scripts && sed -i … hooks/_hooklib.py` and
    `git -C scripts checkout HEAD~3 -- hooks` each wrote the enforcement surface
    past the guard (agent-loopholes-6442185e). `bases` defaults to the
    command's `cd` bases; a git stage passes its own.

    A `$` in the token is expanded first, from the variables the command binds
    itself (see `_expansions`), and each candidate is judged on its own
    (agent-loopholes-d61a805c): `F=scripts/hooks/x.py; echo x > $F` wrote a hook
    while the guard compared the literal `$F`.
    """
    token = token.split("=", 1)[-1]
    if not token:
        return False
    if bases is None:
        bases = _cd_bases(command)
    if "$" not in token and "`" not in token:
        return _path_writes_protected(token, bases)
    candidates = _expansions(token, _bindings(command))
    if candidates is None:
        return True  # too many or self-referential: cannot be judged, so deny
    return any(_candidate_writes_protected(c, bases) for c in candidates)


def _candidate_writes_protected(candidate: str, bases: list[Path]) -> bool:
    """Judge one expanded write target, deciding what an unresolved part may be.

    The rule for what expansion could not resolve (agent-loopholes-d61a805c):

    - A command substitution — `$(…)`, a backtick, or a variable bound by
      `read`/`for … in $(…)` — is a value the command computes itself, and can
      compute any path. It is denied outright.
    - A variable the command never binds (`$TMPDIR`, `$HOME`, `$$`) comes from
      the environment the call inherits, which the call's own text cannot set.
      Denying every such target would make `echo x > "$TMPDIR/y"` impossible,
      so it is bounded instead: denied only when the literal text around it
      could still land on the surface — the part before the variable is at,
      under or above a protected root (`scripts/$X`), or the part after it
      names a component of one (`$X/hooks/a.py`, `$HOME/.claude/settings.json`).
    - A candidate with nothing unresolved is resolved like a literal token.

    Ceiling: an inherited variable that already points into this repository
    (exported by an earlier call, where the shell persists one) is judged by
    the text around it alone.
    """
    # A `$` left once every parameter expansion is removed opened a `$(…)` (the
    # stage split cut it at the paren); `$$` and `$1` are parameters, not that.
    if "`" in candidate or "$" in _ANY_VAR_RE.sub("", candidate):
        return True
    unresolved = list(_ANY_VAR_RE.finditer(candidate))
    if not unresolved:
        return _path_writes_protected(candidate, bases)
    head = candidate[: unresolved[0].start()].rstrip("/")
    tail = candidate[unresolved[-1].end() :]
    if head and _path_writes_protected(head, bases):
        return True
    return bool(_PROTECTED_COMPONENTS.intersection(PurePosixPath(tail).parts))


def _path_writes_protected(token: str, bases: list[Path]) -> bool:
    """True if a literal path token, resolved from each base, lands on the surface."""
    pure = PurePosixPath(token)
    if pure.is_absolute():
        bases = [_REPO_ROOT]  # an absolute token names one place, whatever the cwd
        # Resolved on both sides, matching _protected_path. Comparing against an
        # unresolved _REPO_ROOT made a symlinked checkout a bypass: an absolute
        # token naming the real underlying path raised ValueError here and read
        # as "not protected", and the glob arm below cannot recover it because a
        # plain absolute path carries no metacharacter.
        try:
            token = str(Path(token).resolve().relative_to(_REPO_ROOT.resolve()))
        except (OSError, ValueError):
            return False  # absolute but outside the repo — nothing to protect
    if _touches_protected(token):
        return True
    if not _GLOB_META_RE.search(token):
        return any(_protected_path(base / token, ancestors=True) for base in bases)
    for base in bases:
        for hit in _shell_glob(base, token):
            if _protected_path(hit, ancestors=True):
                return True
    return False


# Every path component of a protected root, for judging the literal tail after
# an inherited variable (see `_candidate_writes_protected`).
_PROTECTED_COMPONENTS = frozenset(part for root in PROTECTED_WRITE for part in root.split("/"))
# Any parameter expansion left after binding: `$NAME`, `${…}`, or a special one.
_ANY_VAR_RE = re.compile(r"\$(?:\{[^}]*\}|[A-Za-z_]\w*|[0-9$!#?@*-])")
# Loop variables take each listed word; `read`-family names take stdin.
_FOR_RE = re.compile(r"(?:^|[\s;&|(])(?:for|select)\s+([A-Za-z_]\w*)\s+in\s+([^;\n]*)")
_READ_RE = re.compile(r"(?:^|[\s;&|(])(?:read|mapfile|readarray)\b([^;&|\n]*)")
# Stand-in value for a variable whose value the command computes at run time.
_COMPUTED = "$(computed)"
# `$(mktemp)` right after an assignment's `=` (the `$` is the value `_ASSIGN_RE`
# captured, so the match starts at the paren), and what it is bound to. Only
# `-d`/`-q`/`-u` are accepted: a template or `-p DIR` chooses where the file
# lands, and `mktemp -p scripts/hooks` would land on the surface.
_MKTEMP_RE = re.compile(r"\(\s*mktemp(?:\s+-[dqu]+)*\s*\)")
# Any absolute path outside a checkout serves; this one names what it stands for.
_MKTEMP_PATH = "/mktemp-result/XXXXXXXX"
# Bounds on `_expansions`: candidates per token, and substitution rounds.
_MAX_EXPANSIONS = 64
_MAX_EXPANSION_ROUNDS = 16


@functools.cache
def _bindings(command: str) -> dict[str, tuple[str, ...]]:
    """Every variable `command` binds itself, name to the values it may take.

    `NAME=value` (bare, after `export`/`local`/`declare`) binds one value; a
    later assignment adds another rather than replacing it, since which one a
    given write sees depends on order the regex does not model — over-binding
    only adds candidates. `for NAME in a b` binds each listed word. A `read`
    name, or a value holding `$(`/a backtick (`t=$(mktemp)` reaches here as
    `t=$`), is bound to `_COMPUTED`: the command computes it, so it can be
    anything. The one exception is `NAME=$(mktemp)` or `$(mktemp -d)`, bound
    to an absolute path outside the repo: mktemp creates a fresh path in the
    temp directory, and denying the cleanup `rm -rf "$tmp"` would block the
    most common temp-file idiom.
    Cached: every written operand of one command asks.
    """
    out: dict[str, list[str]] = {}
    for match in _ASSIGN_RE.finditer(command):
        name, value = match.group(1), match.group(2)
        if value.endswith("$") or "`" in value:
            after = command[match.end(2) :]
            value = _MKTEMP_PATH if _MKTEMP_RE.match(after) else _COMPUTED
        out.setdefault(name, []).append(value)
    for name, words in _FOR_RE.findall(command):
        words = words.split(" do ")[0].split()
        out.setdefault(name, []).extend(words or [_COMPUTED])
    for names in _READ_RE.findall(command):
        for name in (w for w in names.split() if not w.startswith("-")):
            out.setdefault(name, []).append(_COMPUTED)
    return {name: tuple(dict.fromkeys(values)) for name, values in out.items()}


def _expansions(token: str, bindings: dict[str, tuple[str, ...]]) -> list[str] | None:
    """Every spelling `token` can take once the command's own variables are expanded.

    A variable the command does not bind is left in place for
    `_candidate_writes_protected` to judge. None when the candidates exceed
    `_MAX_EXPANSIONS` or the substitution does not settle within
    `_MAX_EXPANSION_ROUNDS` (`A=x$A`): a target that cannot be enumerated is
    one the guard cannot clear.
    """
    candidates = [token]
    for _ in range(_MAX_EXPANSION_ROUNDS):
        expanded: list[str] = []
        changed = False
        for candidate in candidates:
            match = next((m for m in _VAR_RE.finditer(candidate) if m.group(1) in bindings), None)
            if match is None:
                expanded.append(candidate)
                continue
            changed = True
            head, tail = candidate[: match.start()], candidate[match.end() :]
            expanded += [head + value + tail for value in bindings[match.group(1)]]
        candidates = list(dict.fromkeys(expanded))
        if len(candidates) > _MAX_EXPANSIONS:
            return None
        if not changed:
            return candidates
    return None


def _stage_is_mutating(tokens: list[str]) -> bool:
    """True if this pipeline stage's verb writes files."""
    verb = PurePosixPath(tokens[0]).name
    if verb in _WRITE_VERBS:
        return True
    if verb in _STREAM_EDITORS:
        return any(_INPLACE_RE.match(a) for a in tokens[1:])
    if verb == "git":
        i = skip_git_global_opts(tokens, 1)
        return i < len(tokens) and tokens[i] in _GIT_WRITE_SUBCMDS
    return False


def _redirects_into_protected(c: str) -> bool:
    """True if any redirection target lands under a protected-write root.

    Checked separately from the verb scan because `> scripts/hooks/x.py` names
    no command at all — the shell does the writing.
    """
    return any(_token_writes_protected(m.group(1), c) for m in _REDIR_RE.finditer(c))


# Verbs whose LEADING operands are sources and whose last one is the
# destination. Scanning every operand as a destination denied `cp
# scripts/hooks/_hooklib.py /tmp/x` — a read, refused by a guard whose own
# message says "Reading these paths is allowed". `cat` of the same file was
# always allowed, so the asymmetry was in the verb, not in the policy.
#
# `mv` is NOT here: it removes its sources, so `mv scripts/hooks/x.py /tmp` and
# `mv scripts /tmp/s` write the protected tree they name (agent-loopholes-0426afd8).
# `ln` is: its leading operands are link targets, which it only reads.
_DEST_LAST = frozenset({"cp", "install", "ln"})


def _written_operands(tokens: list[str]) -> list[str]:
    """The operands this stage actually WRITES.

    For most verbs that is all of them — `rm a b`, `chmod +x a b`, `mv a b`
    each write every path they name. For the copy-shaped verbs the leading
    operands are sources, so only the last is written. For git, the operands
    are what follows the subcommand: a `-C scripts` value is a directory the
    stage stands in (see `_git_bases`), and reading it as a written operand
    would make every `git -C scripts checkout -- x` a write to the ancestor of
    `scripts/hooks`.

    `-t DIR` / `--target-directory=DIR` inverts the position, putting the
    destination first. Rather than model that, seeing one falls back to scanning
    every operand: over-blocking one unusual spelling costs a blocked command,
    and getting it wrong the other way is a write to the enforcement surface
    that nothing sees.
    """
    verb = PurePosixPath(tokens[0]).name
    if verb == "git":
        return tokens[skip_git_global_opts(tokens, 1) + 1 :]
    if verb not in _DEST_LAST:
        return tokens[1:]
    if any(a.startswith(("-t", "--target-directory")) for a in tokens[1:]):
        return tokens[1:]
    operands = [a for a in tokens[1:] if not a.startswith("-")]
    return operands[-1:] if len(operands) > 1 else tokens[1:]


def _stage_writes_protected(tokens: list[str], c: str) -> bool:
    """True if this one mutating stage writes a protected path.

    The git arm runs first: an unscoped worktree rewrite reaches the protected
    paths without ever naming them, so the operand scan below cannot see it.
    """
    bases = _cd_bases(c)
    if PurePosixPath(tokens[0]).name == "git":
        if _git_rewrites_worktree(tokens):
            return True
        bases = _git_bases(tokens, bases)
    return any(_token_writes_protected(a, c, bases) for a in _written_operands(tokens))


def _git_bases(tokens: list[str], bases: list[Path]) -> list[Path]:
    """`bases` plus the directories a git stage's `-C` and `--work-tree` move it to.

    `git -C scripts checkout HEAD~3 -- hooks` resolves `hooks` from `scripts`,
    so the operand names `scripts/hooks` without spelling it
    (agent-loopholes-6442185e). `-C` is cumulative in git — `-C a -C b` is
    `a/b` — so each one moves the current set of bases on; `--work-tree` is
    added as a base of its own. Over-approximates, which only adds places a path
    is checked from, and grows linearly with the options given.
    """
    out, current = list(bases), list(bases)
    i = 1
    while i < len(tokens) and tokens[i].startswith("-"):
        opt, _, inline = tokens[i].partition("=")
        value = inline or (tokens[i + 1] if i + 1 < len(tokens) else "")
        if opt == "-C" and value:
            current = [base / value for base in current]
            out += current
        elif opt == "--work-tree" and value:
            out += [base / value for base in bases]
        i += 1 if inline or opt not in _VALUE_OPTS else 2
    return out


def _names_protected(code: str) -> bool:
    """True if non-shell code names a protected-write path at all.

    A context-mode call in Python or JavaScript cannot be tokenized into stages,
    so a read cannot be told from a write and naming the path is the only signal
    left (agent-loopholes-41c1b2f3). Over-blocks a read spelled that way, which
    a shell `cat` still performs. `foreign_code` also hands over shell text
    that pipes into a shell (`… | bash`), whose inner command is equally
    untokenizable (agent-loopholes-015b8134).
    """
    c = _canonicalize(code)
    return any(root in c for root in PROTECTED_WRITE)


def _writes_protected(command: str) -> bool:
    """True if the command writes to scripts/hooks/ or .claude/settings.json."""
    c = _canonicalize(command)
    if _redirects_into_protected(c):
        return True
    # Staged from the raw text as well, then canonicalized per token:
    # `_canonicalize` strips quotes, which turns `bash -c 'rm scripts/hooks/x'`
    # into `bash -c rm scripts/hooks/x` — a `-c` string of `rm` alone, with the
    # path demoted to a positional argument — so the unwrapped inner stage only
    # exists in the raw parse (agent-loopholes-015b8134).
    raw = [[_canonicalize(t) for t in s] for s in shell_stages(command)]
    stages = [t for t in shell_stages(c) + raw if t and _stage_is_mutating(t)]
    if not stages:
        return False
    if any(_stage_writes_protected(t, c) for t in stages):
        return True
    # `cd scripts/hooks && sed -i s/a/b/ ruff-hook.py` — the operand carries no
    # directory, so the protected root appears only in the `cd` target.
    return any(_protected_path(base) for base in _cd_bases(c))


def _canonicalize(command: str) -> str:
    """Fold the spellings a shell resolves identically into one comparable form.

    Escaped separators, quotes, backslashes, repeated slashes and `.`
    segments all reach the same path, so without this the textual pass misses
    every obfuscated spelling of the same target.

    Glob metacharacters are deliberately left intact: stripping the `?` in
    `.?laude` collapses it to `.laude` and hides a match the glob-expansion
    pass would otherwise catch.
    """
    command = command.replace("\\/", "/")  # escaped separators: `.claude\/agents`
    command = re.sub(r"[\"'\\]", "", command)  # quotes/backslashes: `agent"s"`, `\agents`
    command = re.sub(r"/{2,}", "/", command)  # repeated slashes: `.claude//agents`
    command = re.sub(r"/(?:\./)+", "/", command)  # `.` segments: `.claude/./agents`
    return command


def _shell_glob(base: Path, pattern: str) -> list[Path]:
    """Expand `pattern` from `base`, falling back to shell semantics for `**`.

    CPython <3.13 raises ValueError when `**` sits adjacent to other characters
    in a path component; 3.13+ accepts it. Swallowing that error treated the
    token as harmless, so on 3.11/3.12 `cat .cl**de/agents/*.md` — which the
    shell DOES expand into the protected tree — passed the guard unexamined.

    The retry collapses every run of two or more stars to one, which is how the
    shell reads them without `globstar`. It must be a regex, not
    `str.replace("**", "*")`: that consumes stars pairwise, so `.cl***de` becomes
    `.cl**de` — still raising, still matching nothing, still a bypass — and a bare
    `***` would collapse to `**`, turning the retry into a recursive full-tree
    walk on a hook that runs for every Bash call. Normalising only on failure
    keeps real recursive globs recursive wherever Python supports them. A blanket
    fail-closed on the exception was the other option and is wrong here:
    `Path.glob` raises on ordinary tokens, so `python -c "print(2**8)"` would be
    denied.
    """
    for candidate in (pattern, re.sub(r"\*{2,}", "*", pattern)):
        try:
            return list(base.glob(candidate))
        except (OSError, ValueError, NotImplementedError):
            continue
    return []


def _cd_bases(command: str) -> list[Path]:
    """Directories the command `cd`s into, each a base a later relative glob would
    resolve from. The repo root is always included. A glob-spelled `cd` target
    (`cd .?laude`) is itself expanded from the repo root, so `cd .?laude && …`
    resolves like `cd .claude && …`.

    Each target is also resolved from the directory the previous `cd` reached,
    so `cd scripts && cd hooks && rm x` has a base at `scripts/hooks`, and
    `pushd` and `cd -P`/`-L` count like a plain `cd`. With every written operand
    now resolved from these bases (agent-loopholes-6442185e), a chain that only
    ever resolved from the root would reopen the hole one `cd` deeper. Resolving
    from both the root and the chain over-approximates the shell, which only
    adds places a path is checked from.
    """
    bases = [_REPO_ROOT]
    current = [_REPO_ROOT]
    for match in _CD_RE.finditer(command):
        raw = match.group(1)
        if _GLOB_META_RE.search(raw):
            from_root = _shell_glob(_REPO_ROOT, raw)
            reached = [hit for base in current for hit in _shell_glob(base, raw)]
        else:
            from_root = [_REPO_ROOT / raw]
            reached = [base / raw for base in current]
        current = list(dict.fromkeys(reached)) or current
        bases += from_root + current
    return list(dict.fromkeys(bases))


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
        parent = str(PurePosixPath(token).parent)
        # A parent ending in `**` matches every directory in the tree, the
        # agents one included, so probing it says nothing about where the token
        # lands: `ls **/*.py` was denied through it (agent-hooks-bbb2edb0). The
        # token itself is still expanded, so `cat .claude/**` stays caught.
        probes = (token,) if PurePosixPath(parent).name == "**" else (token, parent)
        for pattern in probes:
            if not pattern or pattern in (".", "/"):
                continue
            rel = pattern
            if PurePosixPath(pattern).is_absolute():
                try:
                    rel = str(PurePosixPath(pattern).relative_to(_REPO_ROOT))
                except ValueError:
                    continue  # absolute but outside the repo — nothing to check
            for base in bases:
                if any(_hit_in_agents(hit, agents_dir) for hit in _shell_glob(base, rel)):
                    return True
    return False


def _hit_in_agents(hit: Path, agents_dir: Path) -> bool:
    """True if one glob hit resolves at or under the agents tree.

    A hit that cannot be resolved counts as inside. A symlink loop raises here on
    3.11/3.12; uncaught, that exited 1 and Claude Code let the call through, so a
    loop plus a glob disabled the whole guard (agent-loopholes-02f83e02).
    """
    try:
        resolved = hit.resolve()
    except (OSError, RuntimeError):
        return True
    return resolved == agents_dir or agents_dir in resolved.parents


def _names_agent_file(command: str) -> bool:
    """True if any shell token's final path segment is exactly a protected agent
    filename.

    Token-boundary, not substring: `name in command` would also block
    `cat release-readiness-reviewer.md.bak`, a different file the guard has no
    business touching. Splitting on shell separators (and `=`/`,`, so
    `--file=<name>` and comma-joined lists still resolve) and comparing the
    basename keeps the exact-name match while dropping the false positives.
    """
    for token in re.split(r"[\s;&|<>()=,]+", command):
        if token and PurePosixPath(token).name in _AGENT_FILES:
            return True
    return False


def _references_agents(command: str) -> bool:
    """True if the command reaches .claude/agents/ by any spelling the shell would
    resolve there — literal, quoted, escaped, variable-built, or glob."""
    c = _canonicalize(command)
    # The worktree segment is dropped for the textual pass only; the filename
    # and glob passes still see it, and a worktree's own `.claude/agents` keeps
    # its literal spelling after the drop.
    text = _WORKTREE_RE.sub("", c)
    if _textual_reference(text):
        return True
    if _names_agent_file(c):
        return True
    return _glob_reaches_agents(c)


# A shell word, for the textual pass: separators and redirections split it.
_WORD_SPLIT = re.compile(r"[\s;&|<>()]+")
# `NAME=value`, optionally after `export`/`declare -x`/`local`/`readonly`.
_ASSIGN_RE = re.compile(r"(?:^|[\s;&|(])([A-Za-z_]\w*)=([^\s;&|()<>]*)")
_VAR_RE = re.compile(r"\$\{?([A-Za-z_]\w*)\}?")


def _token_reaches_agents(token: str) -> bool:
    """True if one shell word spells a path into the agents tree."""
    return bool(
        _DENIED_RE.search(token) or (_CLAUDE_RE.search(token) and _AGENTS_INDIRECT_RE.search(token))
    )


def _textual_reference(text: str) -> bool:
    """True if a word of `text`, variables expanded, spells a path into the agents tree.

    Matched per word, not across the command. The whole-text match paired a
    `.claude` in one word with an `agent` in another, so
    `sed -n 1p .claude/skills/graphify/SKILL.md; grep -n x
    skills/nitpicker/commands/agent-rules.md` — two reads, neither in the tree —
    was denied (agent-hooks-bbb2edb0), a refusal an agent cannot act on.

    Variable-built paths are the reason the match used to span words, so the
    variables the command assigns are expanded into each word first:
    `A=agents; cat .claude/$A/x` and `D=.claude; cat $D/agents/x` become
    `.claude/agents/x`. Where a word still carries a substitution this pass
    cannot resolve — a variable from the environment, `$(...)`, a backtick —
    the old whole-text match applies, since the unresolved part may supply
    either half. That residual false positive needs a `$` or backtick in the
    command, and errs toward denying.
    """
    assigned = dict(_ASSIGN_RE.findall(text))
    dynamic = False
    for token in _WORD_SPLIT.split(text):
        for _ in range(len(assigned) + 1):  # a value may itself name a variable
            expanded = _VAR_RE.sub(lambda m: assigned.get(m.group(1), m.group(0)), token)
            if expanded == token:
                break
            token = expanded
        if _token_reaches_agents(token):
            return True
        dynamic = dynamic or "$" in token or "`" in token
    return dynamic and bool(_CLAUDE_RE.search(text) and _AGENTS_INDIRECT_RE.search(text))


def main() -> None:
    """Block a Bash command that reaches one of the protected trees.

    Two denials rather than one, because the two surfaces are guarded
    differently: any shell reference to `.claude/agents/`, but only a write to
    the `PROTECTED_WRITE` paths, which may be read. Exit 2 is a PreToolUse deny
    and surfaces stderr to the agent.
    """
    data = load_event_strict()

    command = event_command(data)
    code = foreign_code(data)
    if _references_agents(command) or _references_agents(code):
        # PreToolUse: exit 2 blocks the call and surfaces stderr to the agent.
        print(f"  DENIED  Bash command references {DENIED}", file=sys.stderr, flush=True)
        sys.exit(2)
    if _names_protected(code):
        print(
            "  DENIED  code the guard cannot tokenize names the enforcement surface "
            f"({', '.join(PROTECTED_WRITE)}).\n"
            "          Code in another language, or text piped into a shell, cannot\n"
            "          be judged as a read or a write, so it is refused. Read these\n"
            "          paths with a plain shell command.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(2)
    if _writes_protected(command):
        print(
            "  DENIED  Bash command writes to the enforcement surface "
            f"({', '.join(PROTECTED_WRITE)}).\n"
            "          permissions.deny covers the edit tools, not Bash. Reading\n"
            "          these paths is allowed; changing them is the owner's call.",
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
        print(f"  DENIED  agents-path guard failed internally: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)
