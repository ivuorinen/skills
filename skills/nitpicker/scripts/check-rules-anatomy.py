#!/usr/bin/env python3
"""Check .claude/rules/ files for good rule file anatomy.

Usage:
    check-rules-anatomy.py [<project_root>]

Defaults to cwd when no argument given.

Checks each .md file under <project_root>/.claude/rules/ for:
    - Non-empty body
    - Kebab-case .md filename
    - Valid path-scoped frontmatter when present (paths: must be a list of relative globs)
    - No hedged language ("try to", "prefer", "consider", "generally", "when possible", "might")
    - Dangling symlinks

Outputs a JSON report to stdout. Each file entry lists findings with severity and detail.

Exit codes: 0 = no High/Critical issues, 1 = High or Critical issues found, or
an explicitly supplied <project_root> that has no .claude/rules/ subdirectory.
"""

import datetime
import functools
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import md_fences

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# A backticked repo-relative path: it has a directory separator or a known
# extension. Requiring the backticks is what keeps the false-positive rate
# usable — prose names files constantly, but a *reference* is quoted here.
_REPO_PATH_RE = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*(?:/[A-Za-z0-9_.-]+|\.[a-z]{2,5}))`")

# A directive whose whole point is that it is not negotiable. Deliberately
# narrow: `should`/`avoid` are the hedges the rule above already rejects, so a
# rule file that follows this repo's own style states its core as one of these.
_CRITICAL_RE = re.compile(r"\b(?:NEVER|Never|never|MUST|must not|Do not|DO NOT|Always|always)\b")

# The middle band, from the "lost in the middle" effect: an instruction at the
# top or bottom of a file survives; one buried between them is the one an agent
# skims past. Short files are exempt — in a 20-line rule every line is at some
# percentage, and the depth means nothing until there is enough file to get lost in.
_POSITION_BAND = (0.20, 0.80)
_POSITION_MIN_LINES = 40

# A section opener: a markdown heading, or a bolded lead-in that titles a bullet
# (`- **Never prompts.** …`). Both announce a rule; a sentence in a paragraph
# does not, and matching sentences is what made the first cut of this check
# score ordinary prose in a repo whose style guide mandates that prose.
_SECTION_OPENER_RE = re.compile(r"(#{1,6}\s|(?:[-*+]\s+)?\*\*)")


_NOT_A_PATH_SUFFIX = re.compile(r"\.(?:ai|com|io|org|net|dev|sh|md5)$")

# An unfilled slot. `YYYY-MM-DD` and friends are what a template leaves behind
# when it is copied and not completed, and a rule carrying one states a
# requirement nobody can satisfy.
_PLACEHOLDER_RE = re.compile(r"(YYYY-MM-DD|XXXX?|\bTBD\b|\bTODO\b|\bFIXME\b|\{\{[^}]*\}\})")

# An ISO date in prose. Rules describe standing policy, so a date in one is
# either a decision record or a deadline; both rot.
_ISO_DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_STALE_DATE_DAYS = 180

# A same-file section link. Cross-file links are `stale_path`'s job.
_ANCHOR_LINK_RE = re.compile(r"\]\(#([a-z0-9][a-z0-9-]*)\)")


def _slug(heading: str) -> str:
    """GitHub's heading-to-anchor slug, close enough for a same-file link.

    Lowercase, punctuation dropped, spaces to hyphens. Matching GitHub exactly
    would need its full algorithm; this covers the shapes a rule file uses and
    errs toward *not* reporting — an anchor this misses is a missed finding,
    while one it invents is a false alarm on a commit-time gate.
    """
    text = re.sub(r"`[^`]*`", "", heading.lstrip("#").strip())
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_]+", "-", text)


def _looks_illustrative(ref: str) -> bool:
    """True when a backticked token is not a claim that this repo holds that file.

    Three things wear the shape of a repo path and are not one, all three seen in
    this repo's own rules on the first run of this check:

    - a domain (`claude.ai`) — `.ai` reads as an extension;
    - a GitHub slug (`PyCQA/bandit`) — two segments, no extension;
    - a deliberate example (`src/auth.py`, a glob, a `<placeholder>`), because a
      rule file teaches by showing and names paths that are meant not to exist.

    Each false positive costs more than the miss it prevents: this backs a
    commit-time gate, and a check that cries wolf gets switched off rather than
    heeded.
    """
    if any(c in ref for c in "*<>{}$"):  # glob or placeholder
        return True
    if ref.startswith(("/", "~", "http")):  # absolute, or a URL fragment
        return True
    if _NOT_A_PATH_SUFFIX.search(ref):  # a domain, not a file
        return True
    parts = ref.split("/")
    if len(parts) == 2 and "." not in parts[1]:  # org/repo slug
        return True
    return parts[0] in {"src", "path", "example", "foo", "bar", "tmp", "a", "b"}


@functools.lru_cache(maxsize=8)
def _tracked(root: Path) -> tuple[frozenset[str], frozenset[str]]:
    """(relative paths, basenames) under `root`, for resolving a reference.

    A rule cites a file by whatever spelling reads clearly at that point — the
    repo-relative path, or just `findings.py` when the surrounding sentence
    already says where it lives. Both are correct prose and neither is stale, so
    resolution accepts either. Cached because every rule file asks the same
    question of the same tree.

    Walks the filesystem rather than shelling to `git ls-files`: this is a
    stdlib-only shipped tool, and it must answer the same way in a consumer
    checkout that has no git.
    """
    rel: set[str] = set()
    base: set[str] = set()
    skip = {".git", "node_modules", ".venv", "__pycache__", "graphify-out", ".pytest_cache"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in filenames:
            full = Path(dirpath, name)
            rel.add(full.relative_to(root).as_posix())
            base.add(name)
    return frozenset(rel), frozenset(base)


_HEDGED_RE = re.compile(
    r"\b(try to|prefer|consider|generally|when possible|might|may want to|should consider)\b",
    re.IGNORECASE,
)


def _parse_frontmatter(text: str) -> tuple[dict | None, str]:  # noqa: C901
    """Return (fm_dict, body). ({}, text) if no frontmatter. (None, text) if malformed."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text

    lines = text.splitlines(keepends=True)
    fm_lines: list[str] = []
    body_start: int | None = None

    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip() == "---":
            body_start = i + 1
            break
        fm_lines.append(line)

    if body_start is None:
        return None, text

    fm: dict = {}
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in fm_lines:
        stripped = line.rstrip()
        content = stripped.lstrip()
        if content.startswith("- ") and current_key is not None:
            item = content[2:].strip().strip("\"'")
            if current_list is None:
                current_list = []
                fm[current_key] = current_list
            current_list.append(item)
        elif ":" in stripped and not stripped.startswith(" "):
            current_list = None
            k, _, v = stripped.partition(":")
            current_key = k.strip()
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                # YAML flow-style list, e.g. paths: ["src/**", "lib/**"]
                items = [x.strip().strip("\"'") for x in v[1:-1].split(",")]
                fm[current_key] = [x for x in items if x]
            elif v:
                fm[current_key] = v.strip("\"'")
        elif not content:
            # A blank line inside a list is not a terminator — keep collecting,
            # so a gap between items doesn't drop everything before it. (YAML-
            # correct; single source of truth also imported by validate-rules.py.)
            continue
        else:
            current_list = None

    return fm, "".join(lines[body_start:])


def _check_file(path: Path, project_root: Path, contain: Path | None = None) -> list[dict]:  # noqa: C901
    """Every anatomy problem in one rule file, as findings rather than exceptions.

    Returns a list so one unusable rule does not hide the rest: this backs a
    commit-time gate, and an author fixing rules wants the whole set in a single
    run. Severity is carried per finding because the gate fails on the serious
    ones and merely reports the rest — a rule that will not load is a different
    problem from one that loads and reads poorly.
    """
    findings: list[dict] = []

    def issue(severity: str, code: str, detail: str) -> None:
        findings.append({"severity": severity, "code": code, "detail": detail})

    if path.is_symlink() and not path.exists():
        issue("High", "dangling_symlink", "Symlink target missing — rule will not load")
        return findings

    if contain is not None:
        # Symlinks in `.claude/rules` are followed on purpose — rules get shared
        # between projects that way — so the walk cannot simply refuse them. But
        # a caller confined to a project root must not reach past it: this file
        # is read below, and `hedged_language` quotes the matching line back, so
        # an escaping link turns any file on disk into line-granular disclosure.
        # Reported rather than dropped, matching the dangling case above: a
        # silently skipped rule is a narrower scan wearing a clean result.
        try:
            outside = not path.resolve().is_relative_to(contain)
        except OSError:
            outside = True  # cannot resolve it, so cannot vouch for it
        if outside:
            # The resolved target is deliberately absent from the message: naming
            # it would disclose the path this branch exists to refuse to read.
            issue(
                "High",
                "symlink_escapes_root",
                "Symlink resolves outside the project root — not read",
            )
            return findings

    # Every suffix the discovery table accepts, not `.md` alone. Cursor's rules
    # are `.mdc`, so a valid Cursor rule set landed entirely in `with_issues` —
    # the same partial-harness assumption that made this tool refuse those
    # projects outright, surviving one level down as a per-file finding.
    if path.suffix not in _RULE_SUFFIXES:
        issue(
            "Low",
            "unsupported_extension",
            f"Filename must use a supported rule extension "
            f"({', '.join(sorted(_RULE_SUFFIXES))}); got '{path.suffix}'",
        )

    # `.github/instructions/` uses a `<name>.instructions.md` convention, so
    # `Path.stem` keeps a `.instructions` tail that no kebab-case pattern
    # accepts. Judging the raw stem reported every Copilot instruction file as
    # malformed — the same harness assumption that flagged every `.mdc`,
    # surviving one level further down.
    stem = path.stem
    if stem.endswith(".instructions"):
        stem = stem[: -len(".instructions")]
    if not _KEBAB_RE.match(stem):
        issue("Low", "non_kebab_case", f"Filename stem must be kebab-case (got '{stem}')")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        issue("High", "unreadable", f"Cannot read file: {e}")
        return findings

    if not text.strip():
        issue("High", "empty_file", "File is empty — rule will be ignored")
        return findings

    fm, body = _parse_frontmatter(text)

    if fm is None:
        issue("High", "malformed_frontmatter", "Frontmatter opened with '---' but never closed")
        return findings

    if fm:
        paths_val = fm.get("paths")
        if paths_val is not None:
            if not isinstance(paths_val, list):
                issue("High", "paths_not_list", "'paths:' must be a list of glob strings")
            else:
                for glob in paths_val:
                    if not glob:
                        issue("Medium", "empty_glob", "'paths:' contains an empty glob string")
                    elif glob.startswith("/"):
                        msg = f"'paths:' glob must be relative: {glob!r}"
                        issue("Medium", "absolute_glob", msg)
                    elif ".." in Path(glob).parts:
                        msg = f"'paths:' glob must not traverse root: {glob!r}"
                        issue("Medium", "traversal_glob", msg)
                    else:
                        try:
                            matched = any(True for _ in project_root.glob(glob))
                        except ValueError:
                            # '**' mixed with other chars in a path component raises
                            # ValueError on CPython <3.13; treat it as a bad pattern
                            # rather than crashing the whole run (uncaught otherwise).
                            issue(
                                "Medium",
                                "invalid_glob",
                                f"'paths:' glob is not a valid pattern: {glob!r}",
                            )
                            continue
                        if not matched:
                            msg = f"'paths:' glob matches no files (stale?): {glob!r}"
                            issue("Low", "stale_glob", msg)

    if not body.strip():
        issue("Medium", "empty_body", "Body is empty after frontmatter — no rules defined")
        return findings

    fm_line_count = len(text.splitlines()) - len(body.splitlines())
    body_total = len(body.splitlines())
    buried: list[tuple[int, int, str]] = []
    headings: set[str] = set()
    anchors: list[tuple[int, str]] = []
    seen_lines: dict[str, int] = {}
    dupes: list[tuple[int, int, str]] = []
    # Match fences by their full opening run (``` closed only by a run of ``` at
    # least as long, ~~~ likewise) — a four-backtick opener is not closed by a
    # three-backtick line. A naive toggle left an unclosed fence "open" for the
    # rest of the file, silently disabling the hedged-language gate below it.
    fence = ""
    for body_lineno, line in enumerate(body.splitlines(), 1):
        lineno = fm_line_count + body_lineno
        stripped = line.strip()
        if fence:
            if md_fences.closes(stripped, fence):
                fence = ""
            continue
        opened = md_fences.opener(stripped)
        if opened:
            fence = opened
            continue
        # Position risk is judged on *section openers* only — a heading or a
        # bolded lead-in — never on every line. This repo's style guide requires
        # rules be unconditional, so "never" and "always" saturate ordinary
        # prose; scoring each occurrence inverts the signal and flags hardest the
        # files that follow the guide best. What the effect actually describes is
        # a titled rule an agent skims past, and a title is what this matches.
        depth = body_lineno / body_total
        if (
            body_total >= _POSITION_MIN_LINES
            and _POSITION_BAND[0] <= depth <= _POSITION_BAND[1]
            and _SECTION_OPENER_RE.match(stripped)
            and _CRITICAL_RE.search(stripped)
        ):
            buried.append((lineno, round(depth * 100), stripped[:70]))

        if stripped.startswith("#"):
            headings.add(_slug(stripped))
            continue
        if not stripped:
            continue

        for anchor in _ANCHOR_LINK_RE.findall(line):
            anchors.append((lineno, anchor))

        p = _PLACEHOLDER_RE.search(line)
        if p:
            issue(
                # Medium: a rule with an unfilled slot states a requirement
                # nobody can satisfy, but the slot may be deliberate prose about
                # placeholders — which is why it reports rather than blocks.
                "Medium",
                "placeholder",
                f"Line {lineno}: unfilled placeholder '{p.group(1)}' — "
                f"a rule with a blank in it cannot be followed",
            )

        d = _ISO_DATE_RE.search(line)
        if d:
            try:
                when = datetime.date(int(d.group(1)), int(d.group(2)), int(d.group(3)))
                age = (datetime.date.today() - when).days
            except ValueError:
                age = 0  # 2026-13-45 is not a date; leave it to a human
            if age > _STALE_DATE_DAYS:
                issue(
                    "Low",
                    "stale_date",
                    f"Line {lineno}: date {d.group(0)} is {age} days old — a standing "
                    f"rule that cites a date is either a decision record or a deadline",
                )

        # Exact repeats only. Near-duplicate detection needs similarity scoring,
        # which is a judgement call this gate deliberately does not make.
        if len(stripped) >= 30:
            first = seen_lines.get(stripped)
            if first is None:
                seen_lines[stripped] = lineno
            else:
                dupes.append((first, lineno, stripped[:60]))

        m = _HEDGED_RE.search(line)
        if m:
            snippet = line.strip()[:80]
            issue(
                # High, so it sets the exit code: unconditional phrasing is the
                # property this repo states most emphatically for its own rule
                # files, and a detector whose result never blocks is decoration.
                "High",
                "hedged_language",
                f"Line {lineno}: hedged '{m.group()}' — rules must be unconditional: \"{snippet}\"",
            )

        for ref in _REPO_PATH_RE.findall(line):
            if _looks_illustrative(ref):
                continue
            rel, base = _tracked(project_root)
            if ref in rel or ref.split("/")[-1] in base or (project_root / ref).exists():
                continue
            issue(
                # Low, like `stale_glob` above and for the same reason: a rule may
                # legitimately name a path this repo does not have, so a blocking
                # verdict would fail commits on a judgement call. It reports.
                "Low",
                "stale_path",
                f"Line {lineno}: '{ref}' does not exist under the project root",
            )

    for lineno, anchor in anchors:
        if anchor not in headings:
            issue(
                # Medium: a link into this file that lands nowhere. Deterministic
                # — the headings are right here — so it is graded above the
                # judgement-call checks, but still below the ones that stop a
                # rule loading at all.
                "Medium",
                "dead_anchor",
                f"Line {lineno}: link to '#{anchor}' matches no heading in this file",
            )

    for first, again, text in dupes:
        issue(
            "Low",
            "duplicate_line",
            f'Line {again} repeats line {first} verbatim: "{text}" — '
            f"a rule stated twice drifts when only one copy is edited",
        )

    if buried:
        where = "; ".join(f'line {ln} ({pct}%): "{txt}"' for ln, pct, txt in buried[:3])
        more = f" (+{len(buried) - 3} more)" if len(buried) > 3 else ""
        issue(
            "Low",
            "buried_directive",
            f"{len(buried)} unconditional directive(s) in the middle of a "
            f"{body_total}-line rule — {where}{more}. A rule file long enough to "
            "bury its own directive is a rule file to split.",
        )

    if fence:
        issue(
            "High",
            "unterminated_fence",
            "unterminated code fence — every ``` or ~~~ must be closed; an open "
            "fence silences the hedged-language check for the rest of the file",
        )

    return findings


def _unscannable(rules_dir: Path, exc: OSError, errors: list[tuple[Path, str]] | None) -> None:
    """Record a directory whose rules could not be read, for the gate to fail on.

    Both ways the walk can fail mean the same thing, so both report through here:
    `resolve()` raising, and `os.scandir` raising — the latter covering a
    `.claude/rules` that is a regular file (NotADirectoryError) as well as one
    the process may not read (PermissionError). In every case the rules under it
    went unread, and a report built from what remains is a narrowed scan. Left
    unrecorded it reads as "exists but is empty", which is a clean result.

    Warning and recording are separate jobs: the warning is for a human watching
    the run, the record is what makes `check` raise. A warning alone still lets
    CI exit 0 with rules unread.
    """
    reason = exc.strerror or type(exc).__name__
    print(f"[warn] cannot scan {rules_dir}: {reason}", file=sys.stderr)
    if errors is not None:
        errors.append((rules_dir, reason))


# Rule *directories* by harness. This tool audits somebody else's repository and
# which agent they run is not ours to assume: hardcoded to `.claude/rules`, it
# answered ".claude/rules/ not found" for every Cursor, Windsurf, Cline or
# Copilot project, taking `/nitpicker agent-rules` out of service for them
# entirely rather than auditing the rules they do have.
#
# The single-file forms (`.cursorrules`, `CLAUDE.md`, `.clinerules` as a file)
# belong to check-agent-instructions.py, which scores the always-loaded set.
# This tool is the per-file authority for whichever directory a project keeps.
_RULE_DIRS: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    (".claude/rules", (".md",), False),
    (".cursor/rules", (".mdc", ".md"), False),
    (".windsurf/rules", (".md",), False),
    (".github/instructions", (".md",), False),
    # Cline reads `.clinerules` as either a file or a directory. In its file form
    # it is the other tool's subject, so it is skipped here — scanning it would
    # raise NotADirectoryError and fail the gate on a valid Cline project.
    (".clinerules", (".md",), True),
)

# Derived, never restated: a second list would let the per-file extension check
# and the directory scan disagree, which is exactly how `.mdc` came to be
# discovered and then reported as a defect.
_RULE_SUFFIXES = frozenset(s for _, suffixes, _ in _RULE_DIRS for s in suffixes)


def _iter_rules(
    rules_dir: Path,
    seen: set[Path] | None = None,
    errors: list[tuple[Path, str]] | None = None,
    contain: Path | None = None,
    suffixes: tuple[str, ...] = (".md",),
) -> list[Path]:
    """Rule files under `rules_dir`, following symlinks without looping forever.

    Rules are commonly symlinked between projects, and a link pointing at an
    ancestor turns a plain walk into an infinite one. `seen` tracks resolved
    paths so each file is visited once.

    A dangling symlink is returned in the results rather than dropped, so
    `_check_file` reports it as the finding it is. `errors` is for something
    else — a directory the process cannot read, which narrows the gate silently
    and so is recorded for `main` to fail on rather than merely warn about.
    """
    if seen is None:
        seen = set()
    try:
        real = rules_dir.resolve()
    except OSError as e:
        _unscannable(rules_dir, e, errors)
        return []

    if contain is not None and not real.is_relative_to(contain):
        # Containment has to happen HERE, before os.scandir, not only in
        # `_check_file`. Checking per-file stops the contents leaking but still
        # enumerates the external directory first, so every filename in it comes
        # back in the report — and a link to `/` walks the whole disk to build
        # that list. Returning the link itself lets `_check_file` report it once
        # as `symlink_escapes_root`, so the refusal stays visible rather than
        # becoming a silently narrower scan.
        return [rules_dir]

    if real in seen:
        return []
    seen.add(real)

    results: list[Path] = []
    try:
        with os.scandir(rules_dir) as it:
            for entry in it:
                p = Path(entry.path)
                if entry.is_symlink() and not p.exists():
                    results.append(p)
                elif entry.is_dir(follow_symlinks=True):
                    results.extend(_iter_rules(p, seen, errors, contain, suffixes))
                elif entry.name.endswith(suffixes):
                    results.append(p)
    except OSError as e:
        _unscannable(rules_dir, e, errors)
    return sorted(results)


def _present_rule_dirs(project_root: Path) -> list[tuple[Path, tuple[str, ...]]]:
    """Every harness rules directory this project actually has, with its suffixes.

    Raises ValueError for a directory that is there but cannot be looked at.
    `Path.exists()` answers False in that case — it swallows EACCES along with
    every other OSError — which sent an unreadable rules directory down the
    missing-directory branch and out as a clean report at exit 0, with nothing
    scanned. `stat()` separates "not there" from "cannot look", and only the
    first of those is a clean result.
    """
    present: list[tuple[Path, tuple[str, ...]]] = []
    for rel, suffixes, may_be_file in _RULE_DIRS:
        d = project_root / rel
        try:
            d.stat()
        except FileNotFoundError:
            continue
        except OSError as e:
            raise ValueError(
                f"cannot stat {d}: {e.strerror or type(e).__name__} — rules left unread"
            ) from e
        # Only the ambiguous entry is allowed to be a regular file. Everywhere
        # else a non-directory is a real misconfiguration, and skipping it here
        # would turn that into a silently clean scan.
        if may_be_file and not d.is_dir():
            continue
        present.append((d, suffixes))
    return present


def check(
    project_root: Path, explicit: bool = True, contain: Path | None = None
) -> tuple[dict, bool]:
    """The rule-anatomy report for `project_root`, and whether it blocks; (report, blocking).

    Split out of `main` so the `np_check_rules_anatomy` MCP tool and the CLI run
    one implementation rather than two that drift apart.

    `explicit` distinguishes a caller that named a project root from the CLI's
    bare no-argument default. A named root with no `.claude/rules/` is a
    misconfiguration and raises; the default case returns an empty clean report,
    because a consumer repo with no rules directory is genuinely clean. The MCP
    tool always passes True — its `project_root` argument is always a deliberate
    choice, never a cwd fallback.

    Raises ValueError rather than exiting, for both the missing-directory and the
    unreadable-directory case. `sys.exit` inside the MCP server would unwind
    through the request loop and kill the process; the dispatcher renders a
    ValueError as an error result instead. An unreadable rules directory raises
    rather than returning a partial report, because a silently narrowed scan
    reported as a result reads exactly like a clean one.
    """
    empty_summary = {"total": 0, "ok": 0, "with_issues": 0, "error_count": 0}
    known = ", ".join(rel for rel, _, _ in _RULE_DIRS)

    present = _present_rule_dirs(project_root)

    if not present:
        if explicit:
            # The argument is a PROJECT ROOT, not a rules dir. Pointing it at
            # `.claude/rules/` itself yields `.claude/rules/.claude/rules` and
            # used to exit 0 — a silently green gate.
            raise ValueError(
                f"no rules directory under {project_root} (looked for {known}) — "
                f"argument must be a project root"
            )
        return {
            "rules_dirs": [],
            "exists": False,
            "message": f"no rules directory found (looked for {known})",
            "files": [],
            "summary": empty_summary,
        }, False

    scan_errors: list[tuple[Path, str]] = []
    # One `seen` set across every directory: a project that symlinks
    # `.cursor/rules` at `.claude/rules` to serve two agents from one set would
    # otherwise report each rule twice.
    seen: set[Path] = set()
    rule_files: list[Path] = []
    for d, suffixes in present:
        rule_files += _iter_rules(d, seen, scan_errors, contain, suffixes)
    rule_files.sort()

    if scan_errors:
        # An unscannable rule directory means the gate ran on an incomplete set;
        # fail rather than report exit 0 on a silently narrowed scan (including
        # the case where the top rules dir itself is unreadable and rule_files is
        # empty, and the case where it is a regular file rather than a directory).
        joined = ", ".join(f"{d} ({reason})" for d, reason in scan_errors)
        raise ValueError(f"cannot scan {joined} — rules left unread")

    if not rule_files:
        known_present = ", ".join(str(d) for d, _ in present)
        return {
            "rules_dirs": [str(d) for d, _ in present],
            "exists": True,
            "message": f"{known_present} exists but is empty",
            "files": [],
            "summary": empty_summary,
        }, False

    report: list[dict] = []
    has_blocking = False

    for path in rule_files:
        file_findings = _check_file(path, project_root, contain)
        try:
            rel = str(path.relative_to(project_root))
        except ValueError:
            rel = str(path)
        report.append({"file": rel, "findings": file_findings})
        if any(f["severity"] in ("High", "Critical") for f in file_findings):
            has_blocking = True

    total = len(report)
    with_issues = sum(1 for r in report if r["findings"])

    return {
        "rules_dirs": [str(d) for d, _ in present],
        "exists": True,
        "files": report,
        "summary": {
            "total": total,
            "ok": total - with_issues,
            "with_issues": with_issues,
            "error_count": sum(len(r["findings"]) for r in report),
        },
    }, has_blocking


def main() -> None:
    """CLI entry point: parse argv, print the report, exit per the outcome.

    Thin by design — `check` holds the logic so the MCP tool runs the same code.
    What lives only here is the CLI contract: `explicit` is true only when a root
    was actually named on the command line, which is the distinction that decides
    whether a missing `.claude/rules/` is a misconfiguration or a clean repo, and
    a blocking finding exits 1 so CI fails on it.
    """
    # --help is how an agent learns this script's interface
    # (https://agentskills.io/skill-creation/using-scripts). Checked before the
    # argument is read as a path, or `--help` resolves as a project root.
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__)
        return

    explicit = bool(sys.argv[1:])
    project_root = Path(sys.argv[1]).resolve() if explicit else Path.cwd()

    try:
        report, has_blocking = check(project_root, explicit)
    except ValueError as e:
        print(f"ERROR  {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(report, indent=2))
    sys.exit(1 if has_blocking else 0)


if __name__ == "__main__":
    main()
