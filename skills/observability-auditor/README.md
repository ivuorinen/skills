# observability-auditor

Hostile single-shot audit of a codebase's *signal surface*. Assumes production failures are invisible until the emitted signals prove otherwise: inventories the observability stack actually in use, enumerates every critical path (money, auth, data writes, boundaries, background jobs) plus every log statement and metric label, traces each path's emissions end to end, and cross-checks every in-repo alert config against the metrics the code actually emits. On approval, fixes each finding by adding or correcting emissions only — never a business-logic change, and every added emission must pass the skill's own defect classes.

## When to Use

- "Audit observability" / "check our logging" / "can an on-call engineer debug this at 3am"
- Auditing logging, metrics, tracing, or alerting coverage on critical paths
- After an incident nobody diagnosed from the emitted signals — to find the sibling blind spots
- Before a release, to prove no money, auth, or data-loss path is invisible in production

**When NOT to use:**
- Errors swallowed on the error path → use [silent-failure-hunter]
- Hardcoded secrets and vulnerabilities in source → use [security-auditor]
- Happy-path logic bugs → use [adversarial-reviewer]

## observability-auditor vs. silent-failure-hunter

| | observability-auditor | silent-failure-hunter |
|---|---|---|
| Question | "Does usable signal *exist* — on success and on failure?" | "Is an error that occurred being *swallowed*?" |
| Surface | Emission sites and their absence: critical paths, jobs, boundaries, alert configs, log statements, metric labels | Error handlers: catch blocks, fallbacks, retries, ignored error signals |
| Finds | Paths that emit nothing, unlinkable hops, unfireable alerts, PII in logs, jobs indistinguishable from never running | Failures converted into silence by the handling code |
| Fixes | Adds or corrects emissions; business logic untouched | Changes the error path; happy path untouched |
| Example | A refund succeeds or fails with zero log lines either way — nobody can tell which | A refund fails, the exception is caught, logged at debug, and the caller gets `true` |

Both skills meet at "the failure is invisible" — this skill files the missing emission; that skill files the swallowing handler.

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Project-maintained source (critical paths, jobs, boundary crossings, every log statement and metric label); logging/metrics/tracing framework config; every in-repo alert/monitor/recording-rule config (Prometheus rules, Alertmanager, Grafana provisioning, Terraform/CloudFormation monitors, SLO configs) |
| **Writes** | `docs/audit/observability-auditor-findings.md` |

## How to Invoke

```
/observability-auditor
```

Inventories the stack first, then enumerates the surface and traces emissions automatically. Dashboards, pager routing, and log-shipping infra outside the repo are filed as `Unverifiable:` Summary bullets naming what to check and where — never skipped silently.

## Defect Classes

| Class | Definition |
|-------|------------|
| **dark-path** | A money/auth/data-loss path that emits no log, metric, or span on success or failure |
| **no-correlation** | Requests crossing a service/queue boundary with no propagated correlation ID — each hop unlinkable |
| **level-misuse** | Real errors at debug/info below the deployed threshold, or routine noise at error/warn drowning the pager |
| **unfireable-alert** | An in-repo alert referencing a metric name or label the code never emits |
| **cardinality-bomb** | A metric label fed an unbounded value (user ID, raw URL) that explodes the time-series backend |
| **pii-in-logs** | Personal data or credentials written to logs — the emission, not mere presence in source |
| **silent-job** | A cron/background/queue worker with no success signal and no failure signal — indistinguishable from never running |
| **context-free-error** | An error logged without the identifiers needed to act — no entity ID, no operation, message only |

## Process

```
0. Re-validate existing findings (re-trace each Open path; now signals → Fixed)
1. Inventory the observability stack — logging, metrics, tracing, in-repo alert configs
2. Enumerate the surface — critical paths, boundaries, jobs, alert rules, log statements,
   metric labels — never sample
3. Trace each path's emissions end to end; prove correlation-ID propagation per boundary
4. Cross-check every in-repo alert expression against the emitting code
5. File findings — file:line, Emits vs Needs, the concrete 3am scenario
6. Write docs/audit/observability-auditor-findings.md
7. Ask: "Add signal? (a)ll (c)ritical-and-high only (s)afe (n)o" — re-trace each fix
8. Ask: "Commit findings to git? (y/n)" — never commit silently
```

A run is COMPLETE only when every enumerated element is examined. Any unexamined element is an
`- Unexamined:` Summary bullet and forces verdict INCOMPLETE.

## Findings Format

```
# Observability Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N elements unexamined)
- Stack: logging <lib|none> | metrics <lib|none> | tracing <lib|none> | alert configs N in-repo
- Surface enumerated: critical paths N | boundaries N | jobs N | alert rules N | log statements N | metric labels N

## Open Findings

### Critical

#### [OB-NNN] Short title
Status: Open
Class: <dark-path|no-correlation|level-misuse|unfireable-alert|cardinality-bomb|pii-in-logs|silent-job|context-free-error>
Area: <file path:line of the path>
Emits: <every signal the path emits today — or "nothing">
Needs: <the signal diagnosing it requires>
Scenario: <the concrete 3am production failure that stays invisible or unactionable>
Fix: <the exact emission to add or correct — never a business-logic change>
```

Finding ID format: `OB-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | A data-loss or security event would be invisible in production: dark-path/silent-job on a money, auth, or data-persistence path; unfireable-alert guarding such a path; credentials written to logs |
| High | An outage is diagnosable only by guesswork: no-correlation on a critical path; real errors below the deployed threshold; a cardinality-bomb that takes down the metrics backend; personal data in logs |
| Medium | context-free-error on a critical path; noise drowning the pager; dark-path or unfireable-alert on a non-critical path |
| Low | level-misuse with no threshold or pager consequence; context-free-error on a non-critical path |
| Advisory | Hardening where every scenario already surfaces: span attributes, structured-field consistency, SLO wiring |

## Related Skills

- [silent-failure-hunter] — finds errors *swallowed* on the error path; this skill finds paths with no usable signal at all
- [security-auditor] — hardcoded secrets and source vulnerabilities; emitted PII/credentials stay here
- [adversarial-reviewer] — happy-path correctness bugs found while tracing route there

---

[silent-failure-hunter]: ../silent-failure-hunter/README.md
[security-auditor]: ../security-auditor/README.md
[adversarial-reviewer]: ../adversarial-reviewer/README.md
