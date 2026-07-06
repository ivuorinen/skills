---
name: resource-leak-auditor
description: 'Hostile single-shot resource-lifecycle audit — hunts acquire-without-guaranteed-release on the failure path: unclosed handles, pool exhaustion, listener/subscription leaks, orphaned tasks, uncancelled contexts, temp-artifact leaks, and non-deterministic native-resource release, each finding naming the acquisition site, the path where release is skipped, and the accumulation driver. Use when auditing a codebase for resource leaks, checking for unclosed connections, a file-descriptor or memory-from-listeners leak, or when perf-auditor routes a resource-lifecycle finding here. Triggers: "resource leak audit", "find leaks", "check for unclosed connections", "file descriptor leak", "memory leak from listeners", "run resource-leak-auditor".'
---

# Resource Leak Auditor

## Overview

Hostile single-shot resource-lifecycle audit. Assume every acquired resource leaks on the failure path until a guaranteed-release construct proves otherwise. Hunt seven defect classes — unclosed handles, pool exhaustion, listener/subscription leaks, orphaned tasks, uncancelled contexts, temp-artifact leaks, and non-deterministic native-resource release — and file each with the exact acquisition site, the specific path (usually error or early-return) where release is skipped, the accumulation driver (the repetition that makes the leak grow), and a concrete guaranteed-release fix. Speculation is banned: "it's probably closed somewhere" is not a finding; every leak claim reads every path out of the acquisition and shows the one where release does not happen. Static-first: reads every path out of each acquisition and never runs the target program; it incorporates leak/handle tooling output only when the project already produces it, and never installs or executes such tooling itself. All findings are graded Critical → Advisory and written to `docs/audit/resource-leak-auditor-findings.md`.

## When to Use

- Auditing a codebase for resource leaks before a release, a traffic increase, or a long-running-service deployment
- When asked to "find leaks", "check for unclosed connections", "audit file-descriptor usage", or "why does memory grow from listeners"
- When `perf-auditor` (or any other skill) routes a resource-lifecycle finding here
- After adding a path that acquires a scarce resource — a connection, a file handle, an event listener, a background task

**When NOT to use:** `perf-auditor` owns *unbounded growth by design on the hot path* — a cache with no eviction policy, a queue that fills faster than it drains; this skill owns *acquire-without-release, especially on the failure path*. For a pool: if the pool is simply too small for the offered load, that is `perf-auditor`; if borrowed handles are not returned, that is this skill. `silent-failure-hunter` owns the *swallowed error itself* — the empty catch, the fail-open default; this skill owns the *resource orphaned when that error unwinds*. General logic bugs → `adversarial-reviewer`; security → `security-auditor`; whole-repo defect audit → `nitpicker`. A resource released on every path is not a finding — do not route it, drop it.

## Defect Classes

File a finding only when the class, the acquisition site, the specific path where release is skipped, and the accumulation driver are all named. A driver is a repetition the deployment does not bound: per-request, per-loop-iteration, per-mount, per-event — an acquisition that runs again and again as the process serves traffic. A one-shot acquire on a process that exits immediately (a CLI that acquires once and exits) is at most Low — process exit reclaims it; say so. No acquisition site, no skipped path, no driver → no finding.

| Class | What to hunt | Evidence to construct |
|-------|--------------|------------------------|
| **unclosed-handle** | A file/socket/stream/DB-connection/cursor acquired with no guaranteed close on **all** paths — no `with`/`try-finally`/`defer`/`using`/RAII wrapping the acquisition | The acquire site, the path (usually error/early-return) where close is skipped, the accumulation driver, and the guaranteed-release construct that closes it on every path |
| **pool-exhaustion** | A connection/thread/handle borrowed from a pool and not returned on the error path, accumulating until the pool empties | The borrow site, the path where the handle is not returned, the driver, and the `finally`-return that releases it back |
| **listener-subscription-leak** | An event listener/observer/signal-handler/subscription added with no matching removal on teardown, growing per mount/request/iteration | The add site, the missing removal, the per-X driver, and the teardown-hook removal that pairs it |
| **orphaned-task** | A goroutine/thread/async-task/timer/interval started with no cancellation or join path — fire-and-forget outliving its context | The start site, the absent cancellation, the driver, and the cancellation/join that bounds its lifetime |
| **context-leak** | A cancellation token / context / scope not propagated or cancelled, keeping downstream work and its resources alive | The un-cancelled context, what it keeps alive downstream, the driver, and the propagation/cancel that releases it |
| **temp-artifact-leak** | A temp file/dir/lock-file created without cleanup on the error path | The create site, the path where cleanup is skipped, the driver, and the cleanup (unlink/remove/release) that runs on every path |
| **native-resource-leak** | A native/FFI handle or a `Disposable`/`Closeable`/`AutoCloseable` released non-deterministically — relying on GC/finalizer for a scarce resource | The acquire site, the non-deterministic release path, the driver, and the deterministic-dispose (`using`/`try-with-resources`/explicit `dispose`) fix |

## Process

```
0. Re-validate existing findings
   If docs/audit/resource-leak-auditor-findings.md exists, re-check each finding with Status: Open
   against the current code:
   - The acquisition is now wrapped in a guaranteed-release construct, or the leaking path is
     gone, or the fix landed → Fixed (record date)
   - Finding was wrong (release did happen on every path, the driver does not repeat) → Invalid
     (record why)
   - Still leaking → leave Open. Never carry a finding forward without re-checking it.

1. Map the acquisition sites and the paths that must release
   Enumerate every resource acquisition: file/socket/stream opens, DB connection and cursor
   creation, pool borrows, event-listener/subscription registrations, task/goroutine/thread/
   timer starts, context/scope creation, temp-file/lock creation, native/FFI/Disposable
   handles. For each, name the driver (per-request, per-loop, per-mount, per-event, or one-shot)
   and trace every path out of the acquisition to its release. Every finding sits on an
   acquisition traced to at least one path where release is skipped. An acquisition site left
   untraced is recorded as an `Unexamined:` Summary bullet naming a concrete blocker (unreadable
   generated code, missing source, no access) — effort savings is not a blocker, and a silently
   skipped acquisition is a defect in the audit itself.

2. Probe leak/handle tools — never install
   Probe with `which` and manifest inspection: handle/fd inspectors (lsof, `/proc/<pid>/fd`),
   leak detectors already in the manifest (valgrind, LeakSanitizer, tracemalloc, Go's
   `-race`/pprof goroutine dump, Node `--trace-warnings`/`process._getActiveHandles`), and
   linters that flag unclosed resources (ruff/flake8 resource rules, eslint teardown rules).
   Record what is available in the Summary. Absent tools stay absent — reason from the code.

3. Hunt every defect class on every traced path
   Work the Defect Classes table. For each candidate:
   a. Confirm the acquisition and read EVERY path out of it — the happy path, each early return,
      each raised/thrown branch, each break/continue. The error path decides.
   b. Verify no guaranteed-release construct already covers it: `with`/`try-finally`/`defer`/
      `using`/`try-with-resources`/RAII, or an existing teardown/cleanup hook. "Probably closed
      somewhere" is banned; the path decides. A resource released on every path is not a finding.
   c. Name the accumulation driver and confirm it repeats. A one-shot acquire on a process that
      exits immediately is at most Low — process exit reclaims it; grade it so, do not dismiss it
      and do not inflate it.
   d. Candidate fails a, b, or c → drop it. It is not a finding.

4. File findings
   Assign the next RL-NNN id. Record class, site (acquisition → leaking path, file:line), the
   path where release is skipped, the driver, the impact, and the concrete guaranteed-release fix.

5. Write docs/audit/resource-leak-auditor-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.

6. Present summary — finding counts by severity, tools used, unexamined acquisition sites —
   then ask: "Apply fixes? (a)ll auto-applicable  (c)ritical-and-high only  (n)o"
   Apply in severity order, Critical first. Only the Fix Strategy auto-applicable list
   is eligible through this prompt; every other fix stays a proposal in its finding and
   is applied only when the user approves that specific change by name.

7. Commit gate
   Fix edits are left in the working tree unstaged. Ask: "Commit findings to git? (y/n)" —
   on yes, stage only docs/audit/resource-leak-auditor-findings.md. Never commit silently.
```

## Findings Format

Output path: `docs/audit/resource-leak-auditor-findings.md`

```
# Resource Leak Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Acquisition sites traced: N | Unexamined: N
- Leak/handle tools available: <comma-separated list, or none>
- Unexamined: <acquisition site> — <why not traced>

## Open Findings

### Critical

#### [RL-NNN] Short title
Status: Open
Class: <unclosed-handle|pool-exhaustion|listener-subscription-leak|orphaned-task|context-leak|temp-artifact-leak|native-resource-leak>
Site: <acquisition → leaking path, file:line>
Path: <the specific path where release is skipped — the error/early-return branch>
Driver: <the repetition that grows the leak — per-request, per-loop, per-mount, per-event>
Impact: <what resource is exhausted and at what scale>
Fix: <the concrete guaranteed-release change — with/try-finally/defer/using, finally-return, teardown removal>

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

#### [RL-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <what changed, and the re-check showing release now happens on every path>

## Invalid

### Pass N — YYYY-MM-DD

#### [RL-NNN] Short title
Notes: <why the finding was wrong — release happened on every path, driver does not repeat, dead path>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the other `## Summary` bullets after it. Keep the Total line in exactly that shape and insert no field into it. All supplementary bullets (`Acquisition sites traced`, `Leak/handle tools available`, `Unexamined:`) follow the Total line; unexamined acquisition sites live as `Unexamined:` Summary bullets, never in a separate section. All fixed findings go under one `## Fixed` h2 and all invalid findings under one `## Invalid` h2, sub-divided by `### Pass N — YYYY-MM-DD` h3 headers — never `## Fixed — pass N` variants, never h2 → h4 without an h3.

The per-finding `Status:` field is `Open` for a verified, still-leaking finding; on moving a finding to Fixed or Invalid, drop the `Status:` line. Step 0 re-validation re-checks every finding with `Status: Open`. Finding ID format: `RL-NNN` (zero-padded to 3 digits). Assign sequentially from the highest existing ID; never reuse an ID, even after Fixed or Invalid.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | A leak on a per-request or per-event path that exhausts a finite resource (file-descriptor limit, connection pool) and downs the service under normal traffic |
| High | A leak on a repeated path with a real driver that degrades the process over time — unbounded listener/subscription growth, orphaned goroutines/threads accumulating |
| Medium | A leak only on the error path of a frequently-failing operation; temp-artifact accumulation with a real driver |
| Low | A leak on a bounded or one-shot path (startup, a CLI that acquires once and exits) where process exit reclaims it — named as such |
| Advisory | Non-deterministic release (GC/finalizer) of a scarce resource with no measured accumulation yet, on a path with a named, realistic route to repetition |

## Fix Strategy

**Auto-applicable (ask first via the step 6 prompt, apply only on approval):**
- Wrap an acquisition in the language's guaranteed-release construct — `with`, `try-finally`, `defer`, `using`, `try-with-resources`
- Return a pooled resource in a `finally` so the error path releases it back to the pool
- Add the missing `removeEventListener`/`unsubscribe`/`off` to the **existing** teardown/cleanup hook that pairs the add site
- Add the missing temp-file/lock cleanup (unlink/remove/release) inside the same `finally` that guards the create site

**Requires explicit approval per change:**
- Adding cancellation or a join to an orphaned task — this changes lifecycle and shutdown behavior; name the change in the finding
- Introducing a teardown/lifecycle hook where none exists — this is new structure, not a wrap of existing code
- Propagating or cancelling a context that downstream code depends on — name the downstream effect

**Never:**
- Replace a real deterministic close with reliance on GC/finalizer — that is not a fix, it is often the defect
- Add a dependency — no leak-detector libraries, no handle-tracking frameworks. Absent tools stay absent
- Apply any fix before the step 6 summary and prompt — even the auto-applicable list waits for the answer
- Commit anything silently

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"It's probably closed somewhere."** Read every path out of the acquisition — the error path decides. "Probably" is banned in both directions: filing a leak the code demonstrably closes in a `finally` is a junk finding; dismissing one it demonstrably skips on the raise path is silent approval of a real defect.

**"GC will collect it, so it's fine."** GC does not release file descriptors, sockets, or locks deterministically — a finalizer runs whenever the collector decides, which is far too late for a scarce resource under load. Reliance on GC is not a fix, and for a scarce resource it is often the defect itself.

**"This leaks, but only on the error path nobody hits."** A frequently-erroring operation hits its error path constantly — a failing dependency, a timing-out call, a validation that rejects most input. Name the driver and grade it; do not wave it away because the happy path is clean.

**"It's a short-lived process, so leaks don't matter."** True only for a genuinely one-shot exit path — a CLI that acquires once and exits. Say so and grade it Low; process exit reclaims it. Do not extend that reasoning to a long-running service, where every per-request leak accumulates until the process dies.

**"This unbounded cache is a leak."** No — a cache with no eviction policy is unbounded growth by design, which is `perf-auditor`'s territory. One line routing it there, then back. Your scope is acquire-without-release, not grow-without-bound.

**"The pool is exhausted, so it's a perf problem."** Decide and state which. If borrowed handles are not RETURNED on the error path, the exhaustion is yours — file it as pool-exhaustion. If handles are returned correctly and the pool is simply too small for the offered load, that is `perf-auditor`; route it and say so.

**"I'll wrap it in try/finally as I go."** No fix is applied before the step 6 summary and prompt. Even the auto-applicable list waits for the answer. Fixes applied mid-hunt bypass the approval gate and contaminate re-validation.

**"I found a swallowed exception too, I'll fix the catch here."** The swallowed error is `silent-failure-hunter`'s scope; you own the resource orphaned when that error unwinds. One line naming the route, then back to hunting leaks — do not fix the catch.

**"This acquisition looks fine, so I'll skip tracing its error path."** Every path out of the acquisition is read — the happy path, each early return, each raised branch. A leak lives on exactly the path you did not read. A silently skipped acquisition site is an unfiled finding.

**"Last pass's findings are surely still valid — skip step 0."** Every `Status: Open` finding is re-checked against current code every run. Code moves; a stale Open finding sends the user chasing a fixed leak, and a silently-fixed one never reaches the Fixed ledger.
