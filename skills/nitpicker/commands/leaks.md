# /nitpicker leaks — Resource Leak Auditor

Hostile single-shot resource-lifecycle audit: assume every acquired resource leaks on the failure path until a guaranteed-release construct proves otherwise, and file each leak with the acquisition site, the path where release is skipped, and the accumulation driver.

## When to use

- "resource leak audit", "find leaks", "check for unclosed connections", "file descriptor leak", "memory leak from listeners"
- Before a release, a traffic increase, or a long-running-service deployment
- After adding a path that acquires a scarce resource — a connection, a file handle, an event listener, a background task
- When `/nitpicker perf` (or any other command) routes a resource-lifecycle finding here

**Not this command:** `/nitpicker perf` owns _unbounded growth by design on the hot path_ — a cache with no eviction policy, a queue that fills faster than it drains; this command owns _acquire-without-release, especially on the failure path_. For a pool: borrowed handles not returned → this command; pool simply too small for the offered load → `/nitpicker perf`. `/nitpicker errors` owns the _swallowed error itself_ — the empty catch, the fail-open default; this command owns the _resource orphaned when that error unwinds_. General logic bugs → `/nitpicker review`; security → `/nitpicker security`; whole-repo defect audit → `/nitpicker audit`. A resource released on every path is not a finding — do not route it, drop it.

## Mindset

Speculation is banned: "it's probably closed somewhere" is not a finding; every leak claim reads every path out of the acquisition and shows the one where release does not happen. Static-first: read every path out of each acquisition and never run the target program; incorporate leak/handle tooling output only when the project already produces it, and never install or execute such tooling yourself.

## Defect classes

File a finding only when the class, the acquisition site, the specific path where release is skipped, and the accumulation driver are all named. A driver is a repetition the deployment does not bound: per-request, per-loop-iteration, per-mount, per-event. A one-shot acquire on a process that exits immediately is at most Low — process exit reclaims it; say so. No acquisition site, no skipped path, no driver → no finding.

| Class | What to hunt | Evidence to construct |
| --- | --- | --- |
| **unclosed-handle** | A file/socket/stream/DB-connection/cursor acquired with no guaranteed close on **all** paths — no `with`/`try-finally`/`defer`/`using`/RAII wrapping the acquisition | The acquire site, the path (usually error/early-return) where close is skipped, the driver, and the guaranteed-release construct that closes it on every path |
| **pool-exhaustion** | A connection/thread/handle borrowed from a pool and not returned on the error path, accumulating until the pool empties | The borrow site, the path where the handle is not returned, the driver, and the `finally`-return that releases it back |
| **listener-subscription-leak** | An event listener/observer/signal-handler/subscription added with no matching removal on teardown, growing per mount/request/iteration | The add site, the missing removal, the per-X driver, and the teardown-hook removal that pairs it |
| **orphaned-task** | A goroutine/thread/async-task/timer/interval started with no cancellation or join path — fire-and-forget outliving its context | The start site, the absent cancellation, the driver, and the cancellation/join that bounds its lifetime |
| **context-leak** | A cancellation token / context / scope not propagated or cancelled, keeping downstream work and its resources alive | The un-cancelled context, what it keeps alive downstream, the driver, and the propagation/cancel that releases it |
| **temp-artifact-leak** | A temp file/dir/lock-file created without cleanup on the error path | The create site, the path where cleanup is skipped, the driver, and the cleanup (unlink/remove/release) that runs on every path |
| **native-resource-leak** | A native/FFI handle or a `Disposable`/`Closeable`/`AutoCloseable` released non-deterministically — relying on GC/finalizer for a scarce resource | The acquire site, the non-deterministic release path, the driver, and the deterministic-dispose (`using`/`try-with-resources`/explicit `dispose`) fix |

## Process

1. **Map the acquisition sites and the paths that must release.** Enumerate every resource acquisition: file/socket/stream opens, DB connection and cursor creation, pool borrows, event-listener/subscription registrations, task/goroutine/thread/timer starts, context/scope creation, temp-file/lock creation, native/FFI/Disposable handles. For each, name the driver (per-request, per-loop, per-mount, per-event, or one-shot) and trace every path out of the acquisition to its release. An acquisition site left untraced is recorded in the response summary as unexamined, naming a concrete blocker (unreadable generated code, missing source, no access) — effort savings is not a blocker, and a silently skipped acquisition is a defect in the audit itself.
2. **Probe leak/handle tools — never install.** Probe with `which` and manifest inspection: handle/fd inspectors (lsof, `/proc/<pid>/fd`), leak detectors already in the manifest (valgrind, LeakSanitizer, tracemalloc, Go's `-race`/pprof goroutine dump, Node `--trace-warnings`/`process._getActiveHandles`), linters that flag unclosed resources (ruff/flake8 resource rules, eslint teardown rules). Report what is available in the summary. Absent tools stay absent — reason from the code.
3. **Hunt every defect class on every traced path.** For each candidate:
   - Confirm the acquisition and read EVERY path out of it — the happy path, each early return, each raised/thrown branch, each break/continue. The error path decides.
   - Verify no guaranteed-release construct already covers it: `with`/`try-finally`/`defer`/`using`/`try-with-resources`/RAII, or an existing teardown/cleanup hook. "Probably closed somewhere" is banned; the path decides.
   - Name the accumulation driver and confirm it repeats. A one-shot acquire on an exiting process is at most Low — grade it so, do not dismiss it and do not inflate it.
   - A candidate failing any of these is dropped. It is not a finding.
4. **File findings** via the store protocol in `_conventions.md`, using `--auditor leaks`. `## Evidence` names the class, the acquisition site → leaking path (file:line), the specific path where release is skipped, and the driver; `## Impact` names what resource is exhausted and at what scale; `## Fix` the concrete guaranteed-release change. Then follow the shared run protocol: summary (include tools used and unexamined acquisition sites), apply-fixes prompt, commit gate.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | A leak on a per-request or per-event path that exhausts a finite resource (file-descriptor limit, connection pool) and downs the service under normal traffic |
| High | A leak on a repeated path with a real driver that degrades the process over time — unbounded listener/subscription growth, orphaned goroutines/threads accumulating |
| Medium | A leak only on the error path of a frequently-failing operation; temp-artifact accumulation with a real driver |
| Low | A leak on a bounded or one-shot path (startup, a CLI that acquires once and exits) where process exit reclaims it — named as such |
| Advisory | Non-deterministic release (GC/finalizer) of a scarce resource with no measured accumulation yet, on a path with a named, realistic route to repetition |

## Fix strategy

**Auto-applicable:**

- Wrap an acquisition in the language's guaranteed-release construct — `with`, `try-finally`, `defer`, `using`, `try-with-resources`
- Return a pooled resource in a `finally` so the error path releases it back to the pool
- Add the missing `removeEventListener`/`unsubscribe`/`off` to the **existing** teardown/cleanup hook that pairs the add site
- Add the missing temp-file/lock cleanup (unlink/remove/release) inside the same `finally` that guards the create site

**Requires explicit approval per change:**

- Adding cancellation or a join to an orphaned task — changes lifecycle and shutdown behavior; name the change in the finding
- Introducing a teardown/lifecycle hook where none exists — new structure, not a wrap of existing code
- Propagating or cancelling a context that downstream code depends on — name the downstream effect

**Never:**

- Replace a real deterministic close with reliance on GC/finalizer — that is not a fix, it is often the defect
- Add a dependency — no leak-detector libraries, no handle-tracking frameworks. Absent tools stay absent

## Common mistakes

These rationalizations are forbidden:

- **"It's probably closed somewhere."** Read every path out of the acquisition — the error path decides. "Probably" is banned in both directions: filing a leak the code demonstrably closes in a `finally` is a junk finding; dismissing one it demonstrably skips on the raise path is silent approval of a real defect.
- **"GC will collect it, so it's fine."** GC does not release file descriptors, sockets, or locks deterministically — a finalizer runs whenever the collector decides, far too late for a scarce resource under load. For a scarce resource, GC reliance is often the defect itself.
- **"This leaks, but only on the error path nobody hits."** A frequently-erroring operation hits its error path constantly — a failing dependency, a timing-out call, a validation that rejects most input. Name the driver and grade it.
- **"It's a short-lived process, so leaks don't matter."** True only for a genuinely one-shot exit path — say so and grade it Low. Do not extend that reasoning to a long-running service, where every per-request leak accumulates until the process dies.
- **"This unbounded cache is a leak."** No — a cache with no eviction policy is unbounded growth by design, which is `/nitpicker perf` territory. One line routing it there, then back. Your scope is acquire-without-release, not grow-without-bound.
- **"The pool is exhausted, so it's a perf problem."** Decide and state which. Borrowed handles not RETURNED on the error path → yours, file it as pool-exhaustion. Handles returned correctly but pool too small for the load → `/nitpicker perf`; route it and say so.
- **"I found a swallowed exception too, I'll fix the catch here."** The swallowed error is `/nitpicker errors` scope; you own the resource orphaned when that error unwinds. One line naming the route, then back to hunting leaks — do not fix the catch.
- **"This acquisition looks fine, so I'll skip tracing its error path."** Every path out of the acquisition is read. A leak lives on exactly the path you did not read. A silently skipped acquisition site is an unfiled finding.
