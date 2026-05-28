# security-auditor

Runs all available security scanners, parses their output, deduplicates findings across tools, and writes a consolidated security findings report.

## When to Use

- "Security audit" / "run security scan" / "find vulnerabilities"
- "Check for secrets" / "scan dependencies" / "run security-auditor"
- Pre-release gate: confirm no critical CVEs or exposed secrets
- After adding dependencies or changing infrastructure configuration

**When NOT to use:**
- Logic bugs and code correctness (no scanner tooling involved) → use [adversarial-reviewer]
- Full repository audit across code, tests, docs, and config → use [nitpicker] in security mode, which invokes security-auditor and then extends the review

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Codebase, git history, dependency manifests (`package.json`, `Pipfile`, `go.mod`, etc.), infrastructure config (Terraform, Dockerfile, Kubernetes YAML) |
| **Writes** | `docs/audit/security-findings.md` |

## How to Invoke

```
/security-auditor
```

No arguments required. The skill probes for available tools before running any scan.

## Tool Detection

All tools are optional. The skill probes with `which <tool>` and only runs tools that are present.

| Tool | What it finds |
|------|--------------|
| `semgrep` / `opengrep` | SAST: code-level security bugs |
| `grype` | Dependency vulnerabilities (CVEs) |
| `trivy` | Dependencies, misconfigurations, secrets |
| `gitleaks` | Secrets committed to git history or working tree |
| `checkov` | IaC misconfigurations (Terraform, Dockerfile, Kubernetes, etc.) |
| `gosec` | Go-specific security issues |
| `snyk` | Dependency vulnerabilities (SCA) |
| `npm` / `yarn` / `pnpm` | Node.js dependency vulnerabilities via `audit` |

Missing tools are listed under "Not available" in the report header. Tools that are found but fail to run (e.g., broken environment) are listed under "Errored" with the error message — never silently skipped.

## Process

```
1.  Probe: run `which` for every tool in the table above
2.  Run each available tool with the flags defined in Tool Execution
3.  Capture stdout and stderr; apply tool-specific exit code rules
4.  Parse each tool's JSON output into normalized findings
5.  Deduplicate cross-tool findings:
      - Dependency CVE: match on vulnerability identifier + package name
      - Secret: match on file path + line (±2)
      - SAST / IaC: match on rule ID + file path
      List all source tools under Tool: on the deduplicated finding
6.  Assign severity using the Severity Mapping table
7.  If docs/audit/security-findings.md exists:
      Identify which tools ran successfully this pass.
      For OPEN findings whose detecting tool did NOT run: skip re-validation,
        leave Open, emit warning: "Re-validation skipped for N finding(s) from
        tools not run in this pass: <list>."
      For remaining OPEN findings: if still reported → leave Open;
        if no longer reported → move to Fixed (record date + pass number)
8.  Add new findings (assign next available ID — never reuse IDs)
9.  Write docs/audit/security-findings.md
10. Present summary: tool coverage, finding counts by severity, top 5 Critical/High
11. Ask: "Apply any available auto-fixes? (y/n)" — only if fixable findings exist
12. Ask: "Commit findings to git? (y/n)" — never commit silently
```

## Severity Mapping

Tool-reported severities are normalized to a common scale:

| Normalized | Tool equivalents |
|------------|-----------------|
| Critical | CRITICAL, critical, 9.0–10.0 CVSS |
| High | HIGH, high, 7.0–8.9 CVSS |
| Medium | MEDIUM, medium, 4.0–6.9 CVSS |
| Low | LOW, low, 0.1–3.9 CVSS |
| Advisory | INFO, informational, note |

## Findings Format

```
# Security Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Tool Coverage
- semgrep: Found (N findings)
- grype: Not available
- gitleaks: Found (N findings)
...

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- By severity: Critical: N | High: N | Medium: N | Low: N | Advisory: N

## Open Findings

### Critical

#### [SEC-NNN] Short title
Tool: <tool(s) that reported this finding>
Category: <dependency-vulnerability|sast|secret|iac-misconfiguration>
Area: path/to/file:line (or package@version)
CVE / Rule ID: <identifier if applicable>
Problem: <direct description>
Evidence: <redacted excerpt or rule match>
Impact: <why this matters>
Fix: <concrete remediation>
```

Finding ID format: `SEC-NNN` (zero-padded to 3 digits, e.g. `SEC-001`). IDs are assigned sequentially and never reused. **All secret values are redacted before writing to disk.**

## Rules

- No hedging — if a tool reports it, file it
- Silence means approval — anything not flagged is implicitly approved
- Deduplicate cross-tool findings using the match keys defined in Process step 5
- If a tool fails to parse (bad JSON, crash), record under "Errored" — never skip silently
- Never re-validate findings from tools that did not run in this pass

## Related Skills

- [nitpicker] — security mode invokes security-auditor, then extends with trust-boundary analysis
- [claude-rules-auditor] — reads `docs/audit/security-findings.md` to suggest security-related rules

---

[skill-source]: SKILL.md
[nitpicker]: ../nitpicker/README.md
[adversarial-reviewer]: ../adversarial-reviewer/README.md
[claude-rules-auditor]: ../claude-rules-auditor/README.md
