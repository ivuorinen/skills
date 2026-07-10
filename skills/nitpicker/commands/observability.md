# /nitpicker observability — Observability Auditor

Hostile single-shot audit of the signal surface a codebase emits: assume every production failure is invisible until the emitted logs, metrics, traces, and alerts prove otherwise.

## When to use

- Auditing logging, metrics, tracing, or alerting coverage on critical paths
- After an incident nobody diagnosed from the emitted signals — to find the sibling blind spots
- Before a release, to prove no money, auth, or data-loss path is invisible in production
- Triggers: "audit observability", "check our logging", "can we debug this at 3am"

Run standalone or by the `/nitpicker` default audit flow.

This is not `/nitpicker errors`. That command finds errors being swallowed on the error path; this one asks whether usable signal exists at all — on success and on failure. Both meet at "the failure is invisible": this command files the missing emission; that one files the swallowing handler. Out of scope: swallowed exceptions and fail-open handlers route to `/nitpicker errors`; hardcoded secrets in source route to `/nitpicker security` — but personal data or credentials _emitted to logs_ is this command's pii-in-logs class; happy-path logic bugs route to `/nitpicker review`. Dashboards, pager routing, and log-shipping infra outside the repo are unverifiable — report each in the summary naming what to check and where, never skip the check silently.

## Defect classes

Check every enumerated element against every applicable class. A finding is filed only with the file:line of the path, what it emits versus what diagnosing it requires, and the concrete 3am scenario that stays invisible.

| Class | Definition | Evidence to construct |
| --- | --- | --- |
| **dark-path** | A money, auth, or data-loss path that emits no log, metric, or span on success or failure | The path's entry-to-exit trace with zero emission sites, and a failure on it no signal reports |
| **no-correlation** | Requests crossing a service, queue, or process boundary with no propagated correlation/request ID — each hop unlinkable | The boundary crossing and the emissions on each side that share no identifier |
| **level-misuse** | A real error logged at debug/info below the deployed threshold, or routine noise at error/warn drowning the pager | The statement, its level, and the threshold or pager rule it defeats |
| **unfireable-alert** | An in-repo alert/monitor referencing a metric name or label the code never emits | The alert expression and the absent emission in the codebase |
| **cardinality-bomb** | A metric label fed an unbounded value — user ID, raw URL, free-form string — exploding the time-series backend | The label, the unbounded source feeding it, and the growth driver |
| **pii-in-logs** | Personal data or credentials written to logs — the emission, not mere presence in source | The log statement and the field carrying the personal data or credential |
| **silent-job** | A cron, background, or queue worker with no success signal and no failure signal — indistinguishable from never running | The job entry point and its zero emissions on both outcomes |
| **context-free-error** | An error logged without the identifiers needed to act — no entity ID, no operation, message only | The log statement and the identifier the diagnosis requires that it omits |

**Evidence rule.** Every finding names the file:line of the path, states what the path emits today versus what diagnosing it requires, and constructs the concrete 3am scenario — the production failure an on-call engineer never sees or cannot act on. Signal is usable only end-to-end: emitted on both outcomes, at a deployed level, carrying the identifiers to act, free of PII and unbounded labels. The presence of a logger call proves none of that; a path whose emissions provably meet that standard is not a finding.

## Process

1. **Inventory the observability stack.** Identify the logging framework(s), metrics library, tracing library, and every in-repo alert/monitor/recording-rule config (Prometheus rules, Alertmanager, Grafana provisioning, Terraform/CloudFormation monitors, SLO configs). Record what exists and what is absent — an absent piece is audit input, never an exemption.
2. **Enumerate the surface.** Critical paths (money, auth, data writes/deletes), every cross-service/queue boundary crossing, every cron/background/queue worker, every in-repo alert rule, and every log statement and metric label registration in project-maintained code — pii-in-logs, cardinality-bomb, and level-misuse apply to every emission, not only critical paths. Record counts per category; this inventory is the coverage checklist — never proceed on a sample. Any unexamined element forces run verdict INCOMPLETE.
3. **Trace each path's emissions end to end.** For each critical path, boundary crossing, and job: list every log, metric, and span emitted on success and on failure, the level, and the identifiers carried. At each boundary, confirm in code or config that the correlation ID propagates — platform propagation is proven, not presumed. Sweep every enumerated log statement and metric label for pii-in-logs, cardinality-bomb, and level-misuse.
4. **Cross-check alert configs against emissions.** For every in-repo alert expression, resolve each metric name and label to the emitting code; a reference with no emitting code is unfireable-alert.
5. **File findings** via the store protocol in `_conventions.md`, using `--auditor observability`. The finding body records the class, what the path emits today ("nothing" counts), what diagnosing it needs, and the 3am scenario; the Fix is the exact emission to add or correct — never a business-logic change.
6. **Summary and fix gate.** State the run verdict (COMPLETE only if zero enumerated elements are unexamined) and list unverifiable out-of-repo surfaces, then run the shared apply-fixes prompt. `(s)afe` means: only correct levels on existing log statements and add identifiers or the propagated correlation ID to them — no new emission sites, no metric/alert changes. After each fix, run the project's test suite (when none exists, record that — its absence waives nothing) and re-trace the path to show the scenario now surfaces. A fix that changes business logic is reverted, not adjusted. Fix edits stay in the working tree unstaged.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | A data-loss or security event would be invisible in production: dark-path or silent-job on a money, auth, or data-persistence path with no failure signal; unfireable-alert guarding such a path; credentials or auth tokens written to logs (the log itself is the security event) |
| High | An outage is diagnosable only by guesswork: no-correlation across a boundary on a critical path; real errors below the deployed threshold; cardinality-bomb whose growth takes down the metrics backend; personal data (non-credential) written to logs |
| Medium | context-free-error on a critical path; routine noise at error/warn drowning the pager; dark-path or unfireable-alert on a non-critical path; silent-job whose only liveness check lives outside the repo |
| Low | level-misuse with no threshold or pager consequence; context-free-error on a non-critical path; a critical path signalling one outcome where the other is inferable from adjacent signals |
| Advisory | Hardening where every scenario already surfaces: span attributes, structured-field consistency, SLO wiring for an already-signalled path |

## Fix strategy

Every fix adds or corrects emissions only. Business logic — control flow, return values, side effects other than the added signal — is identical before and after every fix; a fix that fails this test is reverted. Every added emission must itself pass this command's defect classes: no personal data or credentials, bounded label values, a level at or above the deployed threshold, and the identifiers needed to act.

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
- Marking a finding fixed without re-tracing the path and showing the scenario now surfaces
- Silencing the pager by deleting an alert to resolve noise — noise is fixed at the emission

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

- **"There's a logging framework configured, so the system is observable."** A configured framework proves the capability to emit, not that critical paths emit. Coverage is judged per path in step 3; a framework with zero calls on the payment path is a dark-path.
- **"The happy path works — only errors need signal."** A job with no success signal is indistinguishable from a job that never ran; a path silent on success is indistinguishable from a path that is down. Critical paths signal both outcomes.
- **"I'll grep for logger calls and count them — high density means covered."** Density is not coverage. A thousand debug lines on request parsing and zero on the refund path is an invisible refund path. The unit of audit is the critical path traced end to end, never the call count.
- **"Alerts live in Grafana, out of scope — skip the check."** In-repo alert, monitor, and rule configs are in scope and cross-checked in step 4. Out-of-repo surfaces are reported as unverifiable, naming what to check and where — never skipped silently.
- **"Adding logs everywhere is the fix — log the whole request object for completeness."** Blanket logging manufactures level-misuse and drowns the pager, and a whole request object carries PII and unbounded payloads — that fix fails this command's own classes on arrival. Every fix is surgical, tied to one finding, and carries the identifiers needed to act and nothing more.
- **"PII in logs is the security command's job."** The emission is this command's surface: personal data or credentials written to logs is pii-in-logs, filed here. Hardcoded secrets sitting in source, not emitted, route to `/nitpicker security`.
- **"The error is logged, so it's diagnosable."** A message without the entity ID and operation forces the on-call engineer to guess which record and which request. A log line is judged by whether it carries what acting requires — otherwise it is context-free-error.
- **"The service mesh propagates correlation IDs, no need to check."** Propagation is proven in code or config, never presumed from platform. A queue hop, a spawned job, or an unwrapped outbound call drops the ID; trace every boundary in step 3.
- **"This handler swallows the error — I'll file it here."** Suppression on the error path is `/nitpicker errors`' surface; route it there and file here only what the path fails to emit. Conversely, never defer dark paths to that command — a path with no handler and no signal at all is exactly this command's finding.
- **"The metric name looks right, the alert will fire."** Resolve every metric name and label in the expression to the emitting line of code. One renamed label makes the alert unfireable and the path unguarded — file it, never eyeball it.
- **"A user-ID label is fine at our traffic level."** Cardinality is structural, not a traffic question. An unbounded label grows with the data and kills the TSDB at the worst moment — during the incident that spikes it. File cardinality-bomb regardless of current volume.
- **"Too many paths to trace them all, I'll sample."** Sampling is how the silent refund path survives the audit. Enumerate everything in step 2; genuine time exhaustion produces named unexamined elements and verdict INCOMPLETE, never a sample presented as done.
