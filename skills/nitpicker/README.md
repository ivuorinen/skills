# nitpicker

Adversarial, exhaustive whole-repository code review with integrated fixing. Assumes the code is incorrect until proven otherwise. Audits code, tests, documentation, and configuration for defects — then optionally applies fixes in the same run.

## When to Use

- Full repository audit before a release
- PR review when you want every defect found, not just obvious ones
- Release gate enforcement (fail if findings exceed threshold)
- "Tear this apart" / "find everything wrong" / "exhaustive review"
- "Audit this" / "review the whole codebase" / "find all problems"

**When NOT to use:**
- Scanner-based security scan (CVEs, secrets, dependencies) → use [security-auditor]
- Architecture boundary violations specifically → use [arch-auditor]
- Focused hostile code review of a specific file → use [adversarial-reviewer]

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Whole repository (code, tests, docs, config); in focused modes also reads specialist findings files |
| **Writes** | `docs/audit/nitpicker-findings.md` (not written in `inline` mode) |

## How to Invoke

```
/nitpicker
/nitpicker [mode]
/nitpicker changed-files
/nitpicker release-gate
```

## Modes

| Mode | Behavior |
|------|----------|
| `default` | Full repository review — all areas |
| `inline` | Return findings in response; do NOT write `docs/audit/nitpicker-findings.md` |
| `changed-files` | Limit review to modified files and their dependencies |
| `security` | Invoke [security-auditor]; incorporate findings; focus on trust boundaries and auth logic |
| `tests` | Invoke [test-auditor]; incorporate findings; extend with test structure and behavioral coverage |
| `docs` | Invoke [doc-auditor]; incorporate findings; extend with inline comments and cross-references |
| `architecture` | Invoke [arch-detector] (if profile absent or stale), then [arch-auditor]; extend with coupling analysis |
| `loophole` | Invoke [loophole-hunter] and [hooks-enforcer]; incorporate both findings sets; extend with code-level analysis of hook scripts and skills |
| `perf` | Invoke [perf-auditor]; incorporate findings; extend with algorithmic complexity and resource lifecycle |
| `deps` | Invoke [dep-auditor]; incorporate findings; extend with how the flagged dependencies are used in code |
| `errors` | Invoke [silent-failure-hunter]; incorporate findings; extend with error propagation and recovery paths |
| `ci` | Invoke [ci-auditor]; incorporate findings; extend with the pipeline's build and deploy logic |
| `commits` | Invoke [commit-auditor]; incorporate findings; extend with commit granularity and history hygiene |
| `migrations` | Invoke [migration-auditor]; incorporate findings; extend with migration/application-code coupling |
| `observability` | Invoke [observability-auditor]; incorporate findings; extend with the log and metric call sites in code |
| `contract` | Invoke [api-contract-auditor]; incorporate findings; extend with the implementation behind the declared surface |
| `a11y` | Invoke [a11y-auditor]; incorporate findings; extend with the UI logic behind the WCAG conformance defects |
| `privacy` | Invoke [data-privacy-auditor]; incorporate findings; extend with the data-handling paths behind the privacy defects |
| `config` | Invoke [config-auditor]; incorporate findings; extend with the code paths that consume the flagged config values |
| `leaks` | Invoke [resource-leak-auditor]; incorporate findings; extend with acquisition/release pairing on error paths |
| `i18n` | Invoke [i18n-auditor]; incorporate findings; extend with the presentation layer behind the localization defects |
| `concurrency` | Invoke [concurrency-auditor]; incorporate findings; extend with shared-state access and synchronization boundaries |
| `release-gate` | Fail if any findings at or above the threshold exist (default threshold: High) |

`inline` is incompatible with every specialist-invoking mode — `security`, `tests`, `docs`, `architecture`, `loophole`, `perf`, `deps`, `errors`, `ci`, `commits`, `migrations`, `observability`, `contract`, `a11y`, `concurrency`, `i18n`, `leaks`, `config`, and `privacy`. When combined, only the inline behavior applies (no specialist skills invoked, no file written).

## Review Scope

Nitpicker covers all eight areas in every run:

- Code correctness and logic
- Security and trust boundaries
- Reliability and operational safety
- Maintainability and architecture
- Performance characteristics
- Test coverage and effectiveness
- Documentation accuracy and completeness
- Convention adherence (repo, language, framework)

## Severity Levels

| Level | Meaning |
|-------|---------|
| Critical | Correctness or security failure; must be fixed |
| High | Significant risk or defect |
| Medium | Quality or reliability concern |
| Low | Minor issue or smell |
| Advisory | Informational, no action required |

## Single-Shot Behavior

```
1. Create docs/audit/ if it does not exist
2. If docs/audit/nitpicker-findings.md exists: re-validate each OPEN finding
     - Resolved → move to Fixed (record date)
     - Was wrong → move to Invalid (record reason)
     - Still present → leave Open
3. In any specialist-invoking mode (not inline): invoke the specialist skill(s);
     read the output file(s); incorporate Critical/High findings
4. Add new findings (assign next available ID — never reuse IDs)
5. Present findings summary
6. Ask: "Apply fixes? (a)ll  (c)ritical-and-high only  (s)afe — no refactors  (n)o"
     If a/c/s: apply in severity order; re-run in changed-files mode to verify
     finding count decreases; re-validate; update file
7. Write docs/audit/nitpicker-findings.md (unless inline mode)
8. Ask: "Commit findings to git? (y/n)" — never commit silently
```

## Findings Format

```
# Nitpicker Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N

## Open Findings

### Critical

#### [N-NNN] Short title
Category: <correctness|security|reliability|maintainability|performance|tests|docs|conventions>
Area: path/to/file.ts:42
Problem: <direct description>
Evidence: <proof or failing scenario>
Impact: <why this matters>
Fix: <concrete remediation>
```

Finding ID format: `N-NNN` (zero-padded to 3 digits, e.g. `N-001`). IDs are assigned sequentially and never reused.

## Rules

- No compliments
- No hedging without evidence — if something looks wrong, say it is wrong
- Silence means approval — anything not flagged is implicitly approved
- All findings must include evidence
- Prefer concrete failing scenarios over abstract warnings
- Prefer exact fixes over general advice

## Related Skills

- [security-auditor] — invoked by nitpicker in security mode; also usable standalone
- [doc-auditor] — invoked by nitpicker in docs mode; also usable standalone
- [arch-detector] — invoked by nitpicker in architecture mode if profile is missing or stale
- [arch-auditor] — invoked by nitpicker in architecture mode
- [loophole-hunter] — invoked by nitpicker in loophole mode; audits existing constraints for evasion; also usable standalone
- [hooks-enforcer] — invoked by nitpicker in loophole mode; audits the evidence base for missing hooks and context-discipline gaps; also usable standalone
- [test-auditor] — invoked by nitpicker in tests mode; audits the test suite itself; also usable standalone
- [perf-auditor] — invoked by nitpicker in perf mode; performance audit with growth-driver evidence; also usable standalone
- [dep-auditor] — invoked by nitpicker in deps mode; audits dependency health beyond CVEs; also usable standalone
- [silent-failure-hunter] — invoked by nitpicker in errors mode; audits application error handling for swallowed failures; also usable standalone
- [ci-auditor] — invoked by nitpicker in ci mode; audits CI/CD pipeline definitions; also usable standalone
- [commit-auditor] — invoked by nitpicker in commits mode; audits commit-message discipline against diffs; also usable standalone
- [migration-auditor] — invoked by nitpicker in migrations mode; audits schema and data migrations; also usable standalone
- [observability-auditor] — invoked by nitpicker in observability mode; audits the emitted signal surface; also usable standalone
- [api-contract-auditor] — invoked by nitpicker in contract mode; audits the public contract surface against the implementation; also usable standalone
- [a11y-auditor] — invoked by nitpicker in a11y mode; audits the UI layer against WCAG 2.2 AA; also usable standalone
- [adversarial-reviewer] — focused hostile review of a specific file or component

---

[skill-source]: SKILL.md
[security-auditor]: ../security-auditor/README.md
[doc-auditor]: ../doc-auditor/README.md
[arch-detector]: ../arch-detector/README.md
[arch-auditor]: ../arch-auditor/README.md
[loophole-hunter]: ../loophole-hunter/README.md
[hooks-enforcer]: ../hooks-enforcer/README.md
[test-auditor]: ../test-auditor/README.md
[perf-auditor]: ../perf-auditor/README.md
[dep-auditor]: ../dep-auditor/README.md
[silent-failure-hunter]: ../silent-failure-hunter/README.md
[ci-auditor]: ../ci-auditor/README.md
[commit-auditor]: ../commit-auditor/README.md
[migration-auditor]: ../migration-auditor/README.md
[observability-auditor]: ../observability-auditor/README.md
[api-contract-auditor]: ../api-contract-auditor/README.md
[a11y-auditor]: ../a11y-auditor/README.md
[data-privacy-auditor]: ../data-privacy-auditor/README.md
[config-auditor]: ../config-auditor/README.md
[resource-leak-auditor]: ../resource-leak-auditor/README.md
[i18n-auditor]: ../i18n-auditor/README.md
[concurrency-auditor]: ../concurrency-auditor/README.md
[adversarial-reviewer]: ../adversarial-reviewer/README.md
