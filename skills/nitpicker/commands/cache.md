# /nitpicker cache — Cache Correctness Hunt

Hostile audit of caching correctness: assume every cache serves stale data after a write, shares a key across entities that must not share one, grows without bound, and stampedes on expiry — then prove where. A cache is a correctness liability until its key, its invalidation, its bound, and its expiry behavior are all shown right. Faster is not the goal; a faster wrong answer is worse than a slow right one.

## When to use

- Auditing a cache layer, memoization, TTL/invalidation logic, cache keys, or expiry behavior
- When asked to "audit the cache", "is this cache safe", "why is this data stale", "will this cache leak across tenants", or "what happens when the cache expires"
- After a cache-related incident — a stale read, a cross-tenant leak, an OOM, a thundering herd — to find its siblings
- Before a release, to prove no cache serves the wrong entity's data, no write leaves a stale entry, and no expiry stampedes a hot path

Out of scope, routed not dropped: a cache-on-error fallback that hides a primary outage with no operator-reaching signal routes to `/nitpicker errors` (masking-fallback) — this command owns the staleness bound, `errors` owns the invisible outage; retry storms on a retry loop route to `/nitpicker reliability` (this command owns cache-stampede, the concurrent recompute on miss or expiry); a data race that corrupts the cache structure routes to `/nitpicker concurrency` (this command owns the caching semantics — duplicate fill, stale read — not the memory race); general unbounded memory growth, N+1, and hotspots route to `/nitpicker perf`; whether hit/miss/staleness is observable routes to `/nitpicker observability`; a fallback that returns nothing — `None`, empty, or a zero value — rather than a bounded stale value is a fail-open default, routed to `/nitpicker errors`, not a cache finding. A key collision that serves one tenant's data to another is filed here as the caching root cause **and** routed to `/nitpicker security` (or `/nitpicker privacy`) for the exposure severity.

## Defect classes

| Class | Definition | Evidence to construct |
| --- | --- | --- |
| **key-collision** | A cache key omits a dimension the cached value depends on — tenant, user, locale, currency, auth scope, API version — so two distinct values share one entry | The key, the value's dependence on the missing dimension, and at least one caller path plus the second entity whose result would collide (the second may be named off-diff) — a cross-tenant or cross-user leak |
| **missing-invalidation** | A write or mutation of the underlying data leaves the cache entry unchanged, so reads serve the pre-write value | The write path, the cache entry it fails to invalidate or update, and the stale read that follows (unbounded when no TTL backstops it) |
| **incoherent-cache** | A per-process or per-node cache whose invalidation reaches only the local copy, so other instances keep serving stale data after a write | The cache's process/node locality, the write that clears one copy, and the divergent stale read from another instance |
| **unbounded-cache** | A cache with no size bound and eviction, or no TTL — memory grows without limit and entries never expire | The cache structure, the absent maxsize/eviction and absent TTL, and the growth or unbounded staleness it permits |
| **cache-stampede** | An expensive recompute on miss or expiry with no single-flight or lock, so concurrent misses each run it | The recompute, its cost, the expiry or cold-start moment, and the concurrent callers that each trigger it |
| **unbounded-stale-fallback** | Serve-stale or serve-on-error with no maximum age, so an arbitrarily old value is returned indefinitely while the source is unavailable | The fallback, the absent max-age bound, and the age the value can reach on a sustained source outage |
| **serialization-drift** | The serialize/deserialize round-trip loses type or precision — money as float, `datetime` as string, a set or tuple as a list, key ordering | The serialized value, the round-trip, and the concrete divergence from the in-memory value it caches |

**Evidence rule.** Every finding quotes the cache read, write, key construction, TTL/eviction policy, or expiry recompute, names the concrete trigger (a write with no matching invalidation, two tenants resolving to one key, an expiry with N concurrent misses, a `Decimal` through a JSON round-trip), and states the observable consequence — the stale profile, the wrong tenant's price, the OOM, the 12-service thundering herd, the money value off by a rounding step. A cache is a finding only when the scenario shows real harm: a key that already carries every value-determining dimension, a write path that already invalidates, a cache already bounded by size and TTL, an expiry already guarded by single-flight, is not a finding. "It caches, it's faster" is never evidence; the read-write-key-expiry path is.

A defect whose confirmation depends on information off the reviewed diff — a recompute's return type behind a callee, a cached value's field shape, a write path that mutates the cached data — is filed naming that off-diff element as the thing to confirm, never marked clean because the diff did not show it, and that element's run verdict is INCOMPLETE. So a known mutation with no in-scope invalidation is filed `missing-invalidation` naming the off-diff write path, whether or not a TTL is present. Severity follows the worst content the on-diff evidence makes plausible — the value's name, type, or source indicates it — not mere speculation: an unshown field the evidence indicates never lowers severity (a profile on an authorization-sensitive path is Critical naming the field to confirm), and an unshown field nothing indicates never raises it (a product description is not Critical on a guess).

## Process

Run this as a task list — one entry per step, every step closed before reporting. An unexecuted step is a coverage gap, and silence is approval.

1. **Enumerate the cache surface.** Scope: every file the project maintains; excluded are only vendored and generated code. Inventory every cache read, every populate/write, every invalidation, every key construction, every TTL/eviction policy, and every recompute-on-miss-or-expiry. Record counts per category. The first two defects found do not end the audit — a hunt that stops once it has enough to reject is INCOMPLETE.
2. **Check every key.** For each cached value, confirm the key includes every dimension the value depends on — tenant, user, locale, currency, auth scope, version. A missing dimension is `key-collision`; when the collision crosses a tenant or user boundary it is a data leak, filed Critical and routed to `/nitpicker security` (or `/nitpicker privacy`).
3. **Trace every write to its invalidation.** For each mutation of underlying data, confirm the cache entry is invalidated or updated, and that the invalidation reaches every instance — a per-process invalidation that does not fan out is `incoherent-cache`, not out of scope because a shared backend is a larger change. `missing-invalidation` requires that the underlying data is known to mutate — the writer in the diff or named off it; a cached value whose underlying data is not known to mutate and has no TTL is `unbounded-cache` (unbounded staleness), not `missing-invalidation`.
4. **Bound every cache and expiry.** Confirm each cache has a size bound with eviction and a TTL (`unbounded-cache` otherwise), each expensive recompute-on-miss has single-flight (`cache-stampede` otherwise), and each serve-stale fallback has a max-age (`unbounded-stale-fallback` otherwise).
5. **Check serialization fidelity.** For each serialize/deserialize, confirm no type or precision is lost — money is not floated, `datetime` survives, ordering is preserved. Trace what the recompute actually returns; do not assume the round-trip is lossless.
6. **File findings** via the store protocol in `_conventions.md`, using `--auditor cache` (category `correctness` for key-collision, missing-invalidation, incoherent-cache, serialization-drift; `reliability` for unbounded-cache, cache-stampede, unbounded-stale-fallback — but any class is `correctness` when its harm is a wrong money or authorization value). Route each out-of-scope defect as a one-line pointer to its command.
7. **Summarize and fix.** The summary states the run verdict — COMPLETE only when zero surface elements are unexamined, INCOMPLETE otherwise — and the per-class counts. Fix application and the commit gate follow `_conventions.md`, with the fix-scope override below.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | A wrong or stale value is acted on for a money or authorization decision, or served to the wrong entity across a tenant or user boundary — whatever the defect class: a cross-boundary `key-collision`, or `missing-invalidation`, `incoherent-cache`, `unbounded-stale-fallback`, or `serialization-drift` on a balance, price, or authorization value whose wrong result is acted on |
| High | A resource or availability failure the cache causes — `unbounded-cache` whose keyspace is unbounded or grows with traffic (memory exhaustion is the harm whether or not a specific OOM is constructed), `cache-stampede` on a hot expensive path amplifying load — or any correctness defect on a money-, balance-, price-, or authorization-relevant value not shown acted on: a `key-collision`, `missing-invalidation`, `incoherent-cache`, `unbounded-stale-fallback`, or `serialization-drift` on such a value |
| Medium | A correctness or staleness defect with constructed harm on a value that is not money- or authorization-relevant and causes no resource failure: a within-scope `key-collision`, a `missing-invalidation`, an `incoherent-cache` or `unbounded-stale-fallback` on a mundane value, a `serialization-drift` on a non-money value a consumer relies on, or a `cache-stampede` short of a hot expensive path (expensive recompute, no concurrent miss) |
| Low | A staleness or efficiency smell with no constructed harm: a TTL longer than the data's change rate warrants, an `unbounded-cache` on a small fixed keyspace that cannot exhaust memory, a negative result recached each miss |
| Advisory | Preemptive hardening where no harm scenario constructs yet — single-flight or a coherent backend on a path that has not stampeded or diverged |

This table replaces the generic severity table in `_conventions.md` for every cache finding. Low and Advisory are the deliberate exception to the Evidence rule's harm requirement — filed on a named smell or a preemptive-hardening gap, not a constructed harm. **"Acted on"** means a code path consumes the value in a money or authorization decision — a charge, a debit, an allow/deny; mere display to a user is not acted on, so a stale or wrong money- or authorization-relevant value displayed to its **correct** owner is High, not Critical (a mundane value stays Medium or Low per the rows above) — but a value served across a tenant or user boundary (the wrong owner) is Critical whether or not it is acted on. **"Hot"** means the miss path shows concurrent access — a shared hot key, request fan-in, or a measured request rate — not merely an expensive recompute. An `unbounded-cache` carries two harms: its **memory** harm follows the High/Low resource rows, and its **staleness** harm (no TTL) follows the correctness rows — up to Critical when the stale value is money- or authorization-relevant and acted on. File at the higher of the two.

## Fix strategy

Every fix changes cache behavior only; after the fix, a cache hit returns the same value the source would — the fix is what makes that true. After each fix, run the project's test suite (when none exists, record that) and exercise the read-after-write and the concurrent-miss paths to show the defect is gone.

**Auto-applicable:**

- Add the missing value-determining dimension to a cache key
- Add invalidation or write-through to a write path that mutates cached data
- Add a size bound with eviction, and a TTL, to an unbounded cache
- Add a maximum age to a serve-stale or serve-on-error fallback

**Requires explicit approval per change:**

- Adding single-flight or a lock around a recompute — it changes concurrency behavior
- Moving a per-process cache to a shared or coherent backend — an architecture change
- Changing the serialization format or type mapping — it changes what is stored

**Never auto-apply:**

- A `key-collision` fix on a security-sensitive path marked done without confirming the new key actually segregates the entities
- Any change to the value a hit returns while it remains cached on a live path (expiry or eviction that turns a hit into a fresh recompute is the auto-applicable fix, not this)
- Removing a cache layer
- Widening a TTL to hide a stampede instead of adding single-flight

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

- **"Two clear blockers make the call — I can stop reviewing."** The audit's job is every cache defect, not the first one that justifies rejection. Enumerate every cache read, write, and key in step 1; stopping once you have enough to reject leaves the missing key dimension and the stampede unfound, and the run is INCOMPLETE, not done.
- **"The GIL makes the dict op atomic, so the race is benign."** Atomicity of a single get or set does not stop concurrent misses from each running the expensive fill — that is `cache-stampede` at the key level, and the duplicate slow calls are the harm. Reason about the concurrent-miss path; do not wave it away with atomicity.
- **"Multi-instance coherence is an architecture rework, not a line fix — out of scope."** A per-process invalidation that does not fan out serves divergent stale data from every other pod; it is `incoherent-cache`, a correctness finding, filed with the coherent-backend or pub/sub fix named. Expensive to fix is not out of scope.
- **"The JSON round-trip is fine, I didn't check what the function returns."** Serialize/deserialize silently coerces `Decimal` to float (money), `datetime` to string, a tuple to a list. Trace what the recompute returns and prove the round-trip is lossless; assuming fidelity is how a price drifts by a rounding step.
- **"It caches, it's faster, ship it."** Speed is not correctness. A cache that returns a stale profile, the wrong tenant's price, or a rounding-drifted amount is a faster wrong answer — worse than the slow right one. The finding stands whatever the latency win.
- **"No TTL is fine, it's a small cache."** No eviction is unbounded memory growth and no TTL is unbounded staleness — both are defects. A cache with neither is a memory leak and a stale-data source at once; size it and expire it.
- **"Serve last-cached on error is graceful degradation."** Degradation is graceful only when bounded and signalled. A serve-stale with no max-age returns an arbitrarily old value on a sustained outage — file `unbounded-stale-fallback` — and the silent masking of the primary failure routes to `/nitpicker errors`.
- **"The key is unique enough."** Unique-enough is a collision waiting for the second tenant. A key must carry every dimension the value depends on; a `price:{sku}` computed per tenant serves the first tenant's price to all of them. File `key-collision`, Critical when it crosses a tenant or user boundary.
