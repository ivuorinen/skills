---
name: observability-auditor
description: 'Hostile single-shot audit of the signal surface a codebase emits — assumes production failures are invisible until logs, metrics, traces, and alerts prove otherwise: dark paths, missing correlation IDs, level misuse, unfireable alerts, cardinality bombs, PII in logs, silent jobs, context-free errors. Use when auditing logging, metrics, tracing, or alerting coverage, or after an undiagnosable incident. Triggers: "audit observability", "can we debug this at 3am", "check our logging".'
---

# Observability Auditor

## Overview

Hostile audit of a codebase's signal surface. It assumes every production failure is invisible until the emitted signals prove otherwise: it inventories the observability stack actually in use, enumerates every critical path — money movement, auth decisions, data writes, cross-service boundaries, background jobs — plus every log statement and metric label, then traces each path's emissions end to end and cross-checks every in-repo alert config against the metrics the code actually emits. A path an on-call engineer cannot diagnose at 3am from what it emits is a finding; a path that emits a usable signal is not. It writes `docs/audit/observability-auditor-findings.md` and, on approval, fixes each finding by adding or correcting emissions only — never a business-logic change. Single-shot: re-validate existing findings, inventory, enumerate, trace, cross-check, file, optionally fix, re-validate.

This is not `silent-failure-hunter`. That skill finds errors being swallowed on the error path; this skill asks whether usable signal exists at all — on success and on failure. Out of scope: swallowed exceptions and fail-open handlers (route to `silent-failure-hunter`); hardcoded secrets in source (route to `security-auditor` — but personal data or credentials *emitted to logs* is this skill's pii-in-logs class); dashboards, pager routing, and log-shipping infra outside the repo — file each as an `Unverifiable:` Summary bullet naming what to check and where, never skip the check silently.

## When to Use

- Auditing logging, metrics, tracing, or alerting coverage on critical paths
- When asked to "audit observability", "check our logging", or "can an on-call engineer debug this at 3am"
- After an incident nobody diagnosed from the emitted signals — to find the sibling blind spots
- Before a release, to prove no money, auth, or data-loss path is invisible in production

**When NOT to use:** For errors swallowed on the error path, use `silent-failure-hunter`. For hardcoded secrets and vulnerabilities in source, use `security-auditor`. For happy-path logic bugs, use `adversarial-reviewer`.

## Process

Check every enumerated element against every applicable defect class. A finding is filed only with the file:line of the path, what it emits versus what diagnosing it requires, and the concrete 3am scenario that stays invisible.

| Class | Definition | Evidence to construct |
|-------|------------|------------------------|
| **dark-path** | A money, auth, or data-loss path that emits no log, metric, or span on success or failure | The path's entry-to-exit trace with zero emission sites, and a failure on it no signal reports |
| **no-correlation** | Requests crossing a service, queue, or process boundary with no propagated correlation/request ID — each hop unlinkable | The boundary crossing and the emissions on each side that share no identifier |
| **level-misuse** | A real error logged at debug/info below the deployed threshold, or routine noise at error/warn drowning the pager | The statement, its level, and the threshold or pager rule it defeats |
| **unfireable-alert** | An in-repo alert/monitor referencing a metric name or label the code never emits | The alert expression and the absent emission in the codebase |
| **cardinality-bomb** | A metric label fed an unbounded value — user ID, raw URL, free-form string — exploding the time-series backend | The label, the unbounded source feeding it, and the growth driver |
| **pii-in-logs** | Personal data or credentials written to logs — the emission, not mere presence in source | The log statement and the field carrying the personal data or credential |
| **silent-job** | A cron, background, or queue worker with no success signal and no failure signal — indistinguishable from never running | The job entry point and its zero emissions on both outcomes |
| **context-free-error** | An error logged without the identifiers needed to act — no entity ID, no operation, message only | The log statement and the identifier the diagnosis requires that it omits |

**Evidence rule.** Every finding names the file:line of the path, states what the path emits today versus what diagnosing it requires, and constructs the concrete 3am scenario — the production failure an on-call engineer never sees or cannot act on. Signal is usable only end-to-end: emitted on both outcomes, at a deployed level, carrying the identifiers to act, free of PII and unbounded labels. The presence of a logger call proves none of that; a path whose emissions provably meet that standard is not a finding.

```
0. Re-validate existing findings
   If docs/audit/observability-auditor-findings.md exists, re-check each Status: Open
   finding: now signals (re-trace — the scenario surfaces) → Fixed (record date); wrong
   (usable signal existed, or the path is not real) → Invalid; still dark → leave Open.

1. Inventory the observability stack
   Identify the logging framework(s), metrics library, tracing library, and every in-repo
   alert/monitor/recording-rule config (Prometheus rules, Alertmanager, Grafana
   provisioning, Terraform/CloudFormation monitors, SLO configs). Record what exists and
   what is absent — an absent piece is audit input, never an exemption.

2. Enumerate the surface
   Critical paths (money, auth, data writes/deletes), every cross-service/queue boundary
   crossing, every cron/background/queue worker, every in-repo alert rule, and every log
   statement and metric label registration in project-maintained code — pii-in-logs,
   cardinality-bomb, and level-misuse apply to every emission, not only critical paths.
   Record counts per category; this inventory is the coverage checklist — never proceed
   on a sample. Any unexamined element forces run verdict INCOMPLETE.

3. Trace each path's emissions end to end
   For each critical path, boundary crossing, and job: list every log, metric, and span
   emitted on success and on failure, the level, and the identifiers carried. At each
   boundary, confirm in code or config that the correlation ID propagates — platform
   propagation is proven, not presumed. Sweep every enumerated log statement and metric
   label for pii-in-logs, cardinality-bomb, and level-misuse.

4. Cross-check alert configs against emissions
   For every in-repo alert expression, resolve each metric name and label to the
   emitting code; a reference with no emitting code is unfireable-alert.

5. File findings
   Assign the next OB-NNN id; record class, area (file:line), Emits, Needs, Scenario,
   and the exact emission fix. Apply the Evidence rule to every entry.

6. Write docs/audit/observability-auditor-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.

7. Present summary — state the run verdict (COMPLETE only if zero elements are
   Open-Unexamined) — then ask: "Add signal? (a)ll  (c)ritical-and-high only  (s)afe  (n)o"
   - (a)ll / (c)ritical-and-high only: apply the matching Auto-applicable fixes.
   - (s)afe: only correct levels on existing log statements and add identifiers or the
     propagated correlation ID to them — no new emission sites, no metric/alert changes.
   Apply in severity order (Critical first). After each fix, run the project's test suite
   (when none exists, record that — its absence waives nothing) and re-trace the path to
   show the scenario now surfaces. A fix that changes business logic is reverted, not
   adjusted. Move proven fixes to Fixed.

8. Commit gate
   Fix edits to source files stay in the working tree unstaged — never stage or commit
   them silently. Then ask: "Commit findings to git? (y/n)"; on yes, stage only
   docs/audit/observability-auditor-findings.md.
```

## Findings Format

Output path: `docs/audit/observability-auditor-findings.md`

```
# Observability Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N elements unexamined)
- Stack: logging <lib|none> | metrics <lib|none> | tracing <lib|none> | alert configs N in-repo
- Surface enumerated: critical paths N | boundaries N | jobs N | alert rules N | log statements N | metric labels N
- Examined: critical paths N | boundaries N | jobs N | alert rules N | log statements N | metric labels N
- Open-Unexamined: N
- Unexamined: <path or config> — <why not examined>
- Unverifiable: <out-of-repo surface> — <what to check and where>

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

#### [OB-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <the emission added or corrected, and the re-traced scenario that now surfaces>

## Invalid

### Pass N — YYYY-MM-DD

#### [OB-NNN] Short title
Notes: <the usable signal that existed, or why the path is not real>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the other `## Summary` bullets after it. Keep the Total line in exactly that shape and insert no field between `Total:` and `Invalid:`. All supplementary bullets (`Run verdict`, `Stack`, `Surface enumerated`, `Examined`, `Open-Unexamined`, `Unexamined:`, `Unverifiable:`) follow the Total line; unexamined and unverifiable elements live as Summary bullets, never in a separate section. `Open-Unexamined` equals the number of `Unexamined:` bullets and is not part of the Open/Fixed/Invalid totals; `Unverifiable:` bullets count toward neither.

The per-finding `Status:` field is `Open` for an examined, still-dark finding; on moving a finding to Fixed or Invalid, drop the `Status:` line. Step 0 re-validation re-checks every finding with `Status: Open`. Finding ID format: `OB-NNN` (zero-padded to 3 digits). Assign sequentially; never reuse ids.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | A data-loss or security event would be invisible in production: dark-path or silent-job on a money, auth, or data-persistence path with no failure signal; unfireable-alert guarding such a path; credentials or auth tokens written to logs (the log itself is the security event) |
| High | An outage is diagnosable only by guesswork: no-correlation across a boundary on a critical path; real errors below the deployed threshold; cardinality-bomb whose growth takes down the metrics backend; personal data (non-credential) written to logs |
| Medium | context-free-error on a critical path; routine noise at error/warn drowning the pager; dark-path or unfireable-alert on a non-critical path; silent-job whose only liveness check lives outside the repo |
| Low | level-misuse with no threshold or pager consequence; context-free-error on a non-critical path; a critical path signalling one outcome where the other is inferable from adjacent signals |
| Advisory | Hardening where every scenario already surfaces: span attributes, structured-field consistency, SLO wiring for an already-signalled path |

## Fix Strategy

Every fix adds or corrects emissions only. Business logic — control flow, return values, side effects other than the added signal — is identical before and after every fix; a fix that fails this test is reverted. Every added emission must itself pass this skill's defect classes: no personal data or credentials, bounded label values, a level at or above the deployed threshold, and the identifiers needed to act.

**Auto-applicable (ask first, apply only on approval):**
- Correct the level of an existing log statement
- Add entity IDs, operation names, or the propagated correlation ID to an existing log statement
- Add a log or metric emission to a dark path or silent job using the inventoried stack
- Propagate an existing correlation ID across a boundary the code already crosses (header, message attribute)
- Redact or drop a PII field from an existing log statement, keeping a non-PII identifier
- Bound a metric label (enumerate, bucket, or hash) or drop the unbounded label
- Correct an in-repo alert expression to the metric names and labels the code emits

**Requires explicit approval per change:**
- Adding a new metric, span, or alert rule — new time series or new pager behavior
- Deleting a log statement or alert rule outright, or changing what an existing alert pages on beyond correcting an unfireable reference

**Never auto-apply:**
- Any change to business logic — control flow, return values, non-signal side effects
- Adding a dependency — fixes use the inventoried stack only; a missing emitter is filed with the fix specified and the dependency decision routed to the user
- An emission that itself fails a defect class: PII, unbounded label, sub-threshold level, identifier-free message
- Marking a finding Fixed without re-tracing the path and showing the scenario now surfaces
- Silencing the pager by deleting an alert to resolve noise — noise is fixed at the emission

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

- **"There's a logging framework configured, so the system is observable."** A configured framework proves the capability to emit, not that critical paths emit. Coverage is judged per path in step 3; a framework with zero calls on the payment path is a dark-path.
- **"The happy path works — only errors need signal."** dark-path and silent-job disagree. A job with no success signal is indistinguishable from a job that never ran; a path silent on success is indistinguishable from a path that is down. Critical paths signal both outcomes.
- **"I'll grep for logger calls and count them — high density means covered."** Density is not coverage. A thousand debug lines on request parsing and zero on the refund path is an invisible refund path. The unit of audit is the critical path traced end to end, never the call count.
- **"Alerts live in Grafana, out of scope — skip the check."** In-repo alert, monitor, and rule configs are in scope and cross-checked in step 4. Out-of-repo surfaces are filed as `Unverifiable:` Summary bullets naming what to check and where — never skipped silently.
- **"Adding logs everywhere is the fix — log the whole request object for completeness."** Blanket logging manufactures level-misuse and drowns the pager, and a whole request object carries PII and unbounded payloads — that fix fails the skill's own classes on arrival. Every fix is surgical, tied to one finding, and carries the identifiers needed to act and nothing more.
- **"PII in logs is security-auditor's job."** The emission is this skill's surface: personal data or credentials written to logs is pii-in-logs, filed here. Hardcoded secrets sitting in source, not emitted, route to `security-auditor`.
- **"The error is logged, so it's diagnosable."** A message without the entity ID and operation forces the on-call engineer to guess which record and which request. A log line is judged by whether it carries what acting requires — otherwise it is context-free-error.
- **"The service mesh propagates correlation IDs, no need to check."** Propagation is proven in code or config, never presumed from platform. A queue hop, a spawned job, or an unwrapped outbound call drops the ID; trace every boundary in step 3.
- **"This handler swallows the error — I'll file it here."** Suppression on the error path is `silent-failure-hunter`'s surface; route it there and file here only what the path fails to emit. Conversely, never defer dark paths to that skill — a path with no handler and no signal at all is exactly this skill's finding.
- **"The metric name looks right, the alert will fire."** Resolve every metric name and label in the expression to the emitting line of code. One renamed label makes the alert unfireable and the path unguarded — file it, never eyeball it.
- **"A user-ID label is fine at our traffic level."** Cardinality is structural, not a traffic question. An unbounded label grows with the data and kills the TSDB at the worst moment — during the incident that spikes it. File cardinality-bomb regardless of current volume.
- **"Too many paths to trace them all, I'll sample."** Sampling is how the silent refund path survives the audit. Enumerate everything in step 2; genuine time exhaustion produces `Unexamined:` bullets and verdict INCOMPLETE, never a sample presented as done.
