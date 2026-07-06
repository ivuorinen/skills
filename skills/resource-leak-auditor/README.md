# resource-leak-auditor

Hostile single-shot resource-lifecycle audit. Assumes every acquired resource leaks on the failure path until a guaranteed-release construct proves otherwise. Hunts seven defect classes — unclosed handles, pool exhaustion, listener/subscription leaks, orphaned tasks, uncancelled contexts, temp-artifact leaks, and non-deterministic native-resource release. Speculation is banned: every leak claim reads every path out of the acquisition and shows the one where release does not happen, then names the accumulation driver — the repetition that makes the leak grow. Static-first: reads every path out of each acquisition and never runs the target program; incorporates leak/handle tooling output only when the project already produces it, never installing or executing tooling itself.

## When to Use

- "find leaks" / "check for unclosed connections" / "audit file-descriptor usage" / "why does memory grow from listeners"
- Before a release, a traffic increase, or a long-running-service deployment
- After adding a path that acquires a scarce resource — a connection, a file handle, an event listener, a background task
- When [perf-auditor] (or any other skill) routes a resource-lifecycle finding here

**When NOT to use:**
- Unbounded growth by design on the hot path (a cache with no eviction, a queue that fills faster than it drains) → use [perf-auditor]
- The swallowed error itself — the empty catch, the fail-open default → use [silent-failure-hunter]
- General logic bugs → use [adversarial-reviewer]
- Security → use [security-auditor]
- Whole-repo defect audit → use [nitpicker]

A resource released on every path is not a finding — do not route it, drop it. For a pool: if borrowed handles are not returned, that is this skill; if the pool is simply too small for the offered load, that is [perf-auditor].

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Every resource acquisition site (file/socket/stream opens, DB connection and cursor creation, pool borrows, listener/subscription registrations, task/goroutine/thread/timer starts, context/scope creation, temp-file/lock creation, native/FFI/Disposable handles) and every path out of it; any leak/handle tool output the project already produces (lsof, `/proc/<pid>/fd`, tracemalloc, pprof goroutine dump, `process._getActiveHandles`) |
| **Writes** | `docs/audit/resource-leak-auditor-findings.md` |

## How to Invoke

```
/resource-leak-auditor
```

## Defect Classes

| Class | Definition |
|-------|------------|
| **unclosed-handle** | A file/socket/stream/DB-connection/cursor acquired with no guaranteed close on all paths — no `with`/`try-finally`/`defer`/`using`/RAII wrapping the acquisition |
| **pool-exhaustion** | A connection/thread/handle borrowed from a pool and not returned on the error path, accumulating until the pool empties |
| **listener-subscription-leak** | An event listener/observer/signal-handler/subscription added with no matching removal on teardown, growing per mount/request/iteration |
| **orphaned-task** | A goroutine/thread/async-task/timer/interval started with no cancellation or join path — fire-and-forget outliving its context |
| **context-leak** | A cancellation token / context / scope not propagated or cancelled, keeping downstream work and its resources alive |
| **temp-artifact-leak** | A temp file/dir/lock-file created without cleanup on the error path |
| **native-resource-leak** | A native/FFI handle or a `Disposable`/`Closeable`/`AutoCloseable` released non-deterministically — relying on GC/finalizer for a scarce resource |

## Process

```
0. Re-validate existing findings against current code
1. Map the acquisition sites and the paths that must release — name the driver (per-request, per-loop, per-mount, per-event, one-shot)
2. Probe leak/handle tools (probe first, never install)
3. Hunt every defect class on every traced path — read EVERY path out (the error path decides), confirm no guaranteed-release construct covers it, name the driver
4. File findings: RL-NNN, class, site, leaking path, driver, impact, concrete guaranteed-release fix
5. Write docs/audit/resource-leak-auditor-findings.md
6. Ask: "Apply fixes? (a)ll auto-applicable (c)ritical-and-high only (n)o"
7. Ask: "Commit findings to git? (y/n)" — never commit silently
```

An acquisition site left untraced is recorded as an `Unexamined:` Summary bullet naming a concrete blocker.

## Findings Format

```
#### [RL-NNN] Short title
Status: Open
Class: <unclosed-handle|pool-exhaustion|listener-subscription-leak|orphaned-task|context-leak|temp-artifact-leak|native-resource-leak>
Site: <acquisition → leaking path, file:line>
Path: <the specific path where release is skipped — the error/early-return branch>
Driver: <the repetition that grows the leak — per-request, per-loop, per-mount, per-event>
Impact: <what resource is exhausted and at what scale>
Fix: <the concrete guaranteed-release change — with/try-finally/defer/using, finally-return, teardown removal>
```

Finding ID format: `RL-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | A leak on a per-request or per-event path that exhausts a finite resource (file-descriptor limit, connection pool) and downs the service under normal traffic |
| High | A leak on a repeated path with a real driver that degrades the process over time — unbounded listener/subscription growth, orphaned goroutines/threads accumulating |
| Medium | A leak only on the error path of a frequently-failing operation; temp-artifact accumulation with a real driver |
| Low | A leak on a bounded or one-shot path (startup, a CLI that acquires once and exits) where process exit reclaims it — named as such |
| Advisory | Non-deterministic release (GC/finalizer) of a scarce resource with no measured accumulation yet, on a path with a named realistic route to repetition |

## Fix Strategy

Auto-applicable fixes (approval-gated via the step 6 prompt) wrap an acquisition in the language's guaranteed-release construct (`with`, `try-finally`, `defer`, `using`, `try-with-resources`), return a pooled resource in a `finally`, add the missing removal to an existing teardown hook, or add temp-file cleanup inside the same `finally` that guards the create site. Adding cancellation/join to an orphaned task, introducing a teardown hook where none exists, or propagating/cancelling a context downstream code depends on each require explicit per-change approval. Never replace a real deterministic close with reliance on GC/finalizer — that is often the defect itself — and never add a dependency.

## Related Skills

- [perf-auditor] — unbounded-growth-by-design and pool-too-small-for-load routed there
- [silent-failure-hunter] — the swallowed error itself routed there
- [adversarial-reviewer] — general logic bugs routed there
- [security-auditor] — security defects routed there
- [nitpicker] — invokes this skill in `leaks` mode

---

[perf-auditor]: ../perf-auditor/README.md
[silent-failure-hunter]: ../silent-failure-hunter/README.md
[adversarial-reviewer]: ../adversarial-reviewer/README.md
[security-auditor]: ../security-auditor/README.md
[nitpicker]: ../nitpicker/README.md
