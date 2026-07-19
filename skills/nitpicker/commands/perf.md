# /nitpicker perf — Performance Audit

Hostile single-shot performance audit: assume every data path degrades superlinearly until traced and proven otherwise.

## When to use

- Auditing a codebase for performance defects before a release, a traffic increase, or a data-volume increase
- When asked "why is this slow", "find performance issues", "will this scale", or "run a perf audit"
- After adding a data path that fans out per item — loops over query results, per-item API calls, per-file network writes
- When `/nitpicker complexity` (or any other command) routes a performance finding here

Out of scope: correctness bugs route to `/nitpicker review`; security to `/nitpicker security`; over-engineering and bloat to `/nitpicker complexity`; whole-repo defect audit is `/nitpicker audit`. Micro-optimizations without a growth driver are out of scope here and everywhere — do not route them, drop them.

## Defect classes

File a finding only when the class, the traced code path, and the growth driver are all named. A driver is an input whose size the deployment does not bound: user-submitted data, table rows, files on disk, items in an external feed. An input is bounded only when its bound is fixed at deploy time and independent of data volume — config constants, enum members, schema-fixed column counts. "Usually small" and "bounded by a config default the operator raises" are not bounded; a data-dependent size is a driver.

| Class | What to hunt | Evidence to construct |
| --- | --- | --- |
| **n-plus-one** | A query/fetch inside a loop over a result set, where a batch form exists (JOIN, `IN`, `prefetch`, bulk API) | The loop, the per-iteration query, the driver sizing the loop, and the batch call that replaces it |
| **quadratic-hotspot** | O(n²)+ work (nested loops over the same driver, membership scan of a list inside a loop, repeated sort) on a traced entry-point path | Both loops/scans, the shared driver, and the O(n)/O(n log n) replacement |
| **sync-in-async** | A blocking call (sync HTTP client, blocking file/DB read, `sleep`) inside an async handler, coroutine, or event-loop callback | The blocking call site, the event loop it stalls, and the async equivalent or executor offload |
| **unbounded-growth** | A cache, queue, buffer, or in-memory index with no size bound or eviction; a retry loop with no cap or backoff | The insertion site, the absent bound, the driver filling it, and the exact bound/eviction/cap to add |
| **missing-pagination** | A query or list endpoint returning an unbounded result set in one response or one fetch | The query, the driver sizing the result, and the pagination/limit mechanism the framework provides |
| **loop-invariant-work** | Work inside a loop whose result is identical every iteration — compilation, parsing, connection setup, a constant-input computation | The invariant expression, the loop's driver, and the hoisted form |
| **chatty-io** | Per-item network or disk round-trips over a driver-sized collection, where a batch/bulk/streaming form exists | The per-item call, the round-trip count as a function of the driver, and the batch form |

## Process

1. **Map the real data paths.** Enumerate every entry point: HTTP/RPC handlers, CLI commands, scheduled jobs, queue/event consumers, startup/init paths. For each, name the inputs it carries and classify each input bounded or unbounded. Every finding must sit on a path traced from an entry point. An entry point left untraced is recorded in the run summary as unexamined, with a concrete blocker (unreadable generated code, missing source, no access) — effort savings is not a blocker, and a silently skipped entry point is a defect in the audit itself.
2. **Probe measurement tools — never install.** Probe with `which` and manifest inspection: profilers (py-spy, perf, pprof), benchmark runners (hyperfine, `go test -bench`, pytest-benchmark), DB `EXPLAIN`, language-stdlib timing (`timeit`, `cProfile`, `console.time`). Record what is available in the run summary. Tools that are absent stay absent — reason from the code instead.
3. **Hunt every defect class on every traced path.** For each candidate:
   - Trace the driver to its source and confirm it is unbounded.
   - Read the actual call — verify no existing batching, caching, pagination, or bound already neutralizes it. Read the ORM call signature, the cache constructor, the query. "Probably batched" and "probably bounded" are both banned; the call site decides.
   - Demonstrate the scaling claim: complexity reasoning from the code (always cheap — always included), plus a measurement when the claim is contestable, i.e. the reasoning rests on an unverified runtime assumption (query uses an index, library call is O(1)) checkable with an installed tool, `EXPLAIN`, or the library source. Cite tool and number.
   - Candidate fails any of the above → drop it. It is not a finding.
4. **File findings** via the store protocol in `_conventions.md`, using `--auditor perf` (category `performance`). Each finding's Evidence names the class, the path (entry point → hot code, file:line), the driver, and the cost (the complexity reasoning or measurement); Impact states what degrades and at what scale; Fix is the concrete change — batch call, bound, hoist, pagination mechanism.
5. **Summarize and fix.** The summary includes finding counts by severity, measurement tools used, and unexamined entry points. Fix application and the commit gate follow `_conventions.md`; only the auto-applicable list below is eligible through the batch prompt — every other fix stays a proposal in its finding and is applied only when the user approves that specific change by name. No fix is applied before the summary and prompt, even an "obvious" one.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | O(n²)+ or per-item round-trip work on an unbounded driver on a hot production path (request handling, job processing); unbounded in-memory growth (cache/queue/buffer with no bound) that a normal workload fills until the process dies |
| High | N+1 query on an unbounded result set; sync-blocking call inside an async request path or event loop; missing pagination on an unbounded result set exposed to callers; unbounded retries against a failing dependency |
| Medium | Loop-invariant work redone per iteration over an unbounded driver; chatty disk I/O with an available batch form; retry loop capped but without backoff |
| Low | Superlinear work on an input bounded today by deployment reality, with a named, realistic path to unbounded (the finding names that path) |
| Advisory | Demonstrated-but-minor cost on a cold path (startup, admin-only, one-shot migration) with a real driver |

## Fix strategy

**Auto-applicable:**

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

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

**"It looks O(n²), so I'll file it without tracing the data size."** A nested loop over a config list or enum members is O(bounded²) = O(1). No finding exists until the driver is traced to an unbounded source. Filing untraced complexity is junk-finding inflation, and junk findings train users to ignore the report.

**"Demonstrating the claim is too much work — I'll write that it might be slow."** Speculation is banned outright. Complexity reasoning from the code costs minutes and is always included; when the claim is contestable, an installed tool or `EXPLAIN` settles it. A finding without its cost demonstration is not filed.

**"I'll sample the hot-looking directories — handlers and controllers — the rest is probably fine."** Every entry point is traced or recorded as unexamined with a reason. Jobs, consumers, and startup paths hide the worst N+1s precisely because nobody watches them. A silently skipped path is an unfiled finding.

**"This micro-optimization counts as a finding — more findings look thorough."** No growth driver, no finding. String-concat style, `++` vs `+= 1`, one avoidable allocation on a bounded path: drop them without routing them anywhere. Report volume is not report quality.

**"No profiler is installed, so I'll install one real quick."** Never. Probe, use what exists (including language-stdlib timing), and reason from the code for the rest. Adding a dependency to audit a repo mutates the repo under audit.

**"The ORM probably batches this / the cache probably has a bound."** "Probably" is banned in both directions. Read the call signature and the constructor before filing and before dismissing. Filing an N+1 the ORM demonstrably prefetches is a junk finding; dismissing one it demonstrably does not batch is silent approval of a real defect.

**"This slow loop also has a bug and an injection hole — I'll review those here since I found them."** Out of scope. One line naming the route (`/nitpicker review` for the bug, `/nitpicker security` for the hole), then back to hunting performance.

**"The faster algorithm changes output ordering, but nobody will notice."** Behavior changes ride only on explicit approval with the change named in the finding. A perf fix that reorders results or alters error timing is a correctness change wearing a perf hat.
