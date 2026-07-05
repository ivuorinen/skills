# silent-failure-hunter

Hostile single-shot audit of application error handling. Assumes failures are being swallowed and proves where: enumerates every error handler, ignored error signal, async call site, retry loop, and fallback branch, constructs the concrete upstream failure for each, and traces it to its observation point. Every path where a real failure becomes silence — lost data, a fabricated success, an outage no operator sees — is filed with the quoted handler code, the failure scenario, and the observable consequence. On approval it fixes each finding by changing the error path only; the happy path's behavior is never altered.

## When to Use

- "Find silent failures" / "audit error handling" / "what errors are we swallowing"
- Auditing catch blocks, fallback logic, or retry behavior for failures that vanish
- After an incident where a failure surfaced late or never — to find its siblings before they fire
- Before a release, to prove no failure path exits the system unobserved

**When NOT to use:**
- Fail-open hooks or unenforced rules on the Claude Code enforcement surface → use [loophole-hunter]
- General correctness bugs in the happy path → use [adversarial-reviewer]
- Security vulnerabilities → use [security-auditor]

## silent-failure-hunter vs. loophole-hunter vs. adversarial-reviewer

| | silent-failure-hunter | loophole-hunter | adversarial-reviewer |
|---|---|---|---|
| Question | "Which failures does this application swallow?" | "Can this Claude Code constraint be evaded?" | "Where is this code wrong?" |
| Surface | Application error handling: handlers, ignored signals, async sites, retries, fallbacks | The enforcement surface: rules, hooks, settings, permissions, skills | Any code under review: logic, edge cases, state, everything |
| Output | `docs/audit/silent-failure-hunter-findings.md` + error-path-only fixes on approval | `docs/audit/loophole-hunter-findings.md` + closed loopholes on approval | Findings to stdout, severity-ordered, no fixes |

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Every file the project itself maintains (application code, scripts, tools; vendored/third-party and generated code excluded): catch/except/rescue blocks, error callbacks and `.catch()`, unawaited calls and rejection-free promise chains, discarded error-carrying return values, retry loops, fallback branches |
| **Writes** | `docs/audit/silent-failure-hunter-findings.md`; on approval, error-path-only fixes to source files (left unstaged) |

## How to Invoke

```
/silent-failure-hunter
```

Enumerates the full handler surface automatically — never a sample. A run is COMPLETE only when every enumerated element is examined; any `Unexamined:` element forces verdict INCOMPLETE.

## Defect Classes

| Class | Definition |
|-------|------------|
| **swallowed-exception** | Empty catch, or catch-log-continue where the swallowed failure loses or corrupts data |
| **fail-open-default** | Error path returns a success value or default indistinguishable from a real result |
| **overbroad-catch** | `catch Exception` / bare `catch (e)` around logic that raises programming errors, converting bugs into handled failures |
| **ignored-error-signal** | A return code, error result, or errback discarded; an unawaited call or promise chain with no rejection path |
| **masking-fallback** | Fallback (cache-on-error, default config, secondary source) serving degraded data with no signal that the primary failed |
| **silent-retry** | Retry loop with no bound or no exhaustion signal, converting persistent failure into indefinite silence |
| **cause-destroyed** | Rethrow or error message that drops the original exception — no chaining, no context, lost stack |

## The Evidence Rule

Every finding quotes the handler code, names the concrete upstream failure (what throws, times out, or returns the error), and states the observable consequence — what the caller, user, or on-call engineer never finds out about. Style is not harm; no real-harm scenario, no finding. Logging alone is a finding only when the log provably reaches no one — but a log never converts data loss into handled. Deliberate degradation that is documented, signalled, and bounded is not a finding.

## Process

```
0. Re-validate existing findings (re-trace each Open scenario; now signals → Fixed)
1. Enumerate the handler surface — every handler, async site, ignored signal,
   retry, fallback; record counts; never sample
2. Trace every element to its observation point — receipt is not observation;
   an error a caller discards is still silent
3. File findings — quoted handler + scenario + consequence + exact error-path fix
4. Write docs/audit/silent-failure-hunter-findings.md
5. Ask: "Fix silent failures? (a)ll (c)ritical-and-high only (s)afe (n)o" —
   test suite + scenario re-trace after every fix; happy-path changes are reverted
6. Ask: "Commit findings to git? (y/n)" — never commit silently
```

## Findings Format

```
# Silent Failure Hunter Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N elements unexamined)
- Surface enumerated: handlers N | async sites N | ignored-signal sites N | retries N | fallbacks N
- Examined: handlers N | async sites N | ignored-signal sites N | retries N | fallbacks N

## Open Findings

### Critical

#### [SF-NNN] Short title
Status: Open
Class: <swallowed-exception|fail-open-default|overbroad-catch|ignored-error-signal|masking-fallback|silent-retry|cause-destroyed>
Area: <file path:line>
Handler: <the quoted handler code>
Scenario: <the concrete upstream failure>
Consequence: <what the caller/user/on-call engineer never finds out about>
Fix: <the exact error-path change — the happy path stays untouched>
```

Finding ID format: `SF-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | Data loss or corruption passes silently — swallowed exception on a write path; fail-open default stored or returned as real data |
| High | An outage or failure is invisible to operators — masking fallback with no signal; unbounded signal-free retry; error path no log, metric, or alert reaches |
| Medium | Overbroad catch masking programming errors; cause-destroying rethrow; ignored error signal with user-visible effect but no data loss |
| Low | Under-signalled failure (wrong level, missing context, delayed signal) on a path with no data consequence |
| Advisory | Deliberate degradation that is signalled and bounded but undocumented; hardening with no concrete harm scenario yet |

## Related Skills

- [adversarial-reviewer] — hunts happy-path correctness bugs; this skill hunts the failures the error paths hide
- [loophole-hunter] — audits the Claude Code enforcement surface for evasion; fail-open hooks and rules belong there
- [security-auditor] — application-source security findings
- [nitpicker] — whole-repository defect audit across all categories

---

[adversarial-reviewer]: ../adversarial-reviewer/README.md
[loophole-hunter]: ../loophole-hunter/README.md
[security-auditor]: ../security-auditor/README.md
[nitpicker]: ../nitpicker/README.md
