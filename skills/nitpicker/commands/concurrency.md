# /nitpicker concurrency — Concurrency Auditor

Hostile single-shot concurrency-safety audit: assume every piece of state reachable from two or more concurrent execution contexts is corrupted until a happens-before edge proves otherwise, and file each defect with the shared state, the contexts that reach it, the corrupting interleaving, and a concrete synchronization fix.

## When to use

- "concurrency audit", "is this thread-safe", "find race conditions", "check for deadlocks"
- Before a release, a scale-out to multiple workers, or a move from single- to multi-threaded execution
- After adding shared mutable state reachable from concurrent contexts — a request-scoped singleton, a module global touched by handlers, a field mutated across an `await`
- When `/nitpicker review` (or any other command) routes a concurrency finding here

Run standalone or by the `/nitpicker` default audit flow.

**Not this command:** lock contention as a throughput problem → `/nitpicker perf`; a blocking/sync call stalling an async event loop → `/nitpicker perf` (its `sync-in-async` class owns the blocking itself; this command owns only shared-state corruption _across_ an await, not the stall the blocking causes — that split is load-bearing, keep it); ordinary single-threaded logic bugs → `/nitpicker review`; whether a database _migration_ is concurrency-safe to apply → `/nitpicker migrations`; whole-repo defect audit → `/nitpicker audit`. A racy-looking construct with no second concurrent context reaching the state is out of scope here and everywhere — do not route it, drop it.

## Mindset

Speculation is banned: "this looks racy" is not a finding; every finding names the shared state, two concrete concurrent contexts that actually reach it, and the interleaving that corrupts. Static-first: reason from the code and use an installed race detector or thread-safety analyzer only when one is already present and cheap to run — never add one.

## Defect classes

File a finding only when the class, the shared state, ≥2 concrete concurrent contexts that reach it, and the corrupting interleaving are all named. A concurrent context is a thread, goroutine, async task, signal handler, or a request handler sharing a global/singleton. Single-threaded code, request-local state, and immutable state are NOT findings.

| Class                      | What to hunt                                                                                                                                                                               | Evidence to construct                                                                                     |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| **race-condition**         | Unsynchronized access to shared mutable state from ≥2 concurrent contexts (threads, goroutines, async tasks, signal handlers, request handlers sharing a global/singleton)                 | The shared state, the ≥2 contexts that reach it, the corrupting interleaving, and the synchronization fix |
| **check-then-act**         | Non-atomic TOCTOU: a condition checked then acted on without holding a lock across both (get-or-create, exists-then-write, balance-check-then-debit)                                       | The check site, the act site, the window between them, and the atomic replacement                         |
| **deadlock-risk**          | Locks acquired in inconsistent order across call sites; nested/re-entrant acquisition; a lock held across a blocking call or callback that can re-enter                                    | The two acquisition orders (or the held-across-blocking site) and the ordering/scoping fix                |
| **lost-update**            | Read-modify-write on shared state without atomicity (`counter++`, non-atomic accumulation, non-transactional DB read-modify-write)                                                         | The RMW site, the concurrent writers, and the atomic/transactional fix                                    |
| **unsafe-publication**     | An object shared across threads with no happens-before edge — missing volatile/memory-barrier/final, or a partially-constructed object escaping                                            | The publish site, the reader, and the memory-visibility fix                                               |
| **async-shared-state**     | Mutable state shared across `await` points or concurrent tasks where an interleaving corrupts it (a field mutated across an await in a shared service; two asyncio tasks racing on a dict) | The state, the await/task boundary, the interleaving, and the fix                                         |
| **non-atomic-compound-op** | A compound operation on a "thread-safe" container that is atomic per-call but not across calls (ConcurrentDictionary two-step; atomic-map get-then-put)                                    | The two calls, the gap between them, and the single-atomic-operation replacement                          |

## Process

1. **Map the concurrent execution model and the shared state.** Enumerate every source of concurrency: thread pools, goroutines, async task spawns, signal handlers, and request handlers sharing process-level state (globals, singletons, module-level caches, connection pools). For each, name the mutable state it can reach and classify that state shared-across-contexts or context-local (context-local = request-local, thread-local, stack-local, immutable). Every finding must sit on state proven reachable from ≥2 contexts. A concurrency source left unexamined is recorded in the response summary as unexamined, naming a concrete blocker (unreadable generated code, missing source, no access) — effort savings is not a blocker, and a silently skipped source is a defect in the audit itself.
2. **Probe race-detection tools — never install.** Probe with `which` and manifest inspection: race detectors (`go test -race`, ThreadSanitizer, Helgrind), static analyzers (`go vet`, Infer, `-Wthread-safety`), and language-stdlib checks. Report what is available in the summary. Run one only when it is already installed and cheap to invoke. Absent tools stay absent — reason from the code and the memory model instead.
3. **Hunt every defect class on every shared-state site.** For each candidate:
   - Trace the state to its declaration and confirm ≥2 concurrent contexts reach it.
   - Read the actual access — verify no existing lock, atomic type, transaction, or memory barrier already establishes the happens-before edge. Read the lock scope, the field's declared atomicity/volatility, the container's per-call vs cross-call guarantees. "Probably synchronized" and "probably single-threaded" are both banned; the code decides.
   - Construct the corrupting interleaving: name context A's step, context B's step, and the order in which they produce corruption, a lost write, a hang, or a stale read.
   - A candidate failing any of these is dropped. It is not a finding.
4. **File findings** via the store protocol in `_conventions.md`, using `--auditor concurrency`. `## Evidence` names the class, the ≥2 concurrent contexts → the shared state (file:line), the state's declaration site, and the interleaving (context A's step, context B's step, and the corrupting order); `## Impact` what corrupts, hangs, or is lost, and on which path; `## Fix` the concrete change — lock scope, atomic type, atomic API, transaction, memory barrier. Then follow the shared run protocol: summary (include tools used and unexamined concurrency sources), apply-fixes prompt, commit gate.

## Severity guide

| Severity | Condition                                                                                                                                                                                                                     |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Critical | Data-corrupting or money-path race reachable on the normal concurrent path (request handlers sharing mutable state, a balance debit under concurrent requests); a deadlock reachable under normal load that hangs the service |
| High     | Lost update on persisted state under concurrent writers; check-then-act with a realistic window on a correctness-critical path that is not money or data-corrupting (those are Critical)                                      |
| Medium   | Race on non-persisted state that degrades correctness; unsafe publication with a plausible reader                                                                                                                             |
| Low      | Race only under a contrived interleaving on a bounded or admin-only path                                                                                                                                                      |
| Advisory | Theoretical publication/visibility issue on a path that is single-threaded today, with a named realistic path to concurrency                                                                                                  |

## Fix strategy

**Auto-applicable (through the apply-fixes prompt):**

- Wrap an existing read-modify-write in a lock already present in the same scope
- Replace `counter++` or manual accumulation with the language's atomic type
- Replace a check-then-act pair with the atomic API the library already exposes (`compute_if_absent`, `putIfAbsent`, `SETNX`, get-or-create)
- Guard a shared-state mutation across `await` with the async lock the codebase already uses

**Requires explicit approval per change:**

- Introducing a NEW lock — can create deadlock; name the acquisition order in the finding
- Changing lock acquisition order across call sites
- Converting shared mutable state to immutable, actor-owned, or thread-local (control-flow change)
- Wrapping a multi-step DB read-modify-write in a transaction — changes isolation/locking behavior; name the change

**Never:**

- Introduce synchronization that changes throughput or ordering guarantees without naming the change in the finding
- "Fix" a race by inserting sleeps or retries — this masks, never fixes
- Add a dependency — no race detectors, no concurrency libraries. Absent tools stay absent

## Common mistakes

These rationalizations are forbidden:

- **"It looks racy, so I'll file it without proving two contexts reach it."** No shared state plus ≥2 concrete concurrent contexts plus a corrupting interleaving means no finding. Filing unproven races is junk-finding inflation, and junk findings train users to ignore the report.
- **"This is probably fine because it's usually single-threaded."** "Probably single-threaded" is not evidence. Prove the concurrency — name the two contexts that reach the state — or drop the finding. Dismissing a real race because the path "feels" serial is silent approval of a defect that ships under load.
- **"I'll add a lock to be safe."** New locks are approval-gated, not auto-applicable — a lock added without tracing acquisition order is a fresh deadlock. Every new lock names its acquisition order in the finding and waits for explicit per-change approval.
- **"A sleep or retry fixes the race."** Banned outright. Sleeps and retries widen or narrow the window; they never close it. The fix establishes a happens-before edge — a lock scope, an atomic type, an atomic API, a transaction, a memory barrier — never a timing hack.
- **"The container is thread-safe, so the compound operation is too."** Per-call atomicity is not cross-call atomicity. A `ConcurrentDictionary` `get` then `put`, or an atomic-map contains-then-insert, has a gap between the two atomic calls where another context corrupts the invariant. Read the container's cross-call guarantee before dismissing.
- **"This blocking call in async is mine to fix."** No. A sync/blocking call stalling the event loop routes to `/nitpicker perf` (`sync-in-async`). This command owns only shared-state corruption _across_ an await — the stall itself is out of scope. One line naming the route, then back to hunting shared state.
- **"I found a logic bug and an injection hole too — I'll note them here since I found them."** Out of scope. One line naming the route (`/nitpicker review` for the logic bug, `/nitpicker security` for the injection hole), then back to hunting concurrency defects.
- **"The interleaving is obvious — I'll skip writing it out."** The interleaving is mandatory and concrete in every finding's Evidence: context A's step, context B's step, and the order that corrupts. A finding that asserts a race without showing the interleaving is unfalsifiable and cannot be re-validated on the next run.
