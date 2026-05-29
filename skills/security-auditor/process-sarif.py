#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Parse SARIF 2.1.0 files, deduplicate findings, and group by severity and tool.

Usage:
    process-sarif.py <sarif-file> [<sarif-file>...]

Reads one or more SARIF 2.1.0 files (e.g. from semgrep, grype, trivy, checkov, gitleaks),
deduplicates findings by (tool + rule_id + uri + start_line), normalizes severity
to the five-level scale, and outputs grouped JSON.

Output JSON:
    {
        "meta": {source_files, total_raw, unique, duplicates_removed, severity_counts},
        "by_severity": {"Critical": [...], "High": [...], "Medium": [...],
                       "Low": [...], "Advisory": [...]},
        "by_tool": {"toolName": [...]},
        "findings": [...]
    }

Each finding:
    {rule_id, rule_name, tool, severity, message, uri, start_line, start_column, cve_or_rule,
     fingerprint, help_uri, source_file}

Severity normalization:
    CVSS security-severity property → score ≥9.0=Critical, ≥7.0=High, ≥4.0=Medium, else Low
    SARIF level → error=High, warning=Medium, note/none=Low
    Tool-specific severity string → maps to normalized scale

Exit codes: 0 = success, 1 = parse/IO error, 2 = usage error.
"""

import hashlib
import json
import sys
from pathlib import Path

_SEVERITY_ORDER = ["Critical", "High", "Medium", "Low", "Advisory"]
_SEVERITY_RANK = {s: i for i, s in enumerate(_SEVERITY_ORDER)}

_TOOL_SEVERITY_MAP = {
    "CRITICAL": "Critical",
    "HIGH": "High",
    "ERROR": "High",
    "MEDIUM": "Medium",
    "MODERATE": "Medium",
    "WARNING": "Medium",
    "WARN": "Medium",
    "LOW": "Low",
    "NOTE": "Low",
    "INFO": "Low",
    "INFORMATIONAL": "Low",
    "ADVISORY": "Advisory",
    "HINT": "Advisory",
}


def _normalize_severity(
    level: str | None,
    security_severity: str | None,
    tool_severity: str | None,
) -> str:
    # Tool-specific severity string takes precedence when it maps cleanly
    if tool_severity:
        mapped = _TOOL_SEVERITY_MAP.get(tool_severity.upper())
        if mapped:
            return mapped

    # CVSS security-severity score
    if security_severity:
        try:
            score = float(security_severity)
            if score >= 9.0:
                return "Critical"
            if score >= 7.0:
                return "High"
            if score >= 4.0:
                return "Medium"
            return "Low"
        except ValueError:
            pass

    # SARIF level
    lvl = (level or "").lower()
    if lvl == "error":
        return "High"
    if lvl == "warning":
        return "Medium"
    return "Low"


def _extract_rules(run: dict) -> dict[str, dict]:
    rules: dict[str, dict] = {}
    sources = [run.get("tool", {}).get("driver", {})] + [
        ext for ext in run.get("tool", {}).get("extensions", [])
    ]
    for src in sources:
        for rule in src.get("rules", []):
            rid = rule.get("id", "")
            props = rule.get("properties") or {}
            rules[rid] = {
                "name": rule.get("name", rid),
                "short_description": (rule.get("shortDescription") or {}).get("text", ""),
                "help_uri": rule.get("helpUri", ""),
                "security_severity": props.get("security-severity"),
            }
    return rules


def _extract_findings(run: dict, source_file: str) -> list[dict]:
    tool_name = run.get("tool", {}).get("driver", {}).get("name", "unknown")
    rules = _extract_rules(run)
    findings: list[dict] = []

    for result in run.get("results", []):
        rule_id = result.get("ruleId", "")
        rule_meta = rules.get(rule_id, {})
        props = result.get("properties") or {}

        tool_severity = props.get("severity") or props.get("issue_severity")
        security_sev = rule_meta.get("security_severity") or props.get("security-severity")
        severity = _normalize_severity(result.get("level"), security_sev, tool_severity)

        # Message
        msg_raw = result.get("message", {})
        message = msg_raw.get("text", "") if isinstance(msg_raw, dict) else str(msg_raw)

        # Location
        uri, start_line, start_col = "", 0, 0
        locations = result.get("locations", [])
        if locations:
            phys = locations[0].get("physicalLocation", {})
            uri = (phys.get("artifactLocation") or {}).get("uri", "")
            region = phys.get("region") or {}
            start_line = region.get("startLine", 0)
            start_col = region.get("startColumn", 0)

        # CVE ID from taxa (grype/trivy pattern)
        cve_or_rule = rule_id
        for taxon in result.get("taxa", []):
            tid = taxon.get("id", "")
            if tid.startswith("CVE-"):
                cve_or_rule = tid
                break

        # Use message as location key when uri is absent so distinct location-less
        # findings (e.g. different vulnerable packages from grype) don't collapse.
        location_key = f"{uri}:{start_line}:{start_col}" if uri else message[:100]
        fingerprint = hashlib.sha256(f"{tool_name}|{rule_id}|{location_key}".encode()).hexdigest()[
            :16
        ]

        findings.append(
            {
                "rule_id": rule_id,
                "rule_name": rule_meta.get("name", rule_id),
                "tool": tool_name,
                "severity": severity,
                "message": message,
                "uri": uri,
                "start_line": start_line,
                "start_column": start_col,
                "cve_or_rule": cve_or_rule,
                "fingerprint": fingerprint,
                "help_uri": rule_meta.get("help_uri", ""),
                "source_file": source_file,
            }
        )

    return findings


def _parse_sarif(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[error] Cannot parse {path}: {e}", file=sys.stderr)
        sys.exit(1)

    version = data.get("version", "")
    if version not in ("2.1.0", "2.1"):
        print(f"[warn] {path.name}: SARIF version '{version}' not fully supported", file=sys.stderr)

    findings: list[dict] = []
    for run in data.get("runs", []):
        findings.extend(_extract_findings(run, path.name))
    return findings


def _deduplicate(findings: list[dict]) -> tuple[list[dict], int]:
    seen: dict[str, dict] = {}
    for f in findings:
        if f["fingerprint"] not in seen:
            seen[f["fingerprint"]] = f
    unique = list(seen.values())
    return unique, len(findings) - len(unique)


def main() -> None:
    if not sys.argv[1:]:
        print("Usage: process-sarif.py <sarif-file> [<sarif-file>...]", file=sys.stderr)
        sys.exit(2)

    all_findings: list[dict] = []
    sources: list[str] = []

    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.exists():
            print(f"[error] File not found: {path}", file=sys.stderr)
            sys.exit(1)
        all_findings.extend(_parse_sarif(path))
        sources.append(path.name)

    unique, removed = _deduplicate(all_findings)
    unique.sort(key=lambda f: (_SEVERITY_RANK.get(f["severity"], 99), f["uri"], f["start_line"]))

    by_severity: dict[str, list[dict]] = {level: [] for level in _SEVERITY_ORDER}
    by_tool: dict[str, list[dict]] = {}
    for f in unique:
        by_severity[f["severity"]].append(f)
        by_tool.setdefault(f["tool"], []).append(f)

    print(
        json.dumps(
            {
                "meta": {
                    "source_files": sources,
                    "total_raw": len(all_findings),
                    "unique": len(unique),
                    "duplicates_removed": removed,
                    "severity_counts": {
                        level: len(by_severity[level]) for level in _SEVERITY_ORDER
                    },
                },
                "by_severity": by_severity,
                "by_tool": by_tool,
                "findings": unique,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
