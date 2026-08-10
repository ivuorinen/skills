#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PreToolUse hook — block Bash commands that reach the protected trees.

The `permissions.deny` list in .claude/settings.json covers Read/Edit/Write but
never Bash — `head`, `sed -i`, or a redirection walks straight past it. This
hook closes that surface for the Bash tool, in two different shapes because the
deny list itself has two shapes:

- `.claude/agents/**` denies Read as well as Edit/Write, so ANY reference is
  blocked (see `_references_agents`).
- `scripts/hooks/**` and `.claude/settings.json` deny only Edit/Write/
  NotebookEdit — Read stays allowed — so only a WRITE is blocked (see
  `_writes_protected`). Denying `cat scripts/hooks/ruff-hook.py` would
  contradict the permission model and break ordinary work.
"""

import re
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import (  # type: ignore[import-not-found]
    load_event,
    repo_root,
    shell_stages,
    skip_git_global_opts,
)

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


# ── protected-write paths ─────────────────────────────────────────────────────
#
# permissions.deny also covers Edit/Write/NotebookEdit on `scripts/hooks/**` and
# `.claude/settings.json` — the enforcement surface itself — and Bash walks past
# those exactly as it does for the agents tree. Unlike `.claude/agents`, Read is
# NOT denied for them, so this half matches a MUTATION only.
#
# Ceiling, stated rather than implied: this matches redirection targets, a fixed
# set of mutating verbs, in-place stream editors, and the `git` subcommands that
# write the working tree. A write performed *inside* an interpreter
# (`python -c "open(p, 'w')"`), by a script that takes the path as data, or
# through a symlink is not matched. As with the agents half, CODEOWNERS plus
# branch protection remains the binding control; this raises the cost of the
# bypass, it does not close it.
PROTECTED_WRITE = ("scripts/hooks", ".claude/settings.json")

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
    """True if a repo-relative POSIX path sits at or under a protected-write root."""
    rel = rel.strip()
    while rel.startswith("./"):
        rel = rel[2:]
    return any(rel == root or rel.startswith(root + "/") for root in PROTECTED_WRITE)


def _protected_path(path: Path) -> bool:
    """True if a filesystem path resolves inside a protected-write root."""
    try:
        rel = path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return False
    return _under_protected(rel)


def _token_writes_protected(token: str, command: str) -> bool:
    """True if `token`, read as a path, lands under a protected-write root.

    `--file=path` and `dd of=path` carry the path after an `=`, so the tail is
    taken. Glob tokens are expanded through the same machinery the agents half
    uses, so `scripts/ho*ks/*.py` resolves rather than being read literally.
    """
    token = token.split("=", 1)[-1]
    if not token:
        return False
    pure = PurePosixPath(token)
    if pure.is_absolute():
        try:
            token = str(pure.relative_to(_REPO_ROOT))
        except ValueError:
            return False  # absolute but outside the repo — nothing to protect
    if _under_protected(token):
        return True
    if _GLOB_META_RE.search(token):
        for base in _cd_bases(command):
            for hit in _shell_glob(base, token):
                if _protected_path(hit):
                    return True
    return False


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


def _stage_writes_protected(tokens: list[str], c: str) -> bool:
    """True if this one mutating stage writes a protected path.

    The git arm runs first: an unscoped worktree rewrite reaches the protected
    paths without ever naming them, so the operand scan below cannot see it.
    """
    if PurePosixPath(tokens[0]).name == "git" and _git_rewrites_worktree(tokens):
        return True
    return any(_token_writes_protected(a, c) for a in tokens[1:])


def _writes_protected(command: str) -> bool:
    """True if the command writes to scripts/hooks/ or .claude/settings.json."""
    c = _canonicalize(command)
    if _redirects_into_protected(c):
        return True
    stages = [t for t in shell_stages(c) if _stage_is_mutating(t)]
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
    resolves like `cd .claude && …`."""
    bases = [_REPO_ROOT]
    for match in re.finditer(r"(?:^|[\s;&|(])cd\s+([^\s;&|()<>]+)", command):
        raw = match.group(1)
        if _GLOB_META_RE.search(raw):
            bases.extend(_shell_glob(_REPO_ROOT, raw))
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
                for hit in _shell_glob(base, rel):
                    resolved = hit.resolve()
                    if resolved == agents_dir or agents_dir in resolved.parents:
                        return True
    return False


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
    if _DENIED_RE.search(c) or (_CLAUDE_RE.search(c) and _AGENTS_INDIRECT_RE.search(c)):
        return True
    if _names_agent_file(c):
        return True
    return _glob_reaches_agents(c)


def main() -> None:
    """Block a Bash command that reaches one of the protected trees.

    Two denials rather than one, because permissions.deny protects the two
    surfaces differently: any reference to `.claude/agents/`, but only a
    write to `scripts/hooks/` or `.claude/settings.json`, where Read stays
    allowed. Exit 2 is a PreToolUse deny and surfaces stderr to the agent.
    """
    data = load_event()
    if data is None:
        return

    command = (data.get("tool_input") or {}).get("command") or ""
    if _references_agents(command):
        # PreToolUse: exit 2 blocks the call and surfaces stderr to the agent.
        print(f"  DENIED  Bash command references {DENIED}", file=sys.stderr, flush=True)
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
    main()
