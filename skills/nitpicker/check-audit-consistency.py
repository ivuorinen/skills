#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Check docs/audit/*-findings.md files for structural consistency.

Usage:
    check-audit-consistency.py [<findings-file>...]

If no files given, scans docs/audit/ relative to cwd for *-findings.md files.

Checks:
    - Required h2 sections present: Summary, Open Findings, Fixed, Invalid
    - Summary counts match actual finding counts
    - Finding IDs are unique and never appear in both Open and Fixed/Invalid
    - Fixed/Invalid findings are under '### Pass N — YYYY-MM-DD' h3 headers
    - No header level jumps (e.g. h2 → h4 with no h3)

Exit codes: 0 = all OK, 1 = errors found.
"""

import re
import sys
from pathlib import Path

_SUMMARY_RE = re.compile(
    r"Total:\s*(\d+)\s*\|\s*Open:\s*(\d+)\s*\|\s*Fixed:\s*(\d+)\s*\|\s*Invalid:\s*(\d+)"
)
_FINDING_ID_RE = re.compile(r"^####\s+\[([A-Z]+-\d+)\]")
_PASS_HEADER_RE = re.compile(r"^###\s+Pass\s+\d+\s+—\s+\d{4}-\d{2}-\d{2}\s*$")


def check_file(path: Path, errors: list[str], warnings: list[str]) -> None:
    def err(msg: str) -> None:
        errors.append(f"  ERROR  {path}: {msg}")

    def warn(msg: str) -> None:
        warnings.append(f"  WARN   {path}: {msg}")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        err(f"cannot read: {e}")
        return

    lines = text.splitlines()

    # Required h2 sections
    h2_sections = set()
    in_fence = False
    for line in lines:
        stripped = line.rstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        if in_fence:
            continue
        m = re.match(r"^##\s+(.*)", line)
        if m:
            h2_sections.add(m.group(1).strip())
    for required in ("Summary", "Open Findings", "Fixed", "Invalid"):
        if required not in h2_sections:
            err(f"missing required section '## {required}'")

    # Parse Summary counts (skip fenced example blocks)
    summary_match = None
    in_fence = False
    for line in lines:
        stripped = line.rstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _SUMMARY_RE.search(line)
        if m:
            summary_match = m
            break

    # Walk sections and collect IDs
    ids_open: list[str] = []
    ids_fixed: list[str] = []
    ids_invalid: list[str] = []
    in_open = in_fixed = in_invalid = False
    under_pass_fixed = under_pass_invalid = False
    in_fence = False
    current_section = ""
    seen_h3: dict[str, set[str]] = {}

    for lineno, line in enumerate(lines, 1):
        stripped = line.rstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        if in_fence:
            continue
        h2 = re.match(r"^##\s+(.*)", line)
        if h2:
            name = h2.group(1).strip()
            current_section = name
            in_open = name == "Open Findings"
            in_fixed = name == "Fixed"
            in_invalid = name == "Invalid"
            under_pass_fixed = under_pass_invalid = False
            continue

        if re.match(r"^###[^#]", line):
            h3_title = line.lstrip("#").strip()
            bucket = seen_h3.setdefault(current_section, set())
            if h3_title in bucket:
                err(f"line {lineno}: duplicate '### {h3_title}' within '## {current_section}'")
            bucket.add(h3_title)
            if in_fixed:
                under_pass_fixed = bool(_PASS_HEADER_RE.match(line))
            elif in_invalid:
                under_pass_invalid = bool(_PASS_HEADER_RE.match(line))
            continue

        id_match = _FINDING_ID_RE.match(line)
        if re.match(r"^####\s+\[", line) and not id_match:
            err(f"line {lineno}: malformed finding ID (expected '[PREFIX-N]'): {stripped!r}")
            continue
        if not id_match:
            continue
        fid = id_match.group(1)

        if in_open:
            ids_open.append(fid)
        elif in_fixed:
            ids_fixed.append(fid)
            if not under_pass_fixed:
                err(f"line {lineno}: Fixed finding [{fid}] not under '### Pass N — YYYY-MM-DD'")
        elif in_invalid:
            ids_invalid.append(fid)
            if not under_pass_invalid:
                err(f"line {lineno}: Invalid finding [{fid}] not under '### Pass N — YYYY-MM-DD'")

    # Uniqueness check
    all_ids = ids_open + ids_fixed + ids_invalid
    seen: set[str] = set()
    for fid in all_ids:
        if fid in seen:
            err(f"duplicate ID [{fid}] appears more than once")
        seen.add(fid)

    # No ID can be in both Open and Fixed/Invalid
    open_set = set(ids_open)
    for fid in ids_fixed + ids_invalid:
        if fid in open_set:
            err(f"ID [{fid}] appears in both Open Findings and Fixed/Invalid")

    # Summary count verification
    if summary_match:
        c_total = int(summary_match.group(1))
        c_open = int(summary_match.group(2))
        c_fixed = int(summary_match.group(3))
        c_invalid = int(summary_match.group(4))
        a_open, a_fixed, a_invalid = len(ids_open), len(ids_fixed), len(ids_invalid)
        a_total = a_open + a_fixed + a_invalid
        if c_open != a_open:
            err(f"Summary Open: {c_open} but {a_open} Open findings found")
        if c_fixed != a_fixed:
            err(f"Summary Fixed: {c_fixed} but {a_fixed} Fixed findings found")
        if c_invalid != a_invalid:
            err(f"Summary Invalid: {c_invalid} but {a_invalid} Invalid findings found")
        if c_total != a_total:
            err(f"Summary Total: {c_total} but {a_total} total findings found")
    else:
        warn("no Summary line matching 'Total: N | Open: N | Fixed: N | Invalid: N'")

    # Header level progression — no jumps
    prev_level = 1
    in_fence = False
    for lineno, line in enumerate(lines, 1):
        stripped = line.rstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        if not in_fence and line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if level > prev_level + 1:
                err(f"line {lineno}: header jumps from h{prev_level} to h{level}")
            prev_level = level


def main() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    if sys.argv[1:]:
        targets = [Path(a) for a in sys.argv[1:]]
    else:
        audit_dir = Path("docs/audit")
        if not audit_dir.exists():
            print("OK  docs/audit/ not found; nothing to check.")
            sys.exit(0)
        targets = sorted(audit_dir.glob("*-findings.md"))

    if not targets:
        print("OK  no *-findings.md files found.")
        sys.exit(0)

    for t in targets:
        check_file(t, errors, warnings)

    for w in warnings:
        print(w)

    if errors:
        for e in errors:
            print(e)
        print(f"\n{len(errors)} error(s) in audit findings.")
        sys.exit(1)

    print(f"OK  {len(targets)} findings file(s) consistent.")


if __name__ == "__main__":
    main()
