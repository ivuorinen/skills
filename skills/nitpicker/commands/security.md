# /nitpicker security — Security Scan

Automated, tool-driven security audit: probe which security scanners are installed, run each one, normalize and deduplicate the output, and file consolidated findings. No tool is assumed present — every tool is probed before use.

## When to use

- Before a release to verify the project has no known vulnerabilities
- After adding new dependencies or changing infrastructure configuration
- When asked to "run a security scan", "find vulnerabilities", "check for secrets", "scan dependencies", or "audit security"
- As part of a CI gate or pre-push check

Not for: general code quality (`/nitpicker audit`), architecture boundary violations (`/nitpicker arch`), or hostile logic review (`/nitpicker review`).

## Tool detection

Before running any scan, probe for each tool with `which <tool>`. Only run tools that are found. Skip missing tools without attempting to execute them, and list them in the run summary under Tool Coverage as "Not available".

| Tool | What it finds |
| --- | --- |
| semgrep | SAST: code-level security bugs |
| opengrep | SAST: code-level security bugs (semgrep fork) |
| grype | Dependency vulnerabilities (CVEs) |
| trivy | Dependencies, misconfigurations, secrets |
| gitleaks | Secrets committed to git history or working tree |
| checkov | IaC misconfigurations (Terraform, Dockerfile, k8s, etc.) |
| gosec | Go-specific security issues |
| snyk | Dependency vulnerabilities (SCA) |
| npm / yarn / pnpm | Node.js dependency vulnerabilities via `audit` |

If a tool is found but fails to run (e.g., broken Python environment), record it under "Errored" in Tool Coverage with the error message. Always capture stderr separately — never redirect to `/dev/null`.

## Process

1. Probe: run `which` for every tool in the table above.
2. Run each available tool with the exact flags in Tool Execution below.
3. Capture stdout/stderr; apply tool-specific exit-code rules (non-zero usually means findings, not a crash — see per-tool notes).
4. Parse each tool's JSON output into normalized findings.
5. Deduplicate findings from multiple tools into a single finding (name all source tools in its Evidence):
   - Dependency vulnerability: match on vulnerability identifier + package name (CVE, GHSA, RUSTSEC, OSV, or vendor advisory ID)
   - Secret: match on file path + line number (±2) — rule ID and redacted excerpt are not match components (rule IDs differ across tools)
   - SAST / IaC: match on rule ID + file path
6. Assign severity using the Severity Mapping table below.
7. Re-validate open findings per `_conventions.md`, with this override: identify which tools ran successfully this pass (probed found AND did not error). For any open finding whose detecting tool did not run this pass, skip re-validation — leave it open and emit: "Re-validation skipped for N finding(s) from tools not run in this pass: <list>." Re-validate the rest using the match keys from step 5 (for SAST/gosec, ignore line-number drift of ±10).
8. File new findings via the store protocol in `_conventions.md`, using `--auditor security` and `--category security`. Fold the domain fields into the finding body: Problem states what is wrong and the finding class (dependency-vulnerability, secret, sast, misconfiguration, supply-chain); Evidence carries the detecting tool(s), the CVE/rule ID, and the exact package version, file:line, or commit SHA; Impact states why it matters; Fix is the concrete remediation (upgrade command, config change, or code fix).
9. Present the summary: tool coverage (Available / Not available / Not applicable / Errored), finding counts by severity, top 5 Critical/High findings.
10. Offer fixes per the Fix Strategy table and the `_conventions.md` prompts.

## Tool execution

Run each tool with JSON output using the capture form below. Always capture stdout into a variable and stderr into a temp file so both are available for error detection. Never discard either stream.

Create a per-run temp directory first and clean it up after findings are filed:

```bash
_sa_tmp=$(mktemp -d)
# ... run all tools, writing stderr to $_sa_tmp/<tool>-err.txt ...
rm -rf "$_sa_tmp"
```

Capture pattern (every tool):

```bash
tool_out=$(command 2>"$_sa_tmp/tool-err.txt")
tool_exit=$?
# tool_out empty → record as Errored (regardless of exit code)
# tool_out not valid JSON → record as Errored (regardless of exit code)
#   Exception: yarn audit outputs NDJSON — for yarn, "empty output" is the only error condition
# Otherwise → parse; non-zero exit with valid output means findings, not a crash
```

When any tool errors, record "Errored: $(head -3 "$_sa_tmp/<tool>-err.txt")" in Tool Coverage.

### semgrep / opengrep

```bash
semgrep_out=$(semgrep --json --config=auto --quiet . 2>"$_sa_tmp/semgrep-err.txt")
```

Parse `.results[]` → `.check_id`, `.path`, `.start.line`, `.extra.severity`, `.extra.message`.

### grype

Precondition: a supported manifest exists (`go.sum`, `package-lock.json`, `requirements.txt`, `Gemfile.lock`, `Cargo.lock`, `composer.lock`, `yarn.lock`, `pnpm-lock.yaml`). None found → record "Not applicable (no supported manifest)" and skip.

```bash
grype_out=$(grype dir:. --output json 2>"$_sa_tmp/grype-err.txt")
```

Parse `.matches[]` → `.vulnerability.id`, `.vulnerability.severity`, `.vulnerability.description`, `.artifact.name`, `.artifact.version`.

### trivy

```bash
trivy_out=$(trivy fs . --format json --quiet 2>"$_sa_tmp/trivy-err.txt")
```

Parse `.Results[].Vulnerabilities[]` → `.VulnerabilityID`, `.Severity`, `.Title`, `.PkgName`, `.InstalledVersion`, `.FixedVersion`. Also parse `.Results[].Misconfigurations[]` (IaC) and `.Results[].Secrets[]`.

### gitleaks

```bash
gitleaks_out=$(gitleaks detect --source . --report-format json --exit-code 0 2>"$_sa_tmp/gitleaks-err.txt")
```

With `--exit-code 0`, non-zero exit always means a genuine crash, not "found secrets". gitleaks outputs `null` (not `[]`) when no secrets are found — `null` is valid JSON, treat it as an empty findings array, never as an error. Otherwise parse `.[].RuleID`, `.[].Description`, `.[].File`, `.[].StartLine`, `.[].Commit`, `.[].Secret` (redact the secret value — see Redaction).

### checkov

```bash
checkov_out=$(checkov -d . --output json --quiet 2>"$_sa_tmp/checkov-err.txt")
```

Output may be a JSON object (single framework) or a JSON array (multiple). Normalize: array → collect `.results.failed_checks[]` from each element; object → use `.results.failed_checks[]` directly. Each failed check has `.check_id`, `.check_result.result`, `.resource`, `.file_path`, `.file_line_range`, `.check.name`.

### gosec

Precondition: Go source exists (`find . -name "*.go" -not -path "*/vendor/*" | head -1`). None → record "Not applicable (no Go source files)" and skip.

```bash
gosec_out=$(gosec -fmt json ./... 2>"$_sa_tmp/gosec-err.txt")
```

Parse `.issues[]` → `.rule_id`, `.details`, `.severity`, `.confidence`, `.file`, `.line`.

### snyk

Snyk exits 0 (clean), 1 (vulnerabilities found OR unsupported project), or 2 (auth/network failure). Check for an `.error` field in the JSON before parsing — its presence means failure regardless of exit code.

```bash
snyk_out=$(snyk test --json 2>"$_sa_tmp/snyk-err.txt")
```

- exit 2 → "Errored: $(head -1 "$_sa_tmp/snyk-err.txt")" (common cause: `snyk auth` not run)
- exit 0/1 with `.error` field → "Errored: {.error value}"
- exit 0/1 without `.error` → parse normally

Output is a single object for single-project repos, a JSON array for monorepos — normalize by unioning `.vulnerabilities[]`. Each entry has `.id`, `.title`, `.severity`, `.packageName`, `.version`, `.description`, `.fixedIn`.

### npm / yarn / pnpm audit

Precondition — determine which package manager applies:

- `package-lock.json` or `npm-shrinkwrap.json` present AND `which npm` succeeds → npm
- `yarn.lock` present (no npm lockfile) AND `which yarn` succeeds → yarn
- `pnpm-lock.yaml` present AND `which pnpm` succeeds → pnpm
- Lockfile present, binary absent → "Not available (lockfile found but binary missing)"
- No lockfile → "Not applicable (no lockfile)" and skip

```bash
npm_out=$(npm audit --json 2>"$_sa_tmp/npm-err.txt")
```

Parse `.vulnerabilities` (object keyed by package name) → `.severity`, `.via[]`, `.effects[]`, `.fixAvailable`. `.fixAvailable` may be `false`, `true`, or an object `{name, version, isSemVerMajor}` — when an object, use `.fixAvailable.version` as the fix version.

```bash
yarn_out=$(yarn audit --json 2>"$_sa_tmp/yarn-err.txt")
```

yarn outputs NDJSON — parse one JSON object per line, filter `.type == "auditAdvisory"`, read `.data.advisory.{severity, title, module_name, patched_versions, overview}`. Errored only if output is empty; non-zero exit with non-empty output is normal.

```bash
pnpm_out=$(pnpm audit --json 2>"$_sa_tmp/pnpm-err.txt")
```

Parse `.advisories` (object keyed by advisory ID) → `.severity`, `.title`, `.module_name`, `.patched_versions`, `.overview`.

## SARIF consolidation

`scripts/process-sarif.py` (bundled with this skill) parses SARIF 2.1.0 output, deduplicates findings, and groups by severity and tool. Stdlib-only — invoke with plain `python3`, never uv:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/process-sarif.py" <sarif-file> [<sarif-file>...]
```

Non-Claude agents resolve the path relative to this skill's directory. Outputs JSON with `meta` (counts), `by_severity`, `by_tool`, and `findings`. Deduplicates by `(tool + rule_id + uri + start_line)` fingerprint; normalizes severity using CVSS `security-severity` first, then SARIF `level`. Use after running tools to consolidate multi-tool SARIF output before filing.

## Severity mapping

Normalize tool-specific severities to the standard five levels:

| Tool severity | Normalized |
| --- | --- |
| critical / CRITICAL | Critical |
| high / HIGH / error | High |
| medium / MEDIUM / warning / WARN | Medium |
| low / LOW / note / INFO | Low |
| informational / advisory / hint | Advisory |

- gitleaks: all secrets are **Critical** unless the matched rule is tagged `allowlist`.
- semgrep/opengrep: use `.extra.severity`; `ERROR` → High, `WARNING` → Medium, `INFO` → Low.
- checkov: use the check's severity metadata when present; no metadata → default Medium.

## Redaction

Never print an actual secret value. Record file, line, rule, and a redacted excerpt: keep the first 4 and last 4 characters, replace everything between with `***` (`AKIAIOSFODNN7EXAMPLE` → `AKIA***MPLE`). Values of 8 characters or fewer → `[REDACTED]`. Findings files are often committed to git — redact before writing, always.

## Fix strategy

| Finding type | Auto-fixable | Action |
| --- | --- | --- |
| Dependency vulnerability with known fix version | Yes, after asking | Run package manager upgrade command |
| Secret in working tree (not committed) | Yes, after asking | Remove from file, add to `.gitignore` |
| Secret in git history | No — requires `git filter-repo` or BFG | Document the exact command; warn that it is destructive and requires force-push |
| IaC misconfiguration | Sometimes — checkov `--fix` flag | Ask before applying |
| SAST / gosec finding | No — requires code change | Provide the exact fix in the finding |

## Common mistakes

- **Running tools without probing first.** A missing tool is "Not available", not an error.
- **Printing raw JSON output.** Parse it — never dump hundreds of lines of JSON at the user.
- **Including the actual secret value in a finding.** Redact. Always.
- **Treating a non-zero exit code as a fatal error.** Most security tools exit non-zero when they find issues — expected behavior, not a crash.
- **Deduplicating by title instead of ID.** Match on CVE ID or rule ID; description strings differ across tools.
- **Re-validating findings from tools that did not run this pass.** Absence of a report from a tool that never ran proves nothing — leave those findings open.
- **Silently skipping a tool that crashed or emitted bad JSON.** Record it under "Errored" with the message.
