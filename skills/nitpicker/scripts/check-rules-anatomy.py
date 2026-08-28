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

import json
import os
import re
import sys
from pathlib import Path

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
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


def _check_file(path: Path, project_root: Path) -> list[dict]:  # noqa: C901
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

    if path.suffix != ".md":
        issue("Low", "non_md_extension", f"Filename must have .md extension (got '{path.suffix}')")

    if not _KEBAB_RE.match(path.stem):
        issue("Low", "non_kebab_case", f"Filename stem must be kebab-case (got '{path.stem}')")

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
    # Match fences by their full opening run (``` closed only by a run of ``` at
    # least as long, ~~~ likewise) — a four-backtick opener is not closed by a
    # three-backtick line. A naive toggle left an unclosed fence "open" for the
    # rest of the file, silently disabling the hedged-language gate below it.
    fence = ""
    for body_lineno, line in enumerate(body.splitlines(), 1):
        lineno = fm_line_count + body_lineno
        stripped = line.strip()
        if fence:
            close = re.fullmatch(r"(`{3,}|~{3,})\s*", stripped)
            if close and close.group(1)[0] == fence[0] and len(close.group(1)) >= len(fence):
                fence = ""
            continue
        opener = re.match(r"(`{3,}|~{3,})", stripped)
        if opener:
            fence = opener.group(1)
            continue
        if not stripped or stripped.startswith("#"):
            continue
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


def _iter_rules(
    rules_dir: Path,
    seen: set[Path] | None = None,
    errors: list[tuple[Path, str]] | None = None,
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
                    results.extend(_iter_rules(p, seen, errors))
                elif entry.name.endswith(".md"):
                    results.append(p)
    except OSError as e:
        _unscannable(rules_dir, e, errors)
    return sorted(results)


def check(project_root: Path, explicit: bool = True) -> tuple[dict, bool]:
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
    rules_dir = project_root / ".claude" / "rules"
    empty_summary = {"total": 0, "ok": 0, "with_issues": 0, "error_count": 0}

    try:
        rules_dir.stat()
        present = True
    except FileNotFoundError:
        present = False
    except OSError as e:
        # `Path.exists()` answers False for a directory that IS there but cannot
        # be looked at — it swallows EACCES along with every other OSError — so
        # using it here sent an unreadable rules directory down the
        # missing-directory branch and out as a clean report at exit 0, with
        # nothing scanned. `stat()` separates "not there" from "cannot look",
        # and only the first of those is a clean result.
        raise ValueError(
            f"cannot stat {rules_dir}: {e.strerror or type(e).__name__} — rules left unread"
        ) from e

    if not present:
        if explicit:
            # The argument is a PROJECT ROOT, not a rules dir. Pointing it at
            # `.claude/rules/` itself yields `.claude/rules/.claude/rules` and
            # used to exit 0 — a silently green gate.
            raise ValueError(f"{rules_dir} not found — argument must be a project root")
        return {
            "rules_dir": str(rules_dir),
            "exists": False,
            "message": ".claude/rules/ not found",
            "files": [],
            "summary": empty_summary,
        }, False

    scan_errors: list[tuple[Path, str]] = []
    rule_files = _iter_rules(rules_dir, errors=scan_errors)

    if scan_errors:
        # An unscannable rule directory means the gate ran on an incomplete set;
        # fail rather than report exit 0 on a silently narrowed scan (including
        # the case where the top rules dir itself is unreadable and rule_files is
        # empty, and the case where it is a regular file rather than a directory).
        joined = ", ".join(f"{d} ({reason})" for d, reason in scan_errors)
        raise ValueError(f"cannot scan {joined} — rules left unread")

    if not rule_files:
        return {
            "rules_dir": str(rules_dir),
            "exists": True,
            "message": ".claude/rules/ exists but is empty",
            "files": [],
            "summary": empty_summary,
        }, False

    report: list[dict] = []
    has_blocking = False

    for path in rule_files:
        file_findings = _check_file(path, project_root)
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
        "rules_dir": str(rules_dir),
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
