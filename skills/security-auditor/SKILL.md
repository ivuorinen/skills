---
name: security-auditor
description: Use when performing a security scan of the project using available local tools (semgrep, grype, trivy, gitleaks, checkov, gosec, snyk, npm audit), parsing their output, and generating a consolidated security findings report. Triggers: "security audit", "run security scan", "find vulnerabilities", "check for secrets", "scan dependencies", "run security-auditor".
---

# Security Auditor

## Overview

Automated, tool-driven security audit. Detects which security scanning tools are installed on the current machine, runs each one against the project, normalizes the output, and writes a consolidated findings report. No tool is assumed to be present — every tool is probed before use. All findings are graded Critical → Advisory and written to `docs/audit/security-findings.md`.

## When to Use

- Before a release to verify the project has no known vulnerabilities
- After adding new dependencies
- When asked to "run a security scan", "find vulnerabilities", "check for secrets", or "audit security"
- As part of a CI gate or pre-push check

**When NOT to use:** For general code quality issues, use `nitpicker`. For architecture boundary violations, use `arch-auditor`. For hostile code review, use `adversarial-reviewer`.

## Tool Detection

Before running any scan, probe for each tool with `which <tool>` or equivalent. Only run tools that are found. Skip missing tools silently — list them in the report header as "Not available".

| Tool | Command | What it finds |
|------|---------|---------------|
| semgrep | `which semgrep` | SAST: code-level security bugs |
| opengrep | `which opengrep` | SAST: code-level security bugs (semgrep fork) |
| grype | `which grype` | Dependency vulnerabilities (CVEs) |
| trivy | `which trivy` | Dependencies, misconfigurations, secrets |
| gitleaks | `which gitleaks` | Secrets committed to git history or working tree |
| checkov | `which checkov` | IaC misconfigurations (Terraform, Dockerfile, k8s, etc.) |
| gosec | `which gosec` | Go-specific security issues |
| snyk | `which snyk` | Dependency vulnerabilities (SCA) |
| npm | `which npm` | Node.js dependency vulnerabilities via `npm audit` |
| yarn | `which yarn` | Node.js dependency vulnerabilities via `yarn audit` |
| pnpm | `which pnpm` | Node.js dependency vulnerabilities via `pnpm audit` |

If a tool is found but fails to run (e.g., broken Python environment), record it under "Errored" in the report header with the error message. Always capture stderr separately — never redirect to `/dev/null` — so the error message is available for the report.

## Process

```
1. Probe: run `which` for every tool in the Tool Detection table
2. Run each available tool (see Tool Execution section for exact flags)
3. Capture stdout/stderr; for most tools, non-zero exit means possible findings — but apply
     tool-specific exit code rules defined in the Tool Execution section (e.g., snyk exit 2 = error)
4. Parse each tool's JSON output into normalized findings
5. Deduplicate findings from multiple tools into a single finding (list all sources under Tool:):
     - Dependency vulnerability: match on vulnerability identifier + package name (CVE, GHSA, RUSTSEC, OSV, or vendor advisory ID)
     - Secret: match on file path + line number (±2) — rule ID and redacted excerpt are not match components (rule ID names differ across tools)
     - SAST / IaC: match on rule ID + file path
6. Assign severity using the Severity Mapping table
7. If docs/audit/security-findings.md exists:
     Re-validate each OPEN finding using these match keys:
     - Dependency vulnerability: vulnerability identifier + package name (CVE, GHSA, RUSTSEC, OSV, or vendor advisory ID)
     - SAST / gosec: rule ID + file path (ignore line number drift of ±10 lines)
     - Secret: file path + line number (±2) — do NOT use rule ID or redacted excerpt (rule IDs differ across tools; re-redacting inconsistently would prevent matching)
     - IaC misconfiguration: check ID + file path
     If current scan still reports a match → leave as Open
     If current scan no longer reports a match → move to Fixed (record date and pass number)
     If user marks as false positive → move to Invalid (record reason and pass number)
8. Add new findings (assign next available ID — never reuse IDs)
9. Write docs/audit/security-findings.md
10. Present summary: tool coverage, finding counts by severity, top 5 critical/high findings
11. Ask: "Apply any available auto-fixes? (y/n)" — only offer if fixable findings exist
12. Ask: "Commit findings to git? (y/n)" — never commit silently
```

## Tool Execution

Run each tool with JSON output using the capture form below. Always capture stdout into a variable and stderr into a temp file so both are available for error detection. Never discard either stream.

Before running any tool, create a per-run temp directory and clean it up after writing the report:
```bash
_sa_tmp=$(mktemp -d)   # e.g. /tmp/security-auditor.XXXXXX
# ... run all tools, writing stderr to $_sa_tmp/<tool>-err.txt ...
rm -rf "$_sa_tmp"       # cleanup after docs/audit/security-findings.md is written
```

Capture pattern (use for every tool):
```bash
tool_out=$(command 2>"$_sa_tmp/tool-err.txt")
tool_exit=$?
# tool_out is empty → record as Errored (regardless of exit code)
# tool_out is not valid JSON → record as Errored (regardless of exit code)
#   Exception: yarn audit outputs NDJSON — use "empty output" as the only error condition for yarn
# Otherwise → parse tool_out; non-zero exit with valid output means findings were found, not a crash
```

### semgrep / opengrep

```bash
semgrep_out=$(semgrep --json --config=auto --quiet . 2>$_sa_tmp/semgrep-err.txt)
semgrep_exit=$?
```

If output is empty or not valid JSON (regardless of exit code): record as "Errored: $(cat $_sa_tmp/semgrep-err.txt | head -3)".

Parse `$semgrep_out`: `.results[]` → each has `.check_id`, `.path`, `.start.line`, `.extra.severity`, `.extra.message`

### grype

**Precondition:** Check for a supported manifest before running. Look for `go.sum`, `package-lock.json`, `requirements.txt`, `Gemfile.lock`, `Cargo.lock`, `composer.lock`, `yarn.lock`, `pnpm-lock.yaml`. If none found, record grype as "Not applicable (no supported manifest)" and skip.

```bash
grype_out=$(grype dir:. --output json 2>$_sa_tmp/grype-err.txt)
grype_exit=$?
```

If output is empty or not valid JSON (regardless of exit code): record as "Errored: $(cat $_sa_tmp/grype-err.txt | head -3)".

Parse `$grype_out`: `.matches[]` → each has `.vulnerability.id`, `.vulnerability.severity`, `.vulnerability.description`, `.artifact.name`, `.artifact.version`

### trivy

```bash
trivy_out=$(trivy fs . --format json --quiet 2>$_sa_tmp/trivy-err.txt)
trivy_exit=$?
```

If output is empty or not valid JSON (regardless of exit code): record as "Errored: $(cat $_sa_tmp/trivy-err.txt | head -3)".

Parse `$trivy_out`: `.Results[].Vulnerabilities[]` → each has `.VulnerabilityID`, `.Severity`, `.Title`, `.PkgName`, `.InstalledVersion`, `.FixedVersion`

Also parse: `.Results[].Misconfigurations[]` for IaC issues and `.Results[].Secrets[]` for secrets.

### gitleaks

```bash
gitleaks_out=$(gitleaks detect --source . --report-format json --exit-code 0 2>$_sa_tmp/gitleaks-err.txt)
gitleaks_exit=$?
```

If output is empty or not valid JSON (regardless of exit code): record as "Errored: $(cat $_sa_tmp/gitleaks-err.txt | head -3)". Note: gitleaks uses `--exit-code 0`, so a non-zero exit always indicates a genuine crash, not "found secrets". `null` output (no secrets found) is valid JSON — do not treat it as an error.

Parse `$gitleaks_out`: gitleaks outputs `null` (not `[]`) when no secrets are found — treat `null` as an empty findings array. Otherwise: `.[].RuleID`, `.[].Description`, `.[].File`, `.[].StartLine`, `.[].Commit`, `.[].Secret` (redact actual secret value in report).

### checkov

```bash
checkov_out=$(checkov -d . --output json --quiet 2>$_sa_tmp/checkov-err.txt)
checkov_exit=$?
```

If output is empty or not valid JSON (regardless of exit code): record as "Errored: $(cat $_sa_tmp/checkov-err.txt | head -3)".

Parse `$checkov_out`: output may be a JSON object (single framework) or a JSON array (multiple frameworks). Normalize before parsing:
- If top-level is an array: collect `.results.failed_checks[]` from each element
- If top-level is an object: use `.results.failed_checks[]` directly

Each failed check has `.check_id`, `.check_result.result`, `.resource`, `.file_path`, `.file_line_range`, `.check.name`

### gosec

**Precondition:** Only run if the project contains Go source files. Check with `find . -name "*.go" -not -path "*/vendor/*" | head -1`. If no .go files found, record gosec as "Not applicable (no Go source files)" and skip.

```bash
gosec_out=$(gosec -fmt json ./... 2>$_sa_tmp/gosec-err.txt)
gosec_exit=$?
```

If output is empty or not valid JSON (regardless of exit code): record as "Errored: $(cat $_sa_tmp/gosec-err.txt | head -3)".

Parse `$gosec_out`: `.issues[]` → each has `.rule_id`, `.details`, `.severity`, `.confidence`, `.file`, `.line`

### snyk

Snyk exits 0 (clean), 1 (vulnerabilities found OR unsupported project), or 2 (auth/network failure). Check for an `.error` field in the JSON before parsing vulnerabilities — its presence indicates failure regardless of exit code.

```bash
snyk_out=$(snyk test --json 2>$_sa_tmp/snyk-err.txt)
snyk_exit=$?
```

- `snyk_exit == 2`: record as "Errored: $(cat $_sa_tmp/snyk-err.txt | head -1)" (common cause: `snyk auth` not run)
- `snyk_exit == 0 or 1` AND `$snyk_out` contains `.error` field: record as "Errored: {.error value}"
- `snyk_exit == 0 or 1` AND no `.error` field: parse normally

Parse `$snyk_out`: snyk outputs a single object for single-project repos and a JSON array for monorepos. Normalize before parsing: if top-level is an array, union `.vulnerabilities[]` from each element; if top-level is an object, use `.vulnerabilities[]` directly. Each entry has `.id`, `.title`, `.severity`, `.packageName`, `.version`, `.description`, `.fixedIn`.

### npm / yarn / pnpm audit

**Precondition:** Requires both a lockfile and the corresponding binary. Determine which package manager applies:
- `package-lock.json` or `npm-shrinkwrap.json` present AND `which npm` succeeds → use npm
- `yarn.lock` present (no npm lockfile) AND `which yarn` succeeds → use yarn
- `pnpm-lock.yaml` present AND `which pnpm` succeeds → use pnpm
- Lockfile present but binary absent → record as "Not available (lockfile found but binary missing)"
- No lockfile present → record as "Not applicable (no lockfile)" and skip

**npm:**
```bash
npm_out=$(npm audit --json 2>$_sa_tmp/npm-err.txt)
npm_exit=$?
```
If output is empty or not valid JSON (regardless of exit code): record as "Errored: $(cat $_sa_tmp/npm-err.txt | head -3)".

Parse `$npm_out`: `.vulnerabilities` (object, keys are package names) → each has `.severity`, `.via[]`, `.effects[]`, `.fixAvailable`. Note: `.fixAvailable` may be `false`, `true`, or an object `{name, version, isSemVerMajor}` — when it is an object, use `.fixAvailable.version` as the fix version.

**yarn:**
```bash
yarn_out=$(yarn audit --json 2>$_sa_tmp/yarn-err.txt)
yarn_exit=$?
```
Note: yarn audit outputs NDJSON (not single-document JSON), so the generic "invalid JSON → Errored" check does NOT apply. For yarn, record as Errored only if `$yarn_out` is empty. Non-zero exit with non-empty output is normal when vulnerabilities are found.

Parse `$yarn_out` as NDJSON (one JSON object per line). Filter lines where `.type == "auditAdvisory"` and read `.data.advisory.{severity, title, module_name, patched_versions, overview}` from each.

**pnpm:**
```bash
pnpm_out=$(pnpm audit --json 2>$_sa_tmp/pnpm-err.txt)
pnpm_exit=$?
```
If output is empty or not valid JSON (regardless of exit code): record as "Errored: $(cat $_sa_tmp/pnpm-err.txt | head -3)".

Parse `$pnpm_out`: `.advisories` (object, keyed by advisory ID) → each has `.severity`, `.title`, `.module_name`, `.patched_versions`, `.overview`.

## Severity Mapping

Normalize all tool-specific severities to the standard five levels:

| Tool severity | Normalized |
|---------------|-----------|
| critical / CRITICAL | Critical |
| high / HIGH / error | High |
| medium / MEDIUM / warning / WARN | Medium |
| low / LOW / note / INFO | Low |
| informational / advisory / hint | Advisory |

For gitleaks: all secrets are **Critical** unless the matched rule is tagged `allowlist`.
For semgrep/opengrep: use `.extra.severity`; treat `ERROR` as High, `WARNING` as Medium, `INFO` as Low.
For checkov: use the check's severity metadata when present — `critical` → Critical, `high` → High, `medium` → Medium, `low` → Low. If no severity metadata is present, default to Medium.

## Findings Format

Open Findings is a flat, current-state view — no pass headers. Fixed and Invalid group their entries by the pass in which they were resolved, using `### Pass N — YYYY-MM-DD` h3 headers. Each new run appends a new pass group to Fixed and Invalid; it never overwrites them.

```
# Security Audit Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD
Pass: N

## Tool Coverage
- Available: <comma-separated list>
- Not available: <comma-separated list>
- Errored: <tool>: <error message>

## Summary
Total: N | Open: N | Fixed: N | Invalid: N
Critical: N | High: N | Medium: N | Low: N | Advisory: N

## Open Findings

### Critical

#### [ID] Short title
Category: <dependency-vulnerability|secret|sast|misconfiguration|supply-chain>
Tool: <tool that found it>
Source: <file path or package name>
CVE/Rule: <CVE-YYYY-NNNNN or rule ID>
Problem: <direct description — what is wrong>
Evidence: <exact package version, file:line, or commit SHA>
Impact: <why this matters>
Fix: <concrete remediation — upgrade command, config change, or code fix>

### High
[same structure]

### Medium
[same structure]

### Low
[same structure]

### Advisory
[same structure]

## Fixed

### Pass N — YYYY-MM-DD

#### [ID] Short title
Notes: <what changed and which tool no longer reports it>

## Invalid

### Pass N — YYYY-MM-DD

#### [ID] Short title
Notes: <why this finding was a false positive>
```

Finding ID format: `SEC-NNN` (zero-padded to 3 digits, e.g. `SEC-001`). Assign sequentially from the highest existing ID in the file, or start at `SEC-001` if no findings exist yet. IDs are permanent — never reassign or reuse them even after a finding is moved to Fixed or Invalid.

Pass number rules:
- Pass number is tracked in the file header as `Pass: N` (1-based); increment it on every run
- If the file does not exist yet (first run), start at Pass 1
- If the file exists, read the current `Pass: N` header value and increment by 1 for this run
- Each new run appends a new `### Pass N — YYYY-MM-DD` group to Fixed and Invalid
- If nothing was fixed or invalidated in a pass, omit that pass group from the section
- Open Findings is always the full current state — no pass headers ever appear there

**Secrets in findings:** Never print the actual secret value. Record `File`, `Line`, `Rule`, and a redacted excerpt. Redaction format: keep the first 4 and last 4 characters of the secret value and replace everything in between with `***`. Example: `AKIAIOSFODNN7EXAMPLE` → `AKIA***MPLE`. If the value is 8 characters or fewer, replace entirely with `[REDACTED]`.

## Fix Strategy

| Finding type | Auto-fixable | Action |
|--------------|-------------|--------|
| Dependency vulnerability with known fix version | Yes, after asking | Run package manager upgrade command |
| Secret in working tree (not committed) | Yes, after asking | Remove from file, add to `.gitignore` |
| Secret in git history | No — requires `git filter-repo` or BFG; instruct user | Document exact command |
| IaC misconfiguration | Sometimes — checkov `--fix` flag | Ask before applying |
| SAST finding | No — requires code change | Provide exact fix in the finding |
| Gosec finding | No — requires code change | Provide exact fix in the finding |

Never apply fixes without user confirmation. Never commit anything silently.

## Rules

- No compliments
- No hedging — if a tool reports it, file it
- Silence = approval — if something is not flagged, that IS your approval
- Redact all secret values before writing to disk
- Deduplicate cross-tool findings using the per-category match keys defined in Process step 5 — list all source tools under `Tool:`
- Assign IDs sequentially; never reuse a finding ID once assigned
- If a tool fails to parse (bad JSON, crash), record under "Errored" in Tool Coverage — do not skip silently

## Common Mistakes

**Running tools without checking availability first:** Always probe with `which` before executing. A missing tool must be recorded as "Not available", not treated as an error.

**Printing raw JSON output:** Parse it — never dump hundreds of lines of JSON at the user.

**Including the actual secret value in the report:** Redact. Always. A findings file is often committed to git.

**Treating a non-zero exit code as a fatal error:** Most security tools exit non-zero when they find issues. That is expected behavior, not a crash.

**Deduplication by title instead of ID:** Match on CVE ID or rule ID, not on description strings, which differ across tools.

**Offering fixes for secrets in git history without warning:** Filter-repo operations are destructive and require force-push. Always warn before suggesting them.
