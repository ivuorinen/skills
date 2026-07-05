# perf-auditor

Hostile single-shot performance audit. Assumes every data path degrades superlinearly until traced and proven otherwise, then hunts seven defect classes — N+1 queries, O(n²)+ hotspots on real data paths, sync-blocking calls in async contexts, unbounded caches/queues/retries, missing pagination on unbounded result sets, loop-invariant work redone per iteration, and chatty per-item I/O that batches. Every finding names the exact code path, the growth driver (the input that makes it slow), and a concrete fix; every scaling claim carries its demonstration — complexity reasoning from the code, plus a measurement with an installed tool when the claim is contestable. Uses profiling and measurement tools already present; never adds a dependency.

## When to Use

- "Perf audit" / "find performance issues" / "why is this slow" / "will this scale"
- Before a release, a traffic increase, or a data-volume increase
- After adding a data path that fans out per item — loops over query results, per-item API calls, per-file network writes
- When [complexity-hunter] (or any other skill) routes a performance finding here

**When NOT to use:**

- Correctness bugs → use [adversarial-reviewer]
- Security holes → use [security-auditor]
- Over-engineering and bloat → use [complexity-hunter]
- Whole-repo defect audit → use [nitpicker]
- Micro-optimizations without a growth driver — out of scope everywhere; they are dropped, not routed

## perf-auditor vs. complexity-hunter

| | perf-auditor | complexity-hunter |
|---|---|---|
| Question | "What gets slow as the data grows?" | "What should not be built at all?" |
| Unit of finding | A traced code path with a growth driver and a demonstrated cost | A construct to delete, with its simpler replacement |
| Output | `docs/audit/perf-auditor-findings.md`, graded Critical → Advisory | stdout one-liners, ranked by code deleted |

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Every entry point (HTTP/RPC handlers, CLI commands, jobs, queue/event consumers, startup paths) and the code paths they reach; ORM calls, cache constructors, queries; the project manifest and installed tooling (profilers, benchmark runners, `EXPLAIN`, stdlib timing) |
| **Writes** | `docs/audit/perf-auditor-findings.md` |

## How to Invoke

```
/perf-auditor
```

Re-validates existing findings first, maps every entry point and its bounded/unbounded inputs, probes for installed measurement tools (never installs any), then hunts every defect class on every traced path.

## Defect Classes

| Class | What it hunts |
|-------|---------------|
| **n-plus-one** | A query/fetch inside a loop over a result set, where a batch form exists |
| **quadratic-hotspot** | O(n²)+ work on a traced entry-point path — nested loops over the same driver, list-membership scans in a loop |
| **sync-in-async** | A blocking call inside an async handler, coroutine, or event-loop callback |
| **unbounded-growth** | A cache, queue, or buffer with no size bound or eviction; a retry loop with no cap or backoff |
| **missing-pagination** | A query or list endpoint returning an unbounded result set in one response |
| **loop-invariant-work** | Work inside a loop whose result is identical every iteration |
| **chatty-io** | Per-item network or disk round-trips over a driver-sized collection, where a batch form exists |

A finding exists only when the class, the traced path, and the growth driver are all named. An input is bounded only when its bound is fixed at deploy time and independent of data volume — "usually small" is a driver, not a bound.

## Process

```
0. Re-validate existing findings (still present → Open; fixed → Fixed; wrong → Invalid)
1. Map every entry point and classify its inputs bounded/unbounded — untraced entry points
   are recorded as Unexamined with a concrete blocker, never silently skipped
2. Probe installed measurement tools — never install anything
3. Hunt every defect class on every traced path: trace the driver, read the actual call
   (no "probably batched"/"probably bounded"), demonstrate the scaling claim
4. File findings — PA-NNN, with class, path, driver, cost, impact, fix
5. Write docs/audit/perf-auditor-findings.md
6. Ask: "Apply fixes? (a)ll auto-applicable  (c)ritical-and-high only  (n)o"
7. Ask: "Commit findings to git? (y/n)" — never commit silently
```

## Findings Format

```
# Perf Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Entry points traced: N | Unexamined: N
- Measurement tools available: <comma-separated list, or none>

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
```

Finding ID format: `PA-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused. Fixed and Invalid entries are grouped under `### Pass N — YYYY-MM-DD` h3 headers.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | O(n²)+ or per-item round-trip work on an unbounded driver on a hot production path; unbounded in-memory growth a normal workload fills until the process dies |
| High | N+1 on an unbounded result set; sync-blocking call in an async request path; missing pagination exposed to callers; unbounded retries |
| Medium | Loop-invariant work per iteration over an unbounded driver; chatty disk I/O with an available batch form; capped retries without backoff |
| Low | Superlinear work on an input bounded today, with a named, realistic path to unbounded |
| Advisory | Demonstrated-but-minor cost on a cold path (startup, admin-only, one-shot migration) with a real driver |

## Related Skills

- [complexity-hunter] — routes performance findings here; hunts over-engineering, not slowness
- [adversarial-reviewer] — hunts correctness bugs; a perf fix that changes behavior belongs to its review
- [security-auditor] — hunts vulnerabilities; unbounded growth that is attacker-controlled is also its territory
- [nitpicker] — exhaustive whole-repo defect audit

---

[complexity-hunter]: ../complexity-hunter/README.md
[adversarial-reviewer]: ../adversarial-reviewer/README.md
[security-auditor]: ../security-auditor/README.md
[nitpicker]: ../nitpicker/README.md
