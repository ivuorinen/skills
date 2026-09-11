#!/usr/bin/env python3
"""Render the findings store into formats other systems already ingest.

Ships inside the nitpicker skill: stdlib-only, Python 3.11+, no uv required.

The markdown store stays canonical — it is the human-reviewable artifact, and
these renderings are generated from it, never the other way round. Without them
nitpicker's output ends at its own directory: a repository already ingesting
SARIF from three scanners has to transcribe nitpicker's results by hand to see
them beside the rest.

Three formats, each for one consumer:

    sarif   a code-scanning interface (GitHub code scanning, an IDE, a
            dashboard). SARIF 2.1.0.
    json    another agent framework, or a script. The store's own row shape,
            stable and flat.
    junit   a CI test reporter. Open findings are failures, resolved findings
            are passes — which makes a CI run's finding count visible in the
            same panel as its test count.

Separate from `findings.py` so the store's read/write primitives stay one
concern and the renderers another; `findings.py export` is the entry point and
imports this.
"""

from __future__ import annotations

import json
import re

# B406 blacklists `xml.sax` because its *parsers* are vulnerable to entity
# expansion and external-entity attacks. Nothing here parses: `escape` and
# `quoteattr` are output encoders, and they are exactly what a hand-rolled
# replacement would get subtly wrong — `quoteattr` picks the quote character
# from the value's own content, which a naive `.replace('"', "&quot;")` does not.
#
# opengrep's `use-defused-xml` fires on the same import for the same reason and
# is wrong here twice over: `defusedxml` hardens parsers and offers no
# replacement for these two encoders, and it is a third-party package, which a
# shipped tool cannot take — `.claude/rules/use-uv-runner.md` holds everything
# under `skills/*/scripts/` to the standard library. Reported as a Codacy
# critical on PR #131; `CONFIG` in check-opengrep.py was widened in the same
# change so this marker is judged by the local gate rather than only in the UI.
# nosemgrep: use-defused-xml
from xml.sax.saxutils import escape, quoteattr  # nosec B406

FORMATS = ("sarif", "json", "junit")

# Nitpicker severity -> SARIF result level. SARIF has three actionable levels,
# so Critical and High both map to `error`: a code-scanning UI that showed High
# as a warning would sort a real defect below a lint nit.
SARIF_LEVEL = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "note",
    "advisory": "note",
}

# `area` is free text by design — it may be a file, a directory, a glob, or a
# subsystem name. This pulls a line number off the `path:123` spelling and
# leaves everything else alone rather than guessing.
_AREA_LINE = re.compile(r"^(?P<path>.+?):(?P<line>\d+)$")

# `location` is the coordinate a finding was filed with — `path:12` or
# `path:12-40` — recorded by `findings.py new --location` alongside a
# fingerprint of that source. Unlike `area` it is always a path and a line
# range, which is what a SARIF region needs.
_LOCATION_SPEC = re.compile(r"^(?P<path>.+?):(?P<start>\d+)(?:-(?P<end>\d+))?$")


class ExportError(Exception):
    """An unsupported format, reported at the CLI's usage exit code."""


# SARIF models `region.startLine` as a 32-bit integer. A larger value is either
# rejected outright or silently truncated by the ingesting tool, which lands the
# finding on an arbitrary line — so an implausible number is dropped here, where
# the loss is visible, rather than downstream where it is not.
_MAX_SARIF_LINE = 2**31 - 1


def _location(area: str) -> tuple[str, int | None]:
    """(uri, line) from an `area`, with line None unless the area names a usable one."""
    match = _AREA_LINE.match(area.strip())
    if not match:
        return area.strip(), None
    line = int(match.group("line"))
    return match.group("path"), line if 0 < line <= _MAX_SARIF_LINE else None


def _sarif_rule(row: dict) -> dict:
    """One SARIF rule per finding.

    Per-finding rather than per-category: a code-scanning UI groups by rule, and
    collapsing every `security` finding under one rule would show a repository
    with fourteen distinct defects as a single recurring alert.
    """
    return {
        "id": row["id"],
        "name": row["auditor"] or "nitpicker",
        "shortDescription": {"text": row["title"]},
        "defaultConfiguration": {"level": SARIF_LEVEL.get(row["severity"], "warning")},
        "properties": {
            "severity": row["severity"],
            "auditor": row["auditor"],
            "tags": [t for t in (row["auditor"],) if t],
        },
    }


def _region(location: str) -> tuple[str, int, int | None] | None:
    """(uri, startLine, endLine) from a `location`, or None when it yields no range.

    Preferred over `area` for a SARIF result because it is always a path plus a
    line range. `endLine` is None for a single-line location; SARIF treats a
    region with only `startLine` as that one line, so emitting a redundant
    `endLine` would say nothing extra.
    """
    match = _LOCATION_SPEC.match(location.strip())
    if not match:
        return None
    start = int(match.group("start"))
    end = int(match.group("end")) if match.group("end") else None
    if not 0 < start <= _MAX_SARIF_LINE:
        return None
    if end is not None and not start <= end <= _MAX_SARIF_LINE:
        end = None
    return match.group("path"), start, end


def _sarif_result(row: dict) -> dict:
    # `location` first: it is the coordinate the evidence was read at. `area`
    # is the fallback and is free text, so the URI it yields often names a
    # subsystem rather than a path — and a code-scanning consumer given an
    # artifact URI that does not resolve in the repository drops the result
    # entirely, which is worse than placing it imprecisely.
    placed = _region(row.get("location") or "")
    if placed:
        uri, start, end = placed
        region: dict | None = {"startLine": start}
        if end is not None:
            region["endLine"] = end
    else:
        uri, line = _location(row["area"])
        region = {"startLine": line} if line else None
    physical: dict = {"artifactLocation": {"uri": uri}}
    if region:
        physical["region"] = region
    return {
        "ruleId": row["id"],
        "level": SARIF_LEVEL.get(row["severity"], "warning"),
        "message": {"text": row["title"]},
        "locations": [{"physicalLocation": physical}],
        "properties": {"status": row["status"], "auditor": row["auditor"]},
    }


def to_sarif(rows: list[dict]) -> str:
    """SARIF 2.1.0 for the open findings.

    Resolved findings are excluded deliberately. SARIF describes the current
    state of the code; emitting a fixed finding would raise an alert on a defect
    that is gone, and a consumer has no way to tell it apart from a live one.
    """
    live = [r for r in rows if r["status"] == "open"]
    return json.dumps(
        {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "nitpicker",
                            "informationUri": "https://github.com/ivuorinen/skills",
                            "rules": [_sarif_rule(r) for r in live],
                        }
                    },
                    "results": [_sarif_result(r) for r in live],
                }
            ],
        },
        separators=(",", ":"),
    )


def to_json(rows: list[dict]) -> str:
    """The store's own row shape, plus a summary a consumer would otherwise recompute."""
    counts: dict[str, int] = {}
    for row in rows:
        if row["status"] == "open":
            counts[row["severity"]] = counts.get(row["severity"], 0) + 1
    return json.dumps(
        {
            "tool": "nitpicker",
            "summary": {
                "total": len(rows),
                "open": sum(1 for r in rows if r["status"] == "open"),
                "open_by_severity": counts,
            },
            "findings": rows,
        },
        separators=(",", ":"),
    )


def _xml_safe(text: str) -> str:
    """Drop the characters XML 1.0 cannot represent at all.

    `escape` and `quoteattr` encode `<`, `&` and quotes. They do nothing about
    the C0 control characters XML 1.0 forbids outright, and no escaping can:
    there is no representation for them in a conforming document. A finding
    title quotes source code, so a single control byte picked up from a file was
    enough to make the whole exported suite unparseable — and a CI reporter that
    cannot parse the suite drops every finding in it, not the one.

    Tab, newline and carriage return are the three C0 characters XML permits and
    are kept. Surrogates and the two noncharacters at the end of the BMP are
    dropped for the same reason.
    """
    return "".join(
        ch
        for ch in text
        if ch in "\t\n\r"
        or 0x20 <= ord(ch) <= 0xD7FF
        or 0xE000 <= ord(ch) <= 0xFFFD
        or ord(ch) >= 0x10000
    )


def _junit_case(row: dict) -> str:
    """One testcase: open findings fail, resolved findings pass.

    The mapping is the point. A CI panel then shows an unfixed Critical beside
    the failing tests rather than in a report nobody opens.
    """
    name = quoteattr(_xml_safe(f"{row['id']} {row['title']}"))
    classname = quoteattr(_xml_safe(f"nitpicker.{row['auditor'] or 'unknown'}"))
    if row["status"] != "open":
        return f"    <testcase classname={classname} name={name} />"
    message = quoteattr(_xml_safe(f"{row['severity']}: {row['title']}"))
    kind = quoteattr(_xml_safe(row["severity"] or "unknown"))
    area = escape(_xml_safe(row["area"]))
    return (
        f"    <testcase classname={classname} name={name}>\n"
        f"      <failure message={message} type={kind}>{area}</failure>\n"
        f"    </testcase>"
    )


def to_junit(rows: list[dict]) -> str:
    """A JUnit XML suite per auditor, so a CI reporter groups by lens."""
    by_auditor: dict[str, list[dict]] = {}
    for row in rows:
        by_auditor.setdefault(row["auditor"] or "unknown", []).append(row)
    suites = []
    for auditor, group in sorted(by_auditor.items()):
        failures = sum(1 for r in group if r["status"] == "open")
        cases = "\n".join(_junit_case(r) for r in group)
        suites.append(
            f'  <testsuite name={quoteattr(_xml_safe(auditor))} tests="{len(group)}" '
            f'failures="{failures}">\n{cases}\n  </testsuite>'
        )
    total = len(rows)
    failed = sum(1 for r in rows if r["status"] == "open")
    body = "\n".join(suites)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuites name="nitpicker" tests="{total}" failures="{failed}">\n'
        f"{body}\n</testsuites>"
    )


def export(rows: list[dict], fmt: str) -> str:
    """Render `rows` in `fmt`, or raise ExportError naming the supported set."""
    renderers = {"sarif": to_sarif, "json": to_json, "junit": to_junit}
    if fmt not in renderers:
        raise ExportError(f"--format must be one of {', '.join(FORMATS)}. Received: {fmt!r}")
    return renderers[fmt](rows)
