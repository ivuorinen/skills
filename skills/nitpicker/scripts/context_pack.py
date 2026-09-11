#!/usr/bin/env python3
"""Build bounded repository context packs so raw source never enters the model context.

Ships inside the nitpicker skill: stdlib-only, Python 3.11+, no uv required.

The problem this exists for: an agent asked to "read only relevant files" reads
whole files, because a whole file is never wrong. Keeping repository bytes out
of context was previously a convention enforced by an external plugin's hook,
which means it evaporated in every harness that lacked the plugin — Copilot,
pi, CI, a bare spec-conforming host. This module makes the containment a
property of nitpicker itself: it answers with *coordinates and reasons*
(path, line range, enclosing symbol, why it matched), never with file bodies.

Four modes, matching the context-acquisition ladder in `_conventions.md`:

    inventory  Level A — what exists, in what language, how big. No source.
    symbols    Level B — declaration outlines. Signature lines only.
    diff       Level B — changed hunks and the symbol enclosing each.
    evidence   Level C — the smallest ranges matching the goal's terms.

No mode returns a full file. That is deliberate and is the whole point: Level D
is a direct read the caller performs itself, after this tool has told it which
few lines to open. The invariant the callers are held to lives in the
conventions: compression may decide what to inspect next, only original source
may prove a finding.

Budgets are enforced against an *estimate* (four characters per token). That is
adequate for deciding how much to pack and is explicitly not adequate as a CI
gate — see `scripts/check-context-tokens.py`, which says the same thing about
its own numbers. A pack reports both its estimate and the bytes behind it so a
caller can judge.
"""

from __future__ import annotations

import argparse
import ast
import json
import re

# git plumbing only, argv lists, never shell=True. The reason sits above the
# suppression, never after it: bandit reads whatever trails the marker as a list
# of test ids, so a prose clause there becomes one bogus "not a test name"
# warning per word. That applies to prose *about* the marker too — spelling it
# out in a comment is itself picked up, which is why this note does not.
import subprocess  # nosec B404
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Tokens are estimated at four characters each. Every consumer of this constant
# labels the result an estimate; nothing gates on it.
CHARS_PER_TOKEN = 4

# Seconds any one git call may take. Generous for `ls-files` on a large
# repository, short enough that a git which blocks — a credential helper waiting
# on a TTY, a filter driver, an unresponsive network mount under `.git` —
# surfaces as a failure instead of a hang. Unbounded was worse here than in a
# hook: `mcp_server` is a single-threaded stdio loop, so one wedged git stalls
# every later tool call on the server, and a call that never returns is never
# recorded as "errored" either.
GIT_TIMEOUT = 60

MODES = ("inventory", "symbols", "diff", "evidence")

# Extension -> language label. Not exhaustive by design: an unmapped extension
# reports as its bare suffix rather than being dropped, because a file the
# inventory omits is a file no lens can decide to skip on purpose.
LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".sh": "shell",
    ".bash": "shell",
    ".sql": "sql",
    ".tf": "terraform",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".scss": "css",
    ".vue": "vue",
    ".svelte": "svelte",
}

# Declaration shapes for the non-Python fallback. Python uses `ast`; everything
# else gets one regex per family, which finds declarations well enough to give a
# candidate an enclosing name and deliberately does not pretend to be a parser.
_DECL = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?(?:public\s+|private\s+|protected\s+|static\s+|async\s+)*"
    r"(?:function|class|interface|type|struct|enum|trait|impl|def|fn|func|const|resource|module|job)"
    r"\s+[\"']?([A-Za-z_$][\w$.-]*)"
)

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

# Constructs whose signature is punctuation, and which lexical matching therefore
# cannot reach at all. `_WORD` needs three characters, so an unsound cast — whose
# whole signature is the two-character `as` — has no term for a goal to match,
# and the safe `isUser()` in the same file carries `as` too. An entire defect
# family was invisible to `evidence` mode for that reason: unsound casts,
# non-null assertions, loose equality.
#
# A construct is activated by a goal that NAMES it, through `aliases` — a lens
# asks for `unchecked cast ...` and gets the operator, without the caller
# learning a new argument. Nothing activates on its own, so a goal that names no
# construct packs exactly what it did before.
#
# Regexes, not a parser: these are shipped stdlib-only tools, so tree-sitter and
# an LSP are both out. That is the ceiling and it is a real one — this finds the
# construct's *shape*, never its meaning, so `as User` and the legitimate
# `as Record<string, unknown>` inside a type guard both match. Ranking two
# candidates where there were none is the improvement; telling them apart needs
# the syntax-aware provider this deliberately is not.
#
# `languages` is matched against `_language()`. Every construct names its own;
# there is no "all languages" spelling, because each of these is punctuation that
# means something different elsewhere — `as` is an import in Python, `!` is
# negation nearly everywhere.
_CONSTRUCTS: dict[str, tuple[frozenset[str], frozenset[str], re.Pattern[str]]] = {
    # `x as T` — a type assertion that silently unchecks everything downstream.
    # `as const` is excluded: it narrows rather than widens, so it is the one
    # spelling of this operator that asserts nothing.
    "unsound-cast": (
        frozenset({"cast", "casts", "assertion", "assertions", "coercion", "unsound"}),
        frozenset({"typescript", "javascript"}),
        re.compile(r"\bas\s+(?!const\b)[A-Z_$]"),
    ),
    # `value!.field` / `value!` — asserts non-null to the checker and to nobody
    # else. The lookarounds keep `!=` and a leading `!` negation out.
    "non-null-assertion": (
        frozenset({"non-null", "nonnull", "assertion", "assertions", "bang"}),
        frozenset({"typescript"}),
        re.compile(r"[\w\)\]]!(?=\s*[.\[(;,)]|\s*$)"),
    ),
    # `==` / `!=` where the language has a strict form — type coercion at a
    # comparison. Excludes `===`, `!==`, `<=`, `>=` and `=>`.
    "loose-equality": (
        frozenset({"equality", "coercion", "comparison", "loose"}),
        frozenset({"typescript", "javascript", "php"}),
        re.compile(r"(?<![=!<>])(?:==|!=)(?!=)"),
    ),
}


def _active_constructs(terms: set[str], language: str) -> list[tuple[str, re.Pattern[str]]]:
    """Constructs this goal named, narrowed to those meaningful in `language`.

    Both halves matter. Without the alias test every pack would carry every
    construct and `loose-equality` alone would match most of a JavaScript file.
    Without the language test, `as User` would be hunted in Python, where `as`
    is an import and a context manager and never a cast.
    """
    return [
        (name, pattern)
        for name, (aliases, languages, pattern) in _CONSTRUCTS.items()
        if terms & aliases and language in languages
    ]


# Directories never worth walking when git cannot enumerate the tree for us.
_SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "target",
        "vendor",
        ".next",
    }
)


class PackError(Exception):
    """A usage failure: the caller passed something this module cannot act on.

    Reported at exit 2 by the CLI and as a bad argument by the MCP tool, so the
    caller's next move is to fix the call.
    """


class PackEnvironmentError(PackError):
    """The host could not run the work — git absent, broken, or hung.

    Subclasses `PackError` so every existing `except PackError` site keeps
    catching it, but carries the opposite instruction: nothing about the call
    was wrong, so retrying with different arguments cannot help. Reported at
    exit 1, which is what lets `_conventions.md`'s preflight rule record the
    tool as unavailable rather than record the run as clean. Collapsing the two
    onto one code left an agent retrying argument variations against a host
    with no git.
    """


@dataclass(frozen=True)
class Candidate:
    """One source region worth opening, described without quoting it.

    `reason` carries the signals that selected the region so a caller can judge
    the pack rather than trusting its ranking. `symbol` is the enclosing
    declaration where one was resolvable — the unit a reader actually wants,
    since a bare line range severed from its function is evidence nobody can
    check.
    """

    path: str
    start: int
    end: int
    score: float
    reason: tuple[str, ...]
    symbol: str = ""
    tokens: int = 0


@dataclass
class Pack:
    """A mode's result plus what it refused to include and why.

    `omitted` is not bookkeeping. A pack that silently drops most of the
    repository reads exactly like a repository with nothing in it, which is the
    failure every "clean result" rule in this skill exists to prevent.
    """

    mode: str
    goal: str
    budget: dict = field(default_factory=dict)
    candidates: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    omitted: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def estimate_tokens(text: str) -> int:
    """Characters divided by four. An estimate, never a gate — see the module docstring."""
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def _git(root: Path, *args: str) -> str:
    """Run one git plumbing command, or raise PackError naming what failed.

    Returns stdout. A non-zero exit is an error rather than an empty result:
    treating a failed `git diff` as "nothing changed" would report a broken
    invocation as a clean diff.

    The three failure shapes are classified apart, because the caller's next
    move differs: an absent or hung binary is the host's problem
    (`PackEnvironmentError`, exit 1) while a rejected argument — a revision that
    does not resolve — is the call's (`PackError`, exit 2). `_tracked_files`
    already handles a git that *fails* by falling back to a walk, so leaving a
    git that *hangs* unbounded was the one shape nothing covered.
    """
    try:
        # fixed argv, no shell, git only — reason above the marker, see the
        # `import subprocess` note on why nothing may trail it.
        proc = subprocess.run(  # nosec B603
            ["git", *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise PackEnvironmentError(f"git {' '.join(args)} timed out after {GIT_TIMEOUT}s") from exc
    except OSError as exc:
        raise PackEnvironmentError(f"git is not available: {exc}") from exc
    if proc.returncode != 0:
        raise PackError(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.returncode}")
    return proc.stdout


def _rev(base: str) -> str:
    """`base` if it can only be read as a revision, else a PackError.

    git parses any argument starting with `-` as an option, and `git diff`
    accepts options that write files, read files and run filters. `base` reaches
    this module from wherever the caller got it — a branch name, a PR base ref,
    the free text after `/nitpicker review` — so a value like
    `--output=/path/to/write` turns a read-only pack into an arbitrary file
    write. Callers pass `--` after the revision as well; this is the check that
    makes the option interpretation impossible in the first place.
    """
    if not base or base.startswith("-"):
        raise PackError(
            f"--base must name a revision, not an option. Received: {base!r}. "
            "Pass a branch, tag, or commit (for example HEAD, main, or a sha)."
        )
    return base


def _tracked_files(root: Path) -> list[Path]:
    """Every tracked file, from git where possible and a filtered walk otherwise.

    git is preferred because it applies `.gitignore` for free; the walk is the
    fallback for a checkout that is not a repository, and skips the build and
    dependency directories git would have excluded anyway.

    `--cached --others --exclude-standard` is the working tree minus what
    `.gitignore` excludes — tracked files *and* untracked ones. Plain `ls-files`
    lists only what is committed, so any directory whose contents are new
    enumerated as empty: a freshly scaffolded subproject, a generated tree, work
    in progress. The pack then reported zero files, which is exactly the
    "indistinguishable from an empty repository" answer `omitted` exists to
    prevent. An audit reads the working tree, not the index.
    """
    try:
        listing = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    except PackError:
        return sorted(_walk(root))
    return [root / name for name in listing.split("\0") if name]


def _walk(root: Path) -> list[Path]:
    """Filtered recursive walk, used only when git cannot enumerate the tree.

    Symlinked entries are skipped outright. `is_dir()` follows a link, so
    `sub/link -> ..` would push its own ancestor back on the stack and the walk
    would never terminate — and this is the non-git path, so the tree is exactly
    the kind nobody vetted. `GIT_TIMEOUT` does not bound it (no git runs here),
    and `mcp_server` serves stdio single-threaded, so one such call would stall
    every later tool call in the session. The containment test in `_read`
    guards the read, not the traversal.
    """
    out: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in _SKIP_DIRS:
                    stack.append(entry)
            elif entry.is_file():
                out.append(entry)
    return out


def _language(path: Path) -> str:
    return LANGUAGES.get(path.suffix.lower(), path.suffix.lstrip(".") or "none")


def _read(path: Path, root: Path) -> str | None:
    """File text, or None for anything unreadable, not text, or outside `root`.

    Binary and undecodable files are skipped rather than raised on: a pack over
    a repository containing one PNG must still answer.

    The containment test is the security-relevant half, and it belongs here
    rather than at each call site because this is the single choke point every
    mode reads through. A repository may contain a tracked *symlink* pointing
    anywhere on the host — `~/.aws/credentials`, `/etc/passwd`, a sibling
    checkout — and following it would rank, range and return that file's
    contents under an in-repo path. `skill-safety` and `deps` exist to audit
    untrusted third-party trees, which are exactly the ones likely to carry a
    hostile symlink and the ones where a plausible in-repo path in a pack draws
    no attention. `.resolve()` collapses the link before the test.

    Decoded as `utf-8-sig` rather than `utf-8`: a BOM left in place survives as
    a leading `\\ufeff`, which makes `ast.parse` raise and stops the regex
    fallback's `^\\s*` from matching, so a BOM'd file reported zero declarations
    — an empty outline indistinguishable from a file that genuinely has none.
    """
    try:
        if not path.resolve().is_relative_to(root):
            return None
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return None


def _line_count(path: Path, root: Path) -> int | None:
    """Lines in a file, counted without decoding it. None when unreadable.

    `inventory` needs a size, not text, and previously reached through `_read`
    to get one — so Level A, the mode whose whole contract is metadata without
    source, decoded every file in the repository to tally newlines. `build`'s
    docstring names a large repository as the case the design exists for, and
    the inventory is the mode a lens runs first, on the whole tree, before it
    knows what it wants.

    Counting bytes also fixes what the decode got wrong: `count("\\n") + 1`
    reported a newline-terminated file — the normal case — one line too many,
    systematically rather than randomly, so the error survived averaging. And
    `None` for unreadable is distinguishable from `0`, where the old path
    reported a binary file as an empty text file.

    The containment test `_read` performs is kept: a tracked symlink pointing
    at `~/.aws/credentials` must not be ranged or sized under an in-repo path.
    """
    try:
        if not path.resolve().is_relative_to(root):
            return None
        with path.open("rb") as handle:
            return sum(chunk.count(b"\n") for chunk in iter(lambda: handle.read(1 << 20), b""))
    except OSError:
        return None


def _scoped(root: Path, files: list[Path], paths: list[str]) -> list[Path]:
    """Narrow `files` to the caller's path prefixes, refusing any that escape the root."""
    if not paths:
        return files
    prefixes = []
    for raw in paths:
        resolved = (root / raw).resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise PackError(f"path escapes the project root: {raw}")
        prefixes.append(resolved)
    return [f for f in files if any(f.resolve().is_relative_to(p) for p in prefixes)]


# --------------------------------------------------------------------------- symbols


def _python_symbols(source: str) -> list[tuple[str, int, int]]:
    """(name, start, end) for every top-level and nested declaration, via `ast`.

    Returns [] on a syntax error rather than raising: a repository mid-edit
    still deserves an outline of the files that do parse, and the regex fallback
    covers the one that does not.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out: list[tuple[str, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            out.append((node.name, node.lineno, node.end_lineno or node.lineno))
    return sorted(out, key=lambda item: item[1])


def _regex_symbols(source: str) -> list[tuple[str, int, int]]:
    """(name, start, end) from declaration lines, for languages with no bundled parser.

    The end line is the line before the next declaration, which is an
    approximation and is stated as one: it is enough to name the symbol
    enclosing a hunk, and not enough to slice a body exactly.
    """
    starts: list[tuple[str, int]] = []
    for index, line in enumerate(source.splitlines(), start=1):
        match = _DECL.match(line)
        if match:
            starts.append((match.group(1), index))
    total = len(source.splitlines())
    return [
        (name, line, (starts[i + 1][1] - 1) if i + 1 < len(starts) else total)
        for i, (name, line) in enumerate(starts)
    ]


def symbols_of(path: Path, source: str) -> list[tuple[str, int, int]]:
    """Declaration outline for one file: `ast` for Python, regex for everything else."""
    if _language(path) == "python":
        found = _python_symbols(source)
        if found:
            return found
    return _regex_symbols(source)


def _enclosing(outline: list[tuple[str, int, int]], line: int) -> str:
    """The innermost declaration containing `line`, or "" when none does.

    Innermost wins so a method reports its own name rather than its class: the
    method is the unit a reader opens.
    """
    best = ""
    best_span = None
    for name, start, end in outline:
        if start <= line <= end:
            span = end - start
            if best_span is None or span < best_span:
                best, best_span = name, span
    return best


# --------------------------------------------------------------------------- modes


def _inventory(root: Path, files: list[Path], pack: Pack) -> None:
    """Level A: one row per file — path, language, bytes, lines. No source at all.

    Every skipped file is counted into `omitted`. A bare `continue` here made a
    pack over a tree with unreadable files indistinguishable from a pack over a
    tree that does not contain them — which is exactly what `Pack.omitted`'s
    docstring says this module exists to prevent, and what `_conventions.md`
    forbids reporting as clean. Deleted-but-still-indexed paths reach here
    routinely (`git ls-files --cached` lists them), so the count is not an edge
    case.
    """
    by_language: dict[str, int] = {}
    unstatable = 0
    unreadable = 0
    for path in sorted(files):
        try:
            size = path.stat().st_size
        except OSError:
            unstatable += 1
            continue
        language = _language(path)
        by_language[language] = by_language.get(language, 0) + 1
        lines = _line_count(path, root)
        if lines is None:
            unreadable += 1
        pack.files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "language": language,
                "bytes": size,
                "lines": lines,
            }
        )
    pack.omitted = {
        "files_unstatable": unstatable,
        "files_unreadable": unreadable,
        "reason": "stat failed (row omitted), or not readable as bytes (row kept, lines null)",
    }
    pack.notes.append(f"languages: {json.dumps(by_language, sort_keys=True)}")


def _symbols(root: Path, files: list[Path], pack: Pack) -> None:
    """Level B: declaration outlines, signature coordinates only, never bodies."""
    skipped = 0
    for path in sorted(files):
        source = _read(path, root)
        if source is None:
            skipped += 1
            continue
        outline = symbols_of(path, source)
        if not outline:
            continue
        pack.files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "language": _language(path),
                "symbols": [{"name": n, "lines": [s, e]} for n, s, e in outline],
            }
        )
    pack.omitted = {"files": skipped, "reason": "unreadable or not text"}


def _diff_reason(count: int, current: Path | None) -> tuple[str, ...]:
    """Why a hunk was selected, distinguishing a deleted file from deleted lines.

    Three cases the caller acts on differently: the file is gone
    (`deleted-file`, nothing to open in the working tree), lines were removed
    from a file that survives (`deleted-lines`, open the range in `base`), or
    lines exist in the post-image (`changed-hunk`).
    """
    if current is None:
        return ("deleted-file",)
    return ("changed-hunk",) if count else ("deleted-lines",)


def _diff(root: Path, files: list[Path], pack: Pack, base: str) -> None:
    """Level B for review workloads: changed hunks plus the symbol enclosing each.

    Whole changed files are deliberately not returned. The report's own finding
    is that a review reading entire changed files pays for unchanged code it
    already trusts, while still missing the unchanged *callers* a contract
    change breaks — which a hunk's enclosing symbol names and a file dump does
    not.
    """
    scope = {f.resolve() for f in files}
    # `--no-prefix` because the a/ and b/ prefixes are not fixed: a user with
    # `diff.mnemonicPrefix` set gets c/ and w/ instead, and a parser keyed to
    # `+++ b/` silently returns zero hunks on their machine.
    raw = _git(root, "diff", "--no-prefix", "--unified=0", _rev(base), "--")
    current: Path | None = None
    previous: Path | None = None
    outline: list[tuple[str, int, int]] = []
    for line in raw.splitlines():
        # Every entry resets the per-file state here. Keying only on `+++ `
        # meant a deleted file — whose post-image header is `+++ /dev/null` —
        # left `current` pointing at the *previous* entry, so its hunks were
        # emitted as candidates on an unrelated file while the deletion itself
        # produced none. Anchoring on `diff --git` also stops a *content* line
        # from being read as a header: an added line whose text is `++ b/foo`
        # renders as `+++ b/foo`, and this repo's docs quote diffs.
        if line.startswith("diff --git "):
            current, previous, outline = None, None, []
            continue
        if line.startswith("--- "):
            previous = None if line == "--- /dev/null" else root / line[4:]
            continue
        if line.startswith("+++ "):
            current = None if line == "+++ /dev/null" else root / line[4:]
            source = (_read(current, root) or "") if current else ""
            outline = symbols_of(current, source) if source and current else []
            continue
        hunk = _HUNK.match(line)
        # A deleted file has no post-image, so its hunks are attributed to the
        # pre-image path — the file the reader has to look at in `base`.
        target = current if current is not None else previous
        if not hunk or target is None or target.resolve() not in scope:
            continue
        first = int(hunk.group(1))
        count = int(hunk.group(2)) if hunk.group(2) else 1
        # A pure deletion is `+N,0`: no post-image lines exist, and N is the line
        # the removed content sat before. Point at that line rather than emitting
        # the empty range `N..N-1`, which reads as a malformed candidate.
        start = max(1, first if count else first + 1)
        end = max(start, first + count - 1)
        pack.candidates.append(
            asdict(
                Candidate(
                    path=target.relative_to(root).as_posix(),
                    start=start,
                    end=end,
                    score=1.0,
                    reason=_diff_reason(count, current),
                    symbol=_enclosing(outline, start),
                )
            )
        )
    pack.notes.append(f"base: {base}")


def _terms(goal: str) -> set[str]:
    """Distinct search terms from the goal text, lowercased, stop-words dropped."""
    stop = {"the", "and", "for", "with", "that", "this", "find", "any", "all", "are", "not"}
    return {w.lower() for w in _WORD.findall(goal)} - stop


def _evidence(root: Path, files: list[Path], pack: Pack, goal: str, budget: int) -> None:
    """Level C: the smallest ranges matching the goal's terms, packed to the budget.

    Ranges are windows around a match, snapped to the enclosing declaration when
    one is resolvable, because a match severed from its function cannot be
    judged. Packing stops at the budget and records how many candidates were
    left behind — a truncated pack that says nothing reads like a thorough one.
    """
    terms = _terms(goal)
    if not terms:
        raise PackError("goal contains no searchable term; state what is being looked for")
    found: list[Candidate] = []
    unreadable = 0
    for path in sorted(files):
        source = _read(path, root)
        if source is None:
            unreadable += 1
            continue
        found.extend(_file_candidates(root, path, source, terms))
    found.sort(key=lambda c: (-c.score, c.path, c.start))
    packed, spent = _pack_to_budget(found, budget)
    pack.candidates = [asdict(c) for c in packed]
    pack.budget = {"requested": budget, "estimated": spent, "unit": "estimated-tokens"}
    pack.omitted = {
        "files_scanned": len(files),
        "files_unmatched": len(files) - unreadable - len({c.path for c in found}),
        "files_unreadable": unreadable,
        "candidates_over_budget": len(found) - len(packed),
        "terms": sorted(terms),
        "reason": "no goal term matched, or the candidate did not fit the token budget",
    }


def _file_candidates(root: Path, path: Path, source: str, terms: set[str]) -> list[Candidate]:
    """Matching ranges in one file, one per matched line, snapped to enclosing symbols.

    A line matches on a goal TERM, on a CONSTRUCT the goal named, or on both.
    Construct matching runs against the raw line rather than the lowercased copy
    the term scan uses: `as User` is distinguished from `as user` by case, and
    lowercasing first would have made the cast pattern match a variable called
    `as_user`.
    """
    lines = source.splitlines()
    outline = symbols_of(path, source)
    constructs = _active_constructs(terms, _language(path))
    out: list[Candidate] = []
    for index, line in enumerate(lines, start=1):
        lowered = line.lower()
        matched = tuple(sorted(t for t in terms if t in lowered)) + tuple(
            sorted(name for name, pattern in constructs if pattern.search(line))
        )
        if not matched:
            continue
        symbol = _enclosing(outline, index)
        start, end = _range_for(outline, symbol, index, len(lines))
        body = "\n".join(lines[start - 1 : end])
        out.append(
            Candidate(
                path=path.relative_to(root).as_posix(),
                start=start,
                end=end,
                score=float(len(matched)),
                reason=matched,
                symbol=symbol,
                tokens=estimate_tokens(body),
            )
        )
    return _merge(out)


def _range_for(
    outline: list[tuple[str, int, int]], symbol: str, line: int, total: int
) -> tuple[int, int]:
    """The enclosing declaration's span, or a small window when no symbol encloses the line."""
    for name, start, end in outline:
        if name == symbol and start <= line <= end:
            return start, end
    return max(1, line - 8), min(total, line + 8)


def _merge(items: list[Candidate]) -> list[Candidate]:
    """Collapse overlapping ranges in one file into a single candidate.

    Without this, a term appearing eight times in one function yields eight
    candidates covering identical lines, and the budget is spent proving the
    same thing repeatedly.
    """
    out: list[Candidate] = []
    for item in sorted(items, key=lambda c: (c.start, c.end)):
        if out and item.start <= out[-1].end:
            previous = out[-1]
            out[-1] = Candidate(
                path=previous.path,
                start=previous.start,
                end=max(previous.end, item.end),
                score=previous.score + item.score,
                reason=tuple(sorted(set(previous.reason) | set(item.reason))),
                symbol=previous.symbol or item.symbol,
                # Summed, not `max`. The merged range can span more lines than
                # either input — a no-symbol window (line ±8) overlapping a
                # symbol's span widens it — and `max` then carried an estimate
                # for fewer lines than the candidate covers, so
                # `_pack_to_budget` under-counted what it had spent. Summing
                # over-estimates an overlap, which errs toward staying under
                # the caller's ceiling rather than over it.
                tokens=previous.tokens + item.tokens,
            )
        else:
            out.append(item)
    return out


def _pack_to_budget(items: list[Candidate], budget: int) -> tuple[list[Candidate], int]:
    """Take candidates in rank order, skipping any that does not fit the budget.

    A candidate is never truncated to fit: half a function is not evidence, and
    a range whose end was clipped invites a finding proved from the part that
    fit. Skipping rather than stopping is deliberate — one oversized candidate
    early in the ranking would otherwise discard every smaller one behind it.
    """
    packed: list[Candidate] = []
    spent = 0
    for item in items:
        if spent + item.tokens > budget:
            continue
        packed.append(item)
        spent += item.tokens
    return packed, spent


# --------------------------------------------------------------------------- entry


def build(
    root: Path,
    goal: str,
    mode: str,
    budget_tokens: int = 6000,
    paths: list[str] | None = None,
    changed_only: bool = False,
    base: str = "HEAD",
) -> dict:
    """Build one context pack. The single entry point the CLI and MCP tool share.

    `changed_only` narrows every mode to files git reports as changed against
    `base`, which is what makes `evidence` affordable on a large repository
    during review.
    """
    if mode not in MODES:
        raise PackError(f"--mode must be one of {', '.join(MODES)}. Received: {mode!r}")
    if budget_tokens < 256:
        raise PackError(f"--budget-tokens must be at least 256. Received: {budget_tokens}")
    # Validated here, at the boundary, rather than only where git is invoked:
    # `evidence` without `changed_only` never touches `base`, so a call-site-only
    # check let a hostile value through whenever the mode happened not to use it,
    # and would silently reopen the hole the next time a mode started using it.
    base = _rev(base)
    root = root.resolve()
    if not root.is_dir():
        raise PackError(f"not a directory: {root}")

    files = _tracked_files(root)
    if changed_only or mode == "diff":
        changed = {
            (root / name).resolve()
            for name in _git(root, "diff", "--name-only", _rev(base), "--").splitlines()
            if name
        }
        files = [f for f in files if f.resolve() in changed]
    files = _scoped(root, files, paths or [])

    pack = Pack(mode=mode, goal=goal)
    if mode == "inventory":
        _inventory(root, files, pack)
    elif mode == "symbols":
        _symbols(root, files, pack)
    elif mode == "diff":
        _diff(root, files, pack, base)
    else:
        _evidence(root, files, pack, goal, budget_tokens)

    result = asdict(pack)
    result["verification"] = (
        "Coordinates only. Re-read the original source at these ranges before filing a finding."
    )
    return result


def self_test(root: Path) -> dict:
    """Known-positive control: prove the retriever still finds something known to exist.

    A retriever that silently returns nothing is indistinguishable from a
    repository with nothing in it, which is exactly the "clean result" failure
    the conventions forbid. Two controls run against this module — a symbol it
    is guaranteed to contain — and one against `root`, so an empty pack over the
    caller's own tree is reported as a broken retriever rather than a clean one.
    """
    own = Path(__file__)
    outline = symbols_of(own, own.read_text(encoding="utf-8"))
    here = build(root=own.parent, goal="build context pack", mode="evidence")
    there = build(root=root, goal="self test", mode="inventory")
    checks = [
        {"control": "symbols-of-self", "passed": any(n == "build" for n, _, _ in outline)},
        {"control": "evidence-returns-candidates", "passed": bool(here["candidates"])},
        {"control": "inventory-lists-root", "passed": bool(there["files"])},
    ]
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="context-pack",
        description="Bounded repository context packs: coordinates and reasons, never file bodies.",
        epilog="Exit codes: 0 success, 1 runtime/IO error, 2 usage error.",
    )
    p.add_argument("--root", default=".", help="project root (default: cwd)")
    p.add_argument(
        "--goal", default="", help="what is being looked for; required for evidence mode"
    )
    p.add_argument("--mode", default="inventory", choices=MODES, help="acquisition level")
    p.add_argument("--budget-tokens", type=int, default=6000, help="estimated-token ceiling")
    p.add_argument("--paths", nargs="*", default=[], help="narrow to these path prefixes")
    p.add_argument("--changed-only", action="store_true", help="only files changed against --base")
    p.add_argument("--base", default="HEAD", help="diff base (default: HEAD)")
    p.add_argument("--self-test", action="store_true", help="run the known-positive controls")
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Structured JSON to stdout, diagnostics to stderr."""
    args = _parser().parse_args(argv)
    try:
        if args.self_test:
            result = self_test(Path(args.root))
            print(json.dumps(result, separators=(",", ":")))
            return 0 if result["passed"] else 1
        result = build(
            root=Path(args.root),
            goal=args.goal,
            mode=args.mode,
            budget_tokens=args.budget_tokens,
            paths=args.paths,
            changed_only=args.changed_only,
            base=args.base,
        )
    # Order matters: PackEnvironmentError subclasses PackError, so the
    # environment case must be caught first or it reports as a usage error and
    # tells an agent to fix arguments that were never wrong.
    except PackEnvironmentError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except PackError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
