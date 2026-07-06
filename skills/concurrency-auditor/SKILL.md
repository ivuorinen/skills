---
name: concurrency-auditor
description: 'Hostile single-shot concurrency-safety audit — hunts race conditions, check-then-act TOCTOU, deadlock risk, lost updates, unsafe publication, shared state corrupted across await, and non-atomic compound operations on thread-safe containers, each finding naming the shared state, the concurrent contexts that reach it, the corrupting interleaving, and a concrete fix. Use when auditing a codebase for concurrency defects, asked "is this thread-safe", "find race conditions", "check for deadlocks", or when adversarial-reviewer routes a concurrency finding here. Triggers: "concurrency audit", "run concurrency-auditor".'
---

# Concurrency Auditor

## Overview

Hostile single-shot concurrency-safety audit. Assume every piece of state reachable from two or more concurrent execution contexts is corrupted until a happens-before edge proves otherwise. Hunt seven defect classes — race conditions on shared mutable state, check-then-act TOCTOU, deadlock risk from inconsistent lock order, lost updates on read-modify-write, unsafe publication without a memory barrier, mutable state shared across `await` points, and non-atomic compound operations on "thread-safe" containers — and file each with the shared state, the ≥2 concurrent contexts that reach it, the interleaving that corrupts it, and a concrete synchronization fix. Speculation is banned: "this looks racy" is not a finding; every finding names the shared state, two concrete concurrent contexts that actually reach it, and the interleaving that corrupts. Static-first: reasons from the code and uses an installed race detector or thread-safety analyzer only when one is already present and cheap to run, never adding one. All findings are graded Critical → Advisory and written to `docs/audit/concurrency-auditor-findings.md`.

## When to Use

- Auditing a codebase for concurrency defects before a release, a scale-out to multiple workers, or a move from single- to multi-threaded execution
- When asked "is this thread-safe", "find race conditions", "check for deadlocks", or "run a concurrency audit"
- When `adversarial-reviewer` (or any other skill) routes a concurrency finding here
- After adding shared mutable state reachable from concurrent contexts — a request-scoped singleton, a module global touched by handlers, a field mutated across an `await`

**When NOT to use:** lock contention as a throughput problem → `perf-auditor`; a blocking/sync call stalling an async event loop → `perf-auditor` (its `sync-in-async` class owns the blocking itself; concurrency-auditor owns only shared-state corruption *across* an await, not the stall the blocking causes — that split is load-bearing, keep it); ordinary single-threaded logic bugs → `adversarial-reviewer`; whether a database *migration* is concurrency-safe to apply → `migration-auditor`; whole-repo defect audit → `nitpicker`. A racy-looking construct with no second concurrent context reaching the state is out of scope here and everywhere — do not route it, drop it.

## Defect Classes

File a finding only when the class, the shared state, ≥2 concrete concurrent contexts that reach it, and the corrupting interleaving are all named. A concurrent context is a thread, goroutine, async task, signal handler, or a request handler sharing a global/singleton. Single-threaded code, request-local state, and immutable state are NOT findings — no shared state plus two contexts plus an interleaving means no finding. "It looks racy" and "this is probably called concurrently" are not evidence; the two reaching contexts and the interleaving decide.

| Class | What to hunt | Evidence to construct |
|-------|--------------|------------------------|
| **race-condition** | Unsynchronized access to shared mutable state from ≥2 concurrent contexts (threads, goroutines, async tasks, signal handlers, request handlers sharing a global/singleton) | The shared state, the ≥2 contexts that reach it, the corrupting interleaving, and the synchronization fix |
| **check-then-act** | Non-atomic TOCTOU: a condition checked then acted on without holding a lock across both (get-or-create, exists-then-write, balance-check-then-debit) | The check site, the act site, the window between them, and the atomic replacement |
| **deadlock-risk** | Locks acquired in inconsistent order across call sites; nested/re-entrant acquisition; a lock held across a blocking call or callback that can re-enter | The two acquisition orders (or the held-across-blocking site) and the ordering/scoping fix |
| **lost-update** | Read-modify-write on shared state without atomicity (`counter++`, non-atomic accumulation, non-transactional DB read-modify-write) | The RMW site, the concurrent writers, and the atomic/transactional fix |
| **unsafe-publication** | An object shared across threads with no happens-before edge — missing volatile/memory-barrier/final, or a partially-constructed object escaping | The publish site, the reader, and the memory-visibility fix |
| **async-shared-state** | Mutable state shared across `await` points or concurrent tasks where an interleaving corrupts it (a field mutated across an await in a shared service; two asyncio tasks racing on a dict) | The state, the await/task boundary, the interleaving, and the fix |
| **non-atomic-compound-op** | A compound operation on a "thread-safe" container that is atomic per-call but not across calls (ConcurrentDictionary two-step; atomic-map get-then-put) | The two calls, the gap between them, and the single-atomic-operation replacement |

## Process

```
0. Re-validate existing findings
   If docs/audit/concurrency-auditor-findings.md exists, re-check each finding with Status: Open
   against the current code:
   - Code path changed and the state is no longer shared, or the fix landed → Fixed (record date)
   - Finding was wrong (state is request-local, a lock already covers both sites) → Invalid (record why)
   - Still present → leave Open. Never carry a finding forward without re-checking it.

1. Map the concurrent execution model and the shared state
   Enumerate every source of concurrency: thread pools, goroutines, async task spawns, signal
   handlers, and request handlers sharing process-level state (globals, singletons, module-level
   caches, connection pools). For each, name the mutable state it can reach and classify that
   state shared-across-contexts or context-local (context-local = request-local, thread-local,
   stack-local, immutable). Every finding must sit on state proven reachable from ≥2 contexts.
   A concurrency source left unexamined is recorded as an `Unexamined:` Summary bullet naming a
   concrete blocker (unreadable generated code, missing source, no access) — effort savings is not
   a blocker, and a silently skipped source is a defect in the audit itself.

2. Probe race-detection tools — never install
   Probe with `which` and manifest inspection: race detectors (`go test -race`, ThreadSanitizer,
   Helgrind), static analyzers (`go vet`, Infer, `-Wthread-safety`), and language-stdlib checks.
   Record what is available in the Summary. Run one only when it is already installed and cheap to
   invoke. Tools that are absent stay absent — reason from the code and the memory model instead.

3. Hunt every defect class on every shared-state site
   Work the Defect Classes table. For each candidate:
   a. Trace the state to its declaration and confirm ≥2 concurrent contexts reach it.
   b. Read the actual access — verify no existing lock, atomic type, transaction, or memory
      barrier already establishes the happens-before edge. Read the lock scope, the field's
      declared atomicity/volatility, the container's per-call vs cross-call guarantees.
      "Probably synchronized" and "probably single-threaded" are both banned; the code decides.
   c. Construct the corrupting interleaving: name context A's step, context B's step, and the
      order in which they produce corruption, a lost write, a hang, or a stale read.
   d. Candidate fails a, b, or c → drop it. It is not a finding.

4. File findings
   Assign the next CC-NNN id. Record class, path (the two contexts → the shared state, file:line),
   state, the interleaving, impact, and the concrete fix.

5. Write docs/audit/concurrency-auditor-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.

6. Present summary — finding counts by severity, tools used, unexamined concurrency sources —
   then ask: "Apply fixes? (a)ll auto-applicable  (c)ritical-and-high only  (n)o"
   Apply in severity order, Critical first. Only the Fix Strategy auto-applicable list
   is eligible through this prompt; every other fix stays a proposal in its finding and
   is applied only when the user approves that specific change by name.

7. Commit gate
   Fix edits are left in the working tree unstaged. Ask: "Commit findings to git? (y/n)" —
   on yes, stage only docs/audit/concurrency-auditor-findings.md. Never commit silently.
```

## Findings Format

Output path: `docs/audit/concurrency-auditor-findings.md`

```
# Concurrency Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Concurrency sources examined: N | Unexamined: N
- Race-detection tools available: <comma-separated list, or none>
- Unexamined: <concurrency source> — <why not examined>

## Open Findings

### Critical

#### [CC-NNN] Short title
Status: Open
Class: <race-condition|check-then-act|deadlock-risk|lost-update|unsafe-publication|async-shared-state|non-atomic-compound-op>
Path: <the ≥2 concurrent contexts → the shared state, file:line>
State: <the shared mutable state and its declaration site>
Interleaving: <context A's step, context B's step, and the order that corrupts>
Impact: <what corrupts, hangs, or is lost, and on which path>
Fix: <the concrete change — lock scope, atomic type, atomic API, transaction, memory barrier>

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

#### [CC-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <what changed, and the re-check showing the interleaving is no longer reachable>

## Invalid

### Pass N — YYYY-MM-DD

#### [CC-NNN] Short title
Notes: <why the finding was wrong — state is context-local, existing lock covers both sites, immutable>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the other `## Summary` bullets after it. Keep the Total line in exactly that shape and insert no field into it. All supplementary bullets (`Concurrency sources examined`, `Race-detection tools available`, `Unexamined:`) follow the Total line; unexamined concurrency sources live as `Unexamined:` Summary bullets, never in a separate section. All fixed findings go under one `## Fixed` h2 and all invalid findings under one `## Invalid` h2, sub-divided by `### Pass N — YYYY-MM-DD` h3 headers — never `## Fixed — pass N` variants, never h2 → h4 without an h3.

The per-finding `Status:` field is `Open` for a verified, still-present finding; on moving a finding to Fixed or Invalid, drop the `Status:` line. Step 0 re-validation re-checks every finding with `Status: Open`. Finding ID format: `CC-NNN` (zero-padded to 3 digits). Assign sequentially from the highest existing ID; never reuse an ID, even after Fixed or Invalid.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | Data-corrupting or money-path race reachable on the normal concurrent path (request handlers sharing mutable state, a balance debit under concurrent requests); a deadlock reachable under normal load that hangs the service |
| High | Lost update on persisted state under concurrent writers; check-then-act with a realistic window on a correctness-critical path that is not money or data-corrupting (those are Critical) |
| Medium | Race on non-persisted state that degrades correctness; unsafe publication with a plausible reader |
| Low | Race only under a contrived interleaving on a bounded or admin-only path |
| Advisory | Theoretical publication/visibility issue on a path that is single-threaded today, with a named realistic path to concurrency |

## Fix Strategy

**Auto-applicable (ask first via the step 6 prompt, apply only on approval):**
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
- Apply any fix before the step 6 prompt
- Commit anything silently

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"It looks racy, so I'll file it without proving two contexts reach it."** No shared state plus ≥2 concrete concurrent contexts plus a corrupting interleaving means no finding. A construct that looks racy but is only ever touched by one context is not a defect. Filing unproven races is junk-finding inflation, and junk findings train users to ignore the report.

**"This is probably fine because it's usually single-threaded."** "Probably single-threaded" is not evidence. Prove the concurrency — name the two contexts that reach the state — or drop the finding. Dismissing a real race because the path "feels" serial is silent approval of a defect that ships under load.

**"I'll add a lock to be safe."** New locks are approval-gated, not auto-applicable — a lock added without tracing acquisition order is a fresh deadlock. Every new lock names its acquisition order in the finding and waits for explicit per-change approval.

**"A sleep or retry fixes the race."** Banned outright. Sleeps and retries widen or narrow the window; they never close it. The fix establishes a happens-before edge — a lock scope, an atomic type, an atomic API, a transaction, a memory barrier — never a timing hack.

**"The container is thread-safe, so the compound operation is too."** Per-call atomicity is not cross-call atomicity. A `ConcurrentDictionary` `get` then `put`, or an atomic-map contains-then-insert, has a gap between the two atomic calls where another context corrupts the invariant. Read the container's cross-call guarantee before dismissing.

**"This blocking call in async is mine to fix."** No. A sync/blocking call stalling the event loop routes to `perf-auditor`'s `sync-in-async` class. This skill owns only shared-state corruption *across* an await — the stall itself is out of scope. One line naming the route, then back to hunting shared state.

**"I found a logic bug and an injection hole too — I'll note them here since I found them."** Out of scope. One line naming the route (`adversarial-reviewer` for the logic bug, `security-auditor` for the injection hole), then back to hunting concurrency defects.

**"Last pass's findings are surely still valid — skip step 0."** Every `Status: Open` finding is re-checked against current code every run. Code moves; a lock added elsewhere may already cover both sites, and a stale Open finding sends the user chasing a fixed defect while a silently-fixed one never reaches the Fixed ledger.

**"I'll apply the obvious atomic fix as I go."** No fix is applied before the step 6 summary and prompt. Even the auto-applicable list waits for the answer. Fixes applied mid-hunt bypass the approval gate and contaminate re-validation.

**"The interleaving is obvious — I'll skip writing it out."** The Interleaving field is mandatory and concrete: context A's step, context B's step, and the order that corrupts. A finding that asserts a race without showing the interleaving is unfalsifiable and cannot be re-validated in step 0.
