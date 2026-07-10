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

Exit codes: 0 = no High/Critical issues, 1 = High or Critical issues found.
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


def _parse_frontmatter(text: str) -> tuple[dict | None, str]:
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
        else:
            current_list = None

    return fm, "".join(lines[body_start:])


def _check_file(path: Path, project_root: Path) -> list[dict]:
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
                    elif not any(True for _ in project_root.glob(glob)):
                        msg = f"'paths:' glob matches no files (stale?): {glob!r}"
                        issue("Low", "stale_glob", msg)

    if not body.strip():
        issue("Medium", "empty_body", "Body is empty after frontmatter — no rules defined")
        return findings

    fm_line_count = len(text.splitlines()) - len(body.splitlines())
    in_fence = False
    for body_lineno, line in enumerate(body.splitlines(), 1):
        lineno = fm_line_count + body_lineno
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        if in_fence or not stripped or stripped.startswith("#"):
            continue
        m = _HEDGED_RE.search(line)
        if m:
            snippet = line.strip()[:80]
            issue(
                "Low",
                "hedged_language",
                f"Line {lineno}: hedged '{m.group()}' — rules must be unconditional: \"{snippet}\"",
            )

    return findings


def _iter_rules(rules_dir: Path, seen: set[Path] | None = None) -> list[Path]:
    if seen is None:
        seen = set()
    try:
        real = rules_dir.resolve()
    except OSError:
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
                    results.extend(_iter_rules(p, seen))
                elif entry.name.endswith(".md"):
                    results.append(p)
    except PermissionError:
        pass
    return sorted(results)


def main() -> None:
    project_root = Path(sys.argv[1]).resolve() if sys.argv[1:] else Path.cwd()
    rules_dir = project_root / ".claude" / "rules"

    if not rules_dir.exists():
        print(
            json.dumps(
                {
                    "rules_dir": str(rules_dir),
                    "exists": False,
                    "message": ".claude/rules/ not found",
                    "files": [],
                    "summary": {"total": 0, "ok": 0, "with_issues": 0, "error_count": 0},
                },
                indent=2,
            )
        )
        sys.exit(0)

    rule_files = _iter_rules(rules_dir)

    if not rule_files:
        print(
            json.dumps(
                {
                    "rules_dir": str(rules_dir),
                    "exists": True,
                    "message": ".claude/rules/ exists but is empty",
                    "files": [],
                    "summary": {"total": 0, "ok": 0, "with_issues": 0, "error_count": 0},
                },
                indent=2,
            )
        )
        sys.exit(0)

    report: list[dict] = []
    has_blocking = False

    for path in rule_files:
        findings = _check_file(path, project_root)
        try:
            rel = str(path.relative_to(project_root))
        except ValueError:
            rel = str(path)
        report.append({"file": rel, "findings": findings})
        if any(f["severity"] in ("High", "Critical") for f in findings):
            has_blocking = True

    total = len(report)
    with_issues = sum(1 for r in report if r["findings"])

    print(
        json.dumps(
            {
                "rules_dir": str(rules_dir),
                "exists": True,
                "files": report,
                "summary": {
                    "total": total,
                    "ok": total - with_issues,
                    "with_issues": with_issues,
                    "error_count": sum(len(r["findings"]) for r in report),
                },
            },
            indent=2,
        )
    )

    sys.exit(1 if has_blocking else 0)


if __name__ == "__main__":
    main()
