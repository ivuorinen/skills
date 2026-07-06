# concurrency-auditor

Hostile single-shot concurrency-safety audit. Assumes every piece of state reachable from two or more concurrent execution contexts is corrupted until a happens-before edge proves otherwise. Hunts seven defect classes — race conditions on shared mutable state, check-then-act TOCTOU, deadlock risk from inconsistent lock order, lost updates on read-modify-write, unsafe publication without a memory barrier, mutable state shared across `await` points, and non-atomic compound operations on "thread-safe" containers. Speculation is banned: every finding names the shared state, two concrete concurrent contexts that actually reach it, and the interleaving that corrupts it. Static-first: reasons from the code and uses an installed race detector only when one is already present and cheap to run, never adding one.

## When to Use

- "audit concurrency" / "find race conditions" / "check for deadlocks" / "is this thread-safe"
- Before a release, a scale-out to multiple workers, or a move from single- to multi-threaded execution
- After adding shared mutable state reachable from concurrent contexts — a request-scoped singleton, a module global touched by handlers, a field mutated across an `await`
- When [adversarial-reviewer] (or any other skill) routes a concurrency finding here

**When NOT to use:**
- Lock contention as a throughput problem, or a blocking/sync call stalling an async event loop → use [perf-auditor]
- Ordinary single-threaded logic bugs → use [adversarial-reviewer]
- Whether a database migration is concurrency-safe to apply → use [migration-auditor]
- Whole-repo defect audit → use [nitpicker]

A racy-looking construct with no second concurrent context reaching the state is out of scope everywhere — do not route it, drop it.

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Every source of concurrency (thread pools, goroutines, async task spawns, signal handlers, request handlers sharing process-level state); the mutable state each can reach; lock scopes, atomic types, transactions, memory barriers; installed race-detection tool output (`go test -race`, ThreadSanitizer, Helgrind, `go vet`, Infer) |
| **Writes** | `docs/audit/concurrency-auditor-findings.md` |

## How to Invoke

```
/concurrency-auditor
```

## Defect Classes

| Class | Definition |
|-------|------------|
| **race-condition** | Unsynchronized access to shared mutable state from ≥2 concurrent contexts (threads, goroutines, async tasks, signal handlers, request handlers sharing a global/singleton) |
| **check-then-act** | Non-atomic TOCTOU: a condition checked then acted on without holding a lock across both (get-or-create, exists-then-write, balance-check-then-debit) |
| **deadlock-risk** | Locks acquired in inconsistent order across call sites; nested/re-entrant acquisition; a lock held across a blocking call or callback that can re-enter |
| **lost-update** | Read-modify-write on shared state without atomicity (`counter++`, non-atomic accumulation, non-transactional DB read-modify-write) |
| **unsafe-publication** | An object shared across threads with no happens-before edge — missing volatile/memory-barrier/final, or a partially-constructed object escaping |
| **async-shared-state** | Mutable state shared across `await` points or concurrent tasks where an interleaving corrupts it |
| **non-atomic-compound-op** | A compound operation on a "thread-safe" container that is atomic per-call but not across calls (ConcurrentDictionary two-step; atomic-map get-then-put) |

## Process

```
0. Re-validate existing findings against current code
1. Map the concurrent execution model and the shared state — classify each shared-across-contexts or context-local
2. Probe race-detection tools (probe first, never install)
3. Hunt every defect class on every shared-state site — confirm ≥2 contexts, no existing happens-before edge, construct the interleaving
4. File findings: CC-NNN, class, path, state, interleaving, impact, concrete fix
5. Write docs/audit/concurrency-auditor-findings.md
6. Ask: "Apply fixes? (a)ll auto-applicable (c)ritical-and-high only (n)o" — new locks always approval-gated
7. Ask: "Commit findings to git? (y/n)" — never commit silently
```

A concurrency source left unexamined is recorded as an `Unexamined:` Summary bullet naming a concrete blocker.

## Findings Format

```
#### [CC-NNN] Short title
Status: Open
Class: <race-condition|check-then-act|deadlock-risk|lost-update|unsafe-publication|async-shared-state|non-atomic-compound-op>
Path: <the ≥2 concurrent contexts → the shared state, file:line>
State: <the shared mutable state and its declaration site>
Interleaving: <context A's step, context B's step, and the order that corrupts>
Impact: <what corrupts, hangs, or is lost, and on which path>
Fix: <the concrete change — lock scope, atomic type, atomic API, transaction, memory barrier>
```

Finding ID format: `CC-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | Data-corrupting or money-path race reachable on the normal concurrent path; a deadlock reachable under normal load that hangs the service |
| High | Lost update on persisted state under concurrent writers; check-then-act with a realistic window on a correctness-critical path that is not money or data-corrupting (those are Critical) |
| Medium | Race on non-persisted state that degrades correctness; unsafe publication with a plausible reader |
| Low | Race only under a contrived interleaving on a bounded or admin-only path |
| Advisory | Theoretical publication/visibility issue on a path single-threaded today, with a named realistic route to concurrency |

## Fix Strategy

Auto-applicable fixes (approval-gated via the step 6 prompt) reuse synchronization the codebase already has — wrapping a read-modify-write in an existing lock, replacing `counter++` with the language's atomic type, swapping a check-then-act pair for the atomic API the library already exposes. Introducing a NEW lock, changing lock acquisition order, or wrapping a multi-step DB read-modify-write in a transaction each require explicit per-change approval — a lock added without tracing acquisition order is a fresh deadlock. Sleeps and retries are never a fix; they mask the window, never close it. No dependency is ever added.

## Related Skills

- [perf-auditor] — lock contention as throughput and sync-blocking-in-async routed there
- [adversarial-reviewer] — single-threaded logic bugs routed there
- [migration-auditor] — whether a migration is concurrency-safe to apply routed there
- [security-auditor] — injection and other exploits routed there
- [nitpicker] — invokes this skill in `concurrency` mode

---

[perf-auditor]: ../perf-auditor/README.md
[adversarial-reviewer]: ../adversarial-reviewer/README.md
[migration-auditor]: ../migration-auditor/README.md
[security-auditor]: ../security-auditor/README.md
[nitpicker]: ../nitpicker/README.md
