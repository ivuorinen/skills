---
name: perf-auditor
description: 'Hostile single-shot performance audit — hunts N+1 queries, O(n²)+ hotspots on real data paths, sync-blocking calls in async contexts, unbounded caches/queues/retries, missing pagination, and chatty per-item I/O, each finding naming the growth driver and a concrete fix. Use when auditing a codebase for performance defects, asked why something is slow at scale, or when complexity-hunter routes a performance finding here. Triggers: "perf audit", "find performance issues", "run perf-auditor".'
---

# Perf Auditor

## Overview

Hostile single-shot performance audit. Assume every data path degrades superlinearly until traced and proven otherwise. Hunt seven defect classes — N+1 queries, O(n²)+ hotspots on real data paths, sync-blocking calls in async contexts, unbounded caches/queues/retries, missing pagination on unbounded result sets, loop-invariant work redone per iteration, and chatty per-item I/O that batches — and file each with the exact code path, the growth driver (the input that makes it slow), and a concrete fix. Speculation is banned: "this might be slow" is not a finding; every scaling claim carries its demonstration — complexity reasoning from the code always, a measurement with an installed tool when the claim is contestable. Uses installed profiling and measurement tools when present; never adds a dependency. All findings are graded Critical → Advisory and written to `docs/audit/perf-auditor-findings.md`.

## When to Use

- Auditing a codebase for performance defects before a release, a traffic increase, or a data-volume increase
- When asked "why is this slow", "find performance issues", "will this scale", or "run a perf audit"
- When `complexity-hunter` (or any other skill) routes a performance finding here
- After adding a data path that fans out per item — loops over query results, per-item API calls, per-file network writes

**When NOT to use:** correctness bugs → `adversarial-reviewer`; security → `security-auditor`; over-engineering and bloat → `complexity-hunter`; whole-repo defect audit → `nitpicker`. Micro-optimizations without a growth driver are out of scope here and everywhere — do not route them, drop them.

## Defect Classes

File a finding only when the class, the traced code path, and the growth driver are all named. A driver is an input whose size the deployment does not bound: user-submitted data, table rows, files on disk, items in an external feed. An input is bounded only when its bound is fixed at deploy time and independent of data volume — config constants, enum members, schema-fixed column counts. "Usually small" and "bounded by a config default the operator raises" are not bounded; a data-dependent size is a driver.

| Class | What to hunt | Evidence to construct |
|-------|--------------|------------------------|
| **n-plus-one** | A query/fetch inside a loop over a result set, where a batch form exists (JOIN, `IN`, `prefetch`, bulk API) | The loop, the per-iteration query, the driver sizing the loop, and the batch call that replaces it |
| **quadratic-hotspot** | O(n²)+ work (nested loops over the same driver, membership scan of a list inside a loop, repeated sort) on a traced entry-point path | Both loops/scans, the shared driver, and the O(n)/O(n log n) replacement |
| **sync-in-async** | A blocking call (sync HTTP client, blocking file/DB read, `sleep`) inside an async handler, coroutine, or event-loop callback | The blocking call site, the event loop it stalls, and the async equivalent or executor offload |
| **unbounded-growth** | A cache, queue, buffer, or in-memory index with no size bound or eviction; a retry loop with no cap or backoff | The insertion site, the absent bound, the driver filling it, and the exact bound/eviction/cap to add |
| **missing-pagination** | A query or list endpoint returning an unbounded result set in one response or one fetch | The query, the driver sizing the result, and the pagination/limit mechanism the framework provides |
| **loop-invariant-work** | Work inside a loop whose result is identical every iteration — compilation, parsing, connection setup, a constant-input computation | The invariant expression, the loop's driver, and the hoisted form |
| **chatty-io** | Per-item network or disk round-trips over a driver-sized collection, where a batch/bulk/streaming form exists | The per-item call, the round-trip count as a function of the driver, and the batch form |

## Process

```
0. Re-validate existing findings
   If docs/audit/perf-auditor-findings.md exists, re-check each finding with Status: Open
   against the current code:
   - Code path changed and the driver no longer reaches it, or the fix landed → Fixed (record date)
   - Finding was wrong (input is bounded, batching already existed) → Invalid (record why)
   - Still present → leave Open. Never carry a finding forward unre-checked.

1. Map the real data paths
   Enumerate every entry point: HTTP/RPC handlers, CLI commands, scheduled jobs, queue/event
   consumers, startup/init paths. For each, name the inputs it carries and classify each input
   bounded or unbounded (unbounded = user data, table rows, file sets, external feeds).
   Every finding must sit on a path traced from an entry point. An entry point left untraced
   is recorded as an `Unexamined:` Summary bullet naming a concrete blocker (unreadable
   generated code, missing source, no access) — effort savings is not a blocker, and a
   silently skipped entry point is a defect in the audit itself.

2. Probe measurement tools — never install
   Probe with `which` and manifest inspection: profilers (py-spy, perf, pprof), benchmark
   runners (hyperfine, `go test -bench`, pytest-benchmark), DB `EXPLAIN`, language-stdlib
   timing (`timeit`, `cProfile`, `console.time`). Record what is available in the Summary.
   Tools that are absent stay absent — reason from the code instead.

3. Hunt every defect class on every traced path
   Work the Defect Classes table. For each candidate:
   a. Trace the driver to its source and confirm it is unbounded.
   b. Read the actual call — verify no existing batching, caching, pagination, or bound
      already neutralizes it. Read the ORM call signature, the cache constructor, the query.
      "Probably batched" and "probably bounded" are both banned; the call site decides.
   c. Demonstrate the scaling claim: complexity reasoning from the code (always cheap —
      always included), plus a measurement when the claim is contestable, i.e. the reasoning
      rests on an unverified runtime assumption (query uses an index, library call is O(1))
      checkable with an installed tool, EXPLAIN, or the library source. Cite tool and number.
   d. Candidate fails a, b, or c → drop it. It is not a finding.

4. File findings
   Assign the next PA-NNN id. Record class, path (entry point → hot code, file:line), driver,
   cost (the complexity reasoning or measurement), impact, and the concrete fix.

5. Write docs/audit/perf-auditor-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.

6. Present summary — finding counts by severity, tools used, unexamined entry points —
   then ask: "Apply fixes? (a)ll auto-applicable  (c)ritical-and-high only  (n)o"
   Apply in severity order, Critical first. Only the Fix Strategy auto-applicable list
   is eligible through this prompt; every other fix stays a proposal in its finding and
   is applied only when the user approves that specific change by name.

7. Commit gate
   Fix edits are left in the working tree unstaged. Ask: "Commit findings to git? (y/n)" —
   on yes, stage only docs/audit/perf-auditor-findings.md. Never commit silently.
```

## Findings Format

Output path: `docs/audit/perf-auditor-findings.md`

```
# Perf Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Entry points traced: N | Unexamined: N
- Measurement tools available: <comma-separated list, or none>
- Unexamined: <entry point> — <why not traced>

## Open Findings

### Critical

#### [PA-NNN] Short title
Status: Open
Class: <n-plus-one|quadratic-hotspot|sync-in-async|unbounded-growth|missing-pagination|loop-invariant-work|chatty-io>
Path: <entry point → hot code, file:line>
Driver: <the unbounded input and its source>
Cost: <complexity reasoning, or measurement with tool and number>
Impact: <what degrades and at what scale>
Fix: <the concrete change — batch call, bound, hoist, pagination mechanism>

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

#### [PA-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <what changed, and the re-check showing the driver no longer bites>

## Invalid

### Pass N — YYYY-MM-DD

#### [PA-NNN] Short title
Notes: <why the finding was wrong — bounded input, existing batching, dead path>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the other `## Summary` bullets after it. Keep the Total line in exactly that shape and insert no field into it. All supplementary bullets (`Entry points traced`, `Measurement tools available`, `Unexamined:`) follow the Total line; unexamined entry points live as `Unexamined:` Summary bullets, never in a separate section. All fixed findings go under one `## Fixed` h2 and all invalid findings under one `## Invalid` h2, sub-divided by `### Pass N — YYYY-MM-DD` h3 headers — never `## Fixed — pass N` variants, never h2 → h4 without an h3.

The per-finding `Status:` field is `Open` for a verified, still-present finding; on moving a finding to Fixed or Invalid, drop the `Status:` line. Step 0 re-validation re-checks every finding with `Status: Open`. Finding ID format: `PA-NNN` (zero-padded to 3 digits). Assign sequentially from the highest existing ID; never reuse an ID, even after Fixed or Invalid.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | O(n²)+ or per-item round-trip work on an unbounded driver on a hot production path (request handling, job processing); unbounded in-memory growth (cache/queue/buffer with no bound) that a normal workload fills until the process dies |
| High | N+1 query on an unbounded result set; sync-blocking call inside an async request path or event loop; missing pagination on an unbounded result set exposed to callers; unbounded retries against a failing dependency |
| Medium | Loop-invariant work redone per iteration over an unbounded driver; chatty disk I/O with an available batch form; retry loop capped but without backoff |
| Low | Superlinear work on an input bounded today by deployment reality, with a named, realistic path to unbounded (the finding names that path) |
| Advisory | Demonstrated-but-minor cost on a cold path (startup, admin-only, one-shot migration) with a real driver |

## Fix Strategy

**Auto-applicable (ask first via the step 6 prompt, apply only on approval):**
- Hoist loop-invariant work out of the loop
- Replace a per-item query with the batch form the same API already exposes (`IN` clause, `prefetch`/`select_related`, bulk fetch)
- Replace list-membership-in-loop with a set/dict lookup
- Add a size bound to an unbounded cache (`maxsize`) or an explicit cap to an unbounded retry loop
- Buffer per-item disk writes into one batched write within the same function

**Requires explicit approval per change:**
- Adding pagination (changes the API contract for callers)
- Converting a sync call to its async equivalent or offloading to an executor (changes control flow)
- Adding cache eviction policy, backoff strategy, or a DB index
- Any fix that changes observable output ordering, timing guarantees, or error behavior — state the behavior change in the finding

**Never:**
- Add a dependency — no profilers, no benchmark harnesses, no faster-X libraries. Absent tools stay absent
- Trade observable behavior for speed without the user approving the named behavior change
- Apply a fix for a finding that lacks a traced driver
- Commit anything silently

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"It looks O(n²), so I'll file it without tracing the data size."** A nested loop over a config list or enum members is O(bounded²) = O(1). No finding exists until the driver is traced to an unbounded source. Filing untraced complexity is junk-finding inflation, and junk findings train users to ignore the report.

**"Demonstrating the claim is too much work — I'll write that it might be slow."** Speculation is banned outright. Complexity reasoning from the code costs minutes and is always included; when the claim is contestable, an installed tool or `EXPLAIN` settles it. A finding without its Cost field is not filed.

**"I'll sample the hot-looking directories — handlers and controllers — the rest is probably fine."** Every entry point is traced or recorded as `Unexamined:` with a reason. Jobs, consumers, and startup paths hide the worst N+1s precisely because nobody watches them. A silently skipped path is an unfiled finding.

**"This micro-optimization counts as a finding — more findings look thorough."** No growth driver, no finding. String-concat style, `++` vs `+= 1`, one avoidable allocation on a bounded path: drop them without routing them anywhere. Report volume is not report quality.

**"No profiler is installed, so I'll install one real quick."** Never. Probe, use what exists (including language-stdlib timing), and reason from the code for the rest. Adding a dependency to audit a repo mutates the repo under audit.

**"The ORM probably batches this / the cache probably has a bound."** "Probably" is banned in both directions. Read the call signature and the constructor before filing and before dismissing. Filing an N+1 the ORM demonstrably prefetches is a junk finding; dismissing one it demonstrably does not batch is silent approval of a real defect.

**"This slow loop also has a bug and an injection hole — I'll review those here since I found them."** Out of scope. One line naming the route (`adversarial-reviewer` for the bug, `security-auditor` for the hole), then back to hunting performance.

**"I'll apply the obvious fixes as I go."** No fix is applied before the step 6 summary and prompt. Even the auto-applicable list waits for the answer. Fixes applied mid-hunt bypass the approval gate and contaminate re-validation.

**"Last pass's findings are surely still valid — skip step 0."** Every `Status: Open` finding is re-checked against current code every run. Code moves; a stale Open finding sends the user chasing a fixed defect, and a silently-fixed one never reaches the Fixed ledger.

**"The faster algorithm changes output ordering, but nobody will notice."** Behavior changes ride only on explicit approval with the change named in the finding. A perf fix that reorders results or alters error timing is a correctness change wearing a perf hat.
