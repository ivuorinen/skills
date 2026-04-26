#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — validate and autofix docs/audit/*-findings.md structure and summary counts.

Enforces:
  - Single ## Fixed h2 (no ## Fixed — pass N variants)
  - Single ## Invalid h2 (same)
  - h3 sub-sections under Fixed/Invalid use ### Pass N — YYYY-MM-DD format
  - Summary counts match actual h4 finding entries per section
"""

import json
import os
import re
import sys
from pathlib import Path

_default = Path(__file__).parent.parent.parent
REPO_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.environ.get("REPO_ROOT", _default)))

H2_OPEN = re.compile(r"^## Open Findings\s*$", re.IGNORECASE)
H2_FIXED = re.compile(r"^## Fixed", re.IGNORECASE)
H2_INVALID = re.compile(r"^## Invalid", re.IGNORECASE)
H2_SUMMARY = re.compile(r"^## Summary\s*$", re.IGNORECASE)
H3_PASS = re.compile(r"^### Pass \d+ — \d{4}-\d{2}-\d{2}\s*$")
H4_FINDING = re.compile(r"^#### \[")
_DATE_HDR = re.compile(r"^(?:Last validated|Generated):\s*(\d{4}-\d{2}-\d{2})")
SUMMARY_RE = re.compile(
    r"([-\s]*)Total:\s*(\d+)\s*\|\s*Open:\s*(\d+)\s*\|\s*Fixed:\s*(\d+)\s*\|\s*Invalid:\s*(\d+)"
)


def is_findings_file(path: Path) -> bool:
    return path.name.endswith("-findings.md") and path.parent.name == "audit"


def parse_and_fix(text: str) -> tuple[str, list[str]]:
    """Parse findings file, fix structure and summary. Returns (fixed_text, messages)."""
    lines = text.splitlines()
    messages: list[str] = []

    # Classify each line into buckets
    preamble: list[str] = []
    summary_prefix = "- "
    summary_found = False
    summary_extra: list[str] = []
    open_lines: list[str] = []
    fixed_lines: list[str] = []
    invalid_lines: list[str] = []
    current: str = "preamble"
    multiple_fixed = False
    multiple_invalid = False

    prev_blank = True  # treat start-of-file as preceded by blank
    for line in lines:
        # Only recognise structural h2/h3 headers when preceded by a blank line.
        # This prevents Notes: text that starts with "## Fixed" from being
        # misidentified as a section boundary.
        is_blank = not line.strip()
        if prev_blank and H2_SUMMARY.match(line):
            current = "summary"
            prev_blank = is_blank
            continue  # header reconstructed later
        elif prev_blank and H2_OPEN.match(line):
            current = "open"
            open_lines.append(line)
            prev_blank = is_blank
            continue
        elif prev_blank and H2_FIXED.match(line):
            if current == "fixed":
                multiple_fixed = True
            current = "fixed"
            prev_blank = is_blank
            continue  # header reconstructed later
        elif prev_blank and H2_INVALID.match(line):
            if current == "invalid":
                multiple_invalid = True
            current = "invalid"
            prev_blank = is_blank
            continue  # header reconstructed later
        elif prev_blank and line.startswith("## ") and current not in ("preamble", "summary"):
            # Unknown h2 after known sections — treat as end of findings
            current = "other"

        if current == "preamble":
            # Capture the summary line from the preamble area
            m = SUMMARY_RE.search(line)
            if m:
                summary_prefix = m.group(1)
                summary_found = True
                prev_blank = is_blank
                continue  # will be reconstructed
            preamble.append(line)
        elif current == "summary":
            m = SUMMARY_RE.search(line)
            if m:
                summary_prefix = m.group(1)
                summary_found = True
            elif line.strip():
                summary_extra.append(line)
            # skip the Total: line — reconstructed from counts
        elif current == "open":
            open_lines.append(line)
        elif current == "fixed":
            # Strip non-conforming h3 sub-headers (only when preceded by blank)
            if prev_blank and line.startswith("### ") and not H3_PASS.match(line):
                renamed = _try_rename_pass_header(line)
                if renamed:
                    fixed_lines.append(renamed)
                    messages.append(f"  renamed h3: {line!r} → {renamed!r}")
                else:
                    messages.append(f"  removed non-conforming h3 under ## Fixed: {line!r}")
            else:
                fixed_lines.append(line)
        elif current == "invalid":
            if prev_blank and line.startswith("### ") and not H3_PASS.match(line):
                renamed = _try_rename_pass_header(line)
                if renamed:
                    invalid_lines.append(renamed)
                    messages.append(f"  renamed h3: {line!r} → {renamed!r}")
                else:
                    messages.append(f"  removed non-conforming h3 under ## Invalid: {line!r}")
            else:
                invalid_lines.append(line)
        prev_blank = is_blank

    if multiple_fixed:
        messages.append("  merged multiple ## Fixed h2 sections into one")
    if multiple_invalid:
        messages.append("  merged multiple ## Invalid h2 sections into one")

    # Derive a fallback date from preamble; prefer Last validated: over Generated:
    fallback_date = "unknown"
    for ln in preamble:
        m = _DATE_HDR.match(ln)
        if m:
            fallback_date = m.group(1)
            if ln.startswith("Last validated"):
                break  # most recent date — stop scanning

    # Wrap orphaned h4 findings (appearing before any h3) in a Pass 1 header
    fixed_lines = _ensure_pass_header(fixed_lines, messages, "Fixed", fallback_date)
    invalid_lines = _ensure_pass_header(invalid_lines, messages, "Invalid", fallback_date)

    # Count h4 findings per section
    open_count = sum(1 for ln in open_lines if H4_FINDING.match(ln))
    fixed_count = sum(1 for ln in fixed_lines if H4_FINDING.match(ln))
    invalid_count = sum(1 for ln in invalid_lines if H4_FINDING.match(ln))
    total = open_count + fixed_count + invalid_count

    if not summary_found:
        messages.append("  added missing Summary line")

    # Reconstruct file
    result: list[str] = []
    preamble = _strip_leading_trailing_blank(preamble)
    result.extend(preamble)
    result.append("")
    result.append("## Summary")
    summary_line = f"{summary_prefix}Total: {total} | Open: {open_count} | Fixed: {fixed_count}"
    summary_line += f" | Invalid: {invalid_count}"
    result.append(summary_line)
    result.extend(summary_extra)
    result.append("")

    # Open Findings
    if open_lines:
        result.extend(open_lines)
        if open_lines[-1].strip():
            result.append("")
    else:
        result.append("## Open Findings")
        result.append("")
        result.append("(none)")
        result.append("")

    # Fixed
    result.append("## Fixed")
    result.append("")
    body = _strip_leading_trailing_blank(fixed_lines)
    if body:
        result.extend(body)
        result.append("")
    else:
        result.append("(none)")
        result.append("")

    # Invalid
    result.append("## Invalid")
    result.append("")
    body = _strip_leading_trailing_blank(invalid_lines)
    if body:
        result.extend(body)
        result.append("")
    else:
        result.append("(none)")
        result.append("")

    new_text = "\n".join(result).rstrip() + "\n"
    return new_text, messages


def _strip_leading_trailing_blank(lines: list[str]) -> list[str]:
    while lines and not lines[0].strip():
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    return lines


_DATE_FROM_FIXED = re.compile(r"^Fixed:\s*(\d{4}-\d{2}-\d{2})")


def _ensure_pass_header(
    lines: list[str], messages: list[str], section: str, fallback_date: str = "unknown"
) -> list[str]:
    """If h4 findings appear before the first h3 in a Fixed/Invalid section, wrap them."""
    stripped = _strip_leading_trailing_blank(lines)
    if not stripped:
        return lines
    # Check if the first non-blank substantive line is a h4 (no h3 above it)
    first_h3 = next((i for i, ln in enumerate(stripped) if ln.startswith("### ")), None)
    first_h4 = next((i for i, ln in enumerate(stripped) if H4_FINDING.match(ln)), None)
    if first_h4 is None:
        return lines
    if first_h3 is not None and first_h3 < first_h4:
        return lines  # h3 comes first — structure is fine
    # Orphaned h4s found — determine date from first Fixed: line, then fall back
    date = fallback_date
    for ln in stripped[:first_h4 + 5]:
        m = _DATE_FROM_FIXED.match(ln)
        if m:
            date = m.group(1)
            break
    # Determine pass number: one less than the lowest existing Pass N
    existing = [int(m.group(1)) for ln in stripped if (m := re.match(r"^### Pass (\d+)", ln))]
    pass_n = (min(existing) - 1) if existing else 1
    if pass_n < 1:
        pass_n = 1
    header = f"### Pass {pass_n} — {date}"
    messages.append(f"  added missing pass header {header!r} under ## {section}")
    return [header, ""] + stripped


# Patterns like "### 2026-04-26, third pass" or "### 2026-04-24, first pass"
_ORDINAL_TO_N = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
                 "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
_OLD_H3 = re.compile(r"^### (\d{4}-\d{2}-\d{2}),?\s+(\w+)\s+pass\s*$", re.IGNORECASE)


def _try_rename_pass_header(line: str) -> str | None:
    """Attempt to rename a non-conforming h3 header to ### Pass N — YYYY-MM-DD."""
    m = _OLD_H3.match(line)
    if m:
        date, ordinal = m.group(1), m.group(2).lower()
        n = _ORDINAL_TO_N.get(ordinal)
        if n:
            return f"### Pass {n} — {date}"
    return None


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    file_path = data.get("file_path") or data.get("path") or ""
    raw = Path(file_path)
    path = raw if raw.is_absolute() else REPO_ROOT / raw

    if not is_findings_file(path):
        return

    if not path.exists():
        return

    original = path.read_text(encoding="utf-8")
    fixed, messages = parse_and_fix(original)

    if fixed != original:
        path.write_text(fixed, encoding="utf-8")
        print(f"  audit-findings hook: fixed {path.name}", flush=True)
        for msg in messages:
            print(msg, flush=True)
    else:
        # Verify summary counts are correct even without structural changes
        m = SUMMARY_RE.search(original)
        if m:
            total_d = int(m.group(2))
            open_d, fixed_d, invalid_d = int(m.group(3)), int(m.group(4)), int(m.group(5))
            lines = original.splitlines()
            # Quick count to verify
            cur = ""
            oc = fc = ic = 0
            for ln in lines:
                if H2_OPEN.match(ln):
                    cur = "open"
                elif H2_FIXED.match(ln):
                    cur = "fixed"
                elif H2_INVALID.match(ln):
                    cur = "invalid"
                elif ln.startswith("## "):
                    cur = ""
                if H4_FINDING.match(ln):
                    if cur == "open":
                        oc += 1
                    elif cur == "fixed":
                        fc += 1
                    elif cur == "invalid":
                        ic += 1
            tc = oc + fc + ic
            if (tc, oc, fc, ic) != (total_d, open_d, fixed_d, invalid_d):
                # Rewrite just the summary line
                prefix = m.group(1)
                new_summary = f"{prefix}Total: {tc} | Open: {oc} | Fixed: {fc} | Invalid: {ic}"
                fixed2 = SUMMARY_RE.sub(new_summary, original, count=1)
                path.write_text(fixed2, encoding="utf-8")
                print(
                    f"  audit-findings hook: corrected summary in {path.name} "
                    f"(was Total:{total_d}|Open:{open_d}|Fixed:{fixed_d}|Invalid:{invalid_d}, "
                    f"now Total:{tc}|Open:{oc}|Fixed:{fc}|Invalid:{ic})",
                    flush=True,
                )


if __name__ == "__main__":
    main()
