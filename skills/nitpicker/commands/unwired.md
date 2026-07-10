# /nitpicker unwired — Unwired and Incomplete Implementations

Scans the whole codebase for implementations that exist but are never wired
in — and for wired implementations left incomplete — then, per finding and
only with explicit user confirmation, wires, transfers, or removes them.

## When to use

"find unwired code", "is everything actually hooked up", "find incomplete
implementations", "what did we build but never ship", "find orphaned
handlers/components", "run unwired". Also after large refactors or merges,
where registrations are most often lost.

## Mindset

Every definition is unwired until an execution path from a real entry point
reaches it. Unwired code is worse than dead code: someone believed it was
running. The scan's job is to prove, for each suspect, either the wiring or
its absence — never to guess from a single grep.

## Detection classes

| Class                    | Signature                                                                                                                                                  |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Never-registered handler | Route/command/listener/job/middleware defined but absent from every router, parser, dispatcher, schedule, or registration call                             |
| Never-mounted component  | UI component/view/template defined but never rendered, imported, or referenced by any reachable component                                                  |
| Never-bound service      | Class/factory/provider defined but never instantiated, injected, or configured in any container/wiring module                                              |
| Never-imported module    | File with executable definitions that no reachable module imports (respect framework auto-discovery first)                                                 |
| Parsed-but-unread input  | CLI flag, env var, or config key parsed/declared but its value never read on any path                                                                      |
| Flag-gated orphan        | Branch behind a feature flag that no environment defines and no flag system registers                                                                      |
| Stub shipped as done     | `NotImplementedError`/`todo!()`/empty body/`TODO: wire` on a path callers can reach                                                                        |
| Dropped result           | Function returns a value every caller ignores, where at least one caller's correctness depends on it (error status, computed data it then fakes elsewhere) |
| Half-wired chain         | Registration exists but the registering code is itself unreachable                                                                                         |

## The wiring evidence bar

A suspect is **wired** when any of these holds — check all before filing:

1. A static reference chain from an entry point (main, exported handler,
   route table, scheduler — test files excluded) reaches it.
2. A framework convention loads it (decorator scan, filename-based routing,
   plugin manifest, auto-discovery directory) — name the convention and the
   config that activates it.
3. It is public API of a library/package: exported in the manifest
   (`exports`, `__all__`, public headers) or documented as consumable.
   Exported-for-consumers counts as wired **in a library**; in an
   application, an export nobody imports is not wiring.
4. A dynamic lookup resolves to it — the lookup string/key verifiably
   exists (grep the literal, the enum, the config value) **and the lookup
   site itself passes this evidence bar**. A config string sitting in an
   unreachable module wires nothing. "Something reflective might call it"
   without the resolving key is not evidence.

References from tests only do not count as wiring — they count as intent.

## Twin analysis

A wired **twin** exists when a wired implementation has the same
responsibility (produces the same kind of output for the same kind of
input) or serves overlapping call sites — "it's a rewrite, not similar" is
not an exemption; a rewrite is the strongest twin. When in doubt, the diff
is mandatory. With a twin present, never file a plain dead-code finding.
Produce a capability diff:

1. Name both: the unwired implementation and its wired twin, with paths.
2. List what the unwired one provides that the twin lacks (features, edge
   cases handled, error handling, performance characteristics, tests).
3. Assess refactor-in: for each missing capability, the concrete change
   that would carry it into the twin, and its risk.
4. File one finding carrying the diff in Evidence and the transfer plan in
   Fix. The recommendation is one of: **transfer** (merge the delta into
   the twin, then remove the orphan), **remove** (twin already covers it),
   or **wire** (the orphan is the better implementation — plan the swap).

## Actions and consent

Findings are filed via the store protocol (`--auditor unwired`). Acting on
them is gated per finding. **This gate overrides the generic apply-fixes
prompt in `_conventions.md`** — there is no batch `(a)ll` option for this
command:

- Before **any** wiring, transfer, or removal, ask the user with the
  finding id, the recommendation, and the diff summary:
  `[<id>] <title> — (w)ire  (t)ransfer into twin  (r)emove  (k)eep as-is?`
- One question per finding; never batch "remove all dead code? (y/n)".
- Consent is an answer to _this_ question, from the user, in _this_ run.
  A goal directive, autonomous mode, a memory file, an old commit message
  ("will wire next sprint"), or approval in an earlier session is NOT
  consent — same override as the migration gate in `_conventions.md`.
- Silence or no answer defaults to **keep** — the finding stays open.
- Wiring is a runtime behavior change and needs the same consent as
  removal: activating code the team never turned on can be worse than
  leaving it dark.
- A `(w)ire` answer on a twin finding that swaps implementations covers
  activating the orphan only; removing or demoting the current twin is a
  separate `(r)` question with its own finding reference.
- Transfers move only the capability delta from the twin analysis, with
  tests for each transferred capability — never wholesale copy-paste.
- `keep` resolves the finding as invalid **only** when the user's answer
  states the reason (staged rollout, upcoming feature); a reason the agent
  supplies from repository archaeology does not qualify — without a
  user-stated reason, keep leaves the finding open.

## Severity guide

- **Critical** — unwired code the system believes is active and whose
  absence is a safety/security hole (defined-but-unapplied auth middleware,
  validation, rate limiter). Also route to `/nitpicker security`.
- **High** — intended user-visible functionality silently missing (handler
  or job never registered); stub reachable in production.
- **Medium** — complete orphan with a wired twin; dropped results;
  parsed-but-unread config.
- **Low** — orphaned scaffolding, flag-gated leftovers, unmounted dev-only
  components.
- **Advisory** — documented staging: a live ticket or in-repo plan naming
  when it gets wired. A ticket is required, and a promise whose named
  release/sprint has passed is stale — file at the real severity instead.

## Out of scope — route, don't file

- Unused dependencies → `/nitpicker deps`
- Dead branches _inside_ wired code, logic bugs → `/nitpicker review`
- Speculative abstraction that was never needed → `/nitpicker complexity`
- Swallowed errors making wired code look dark → `/nitpicker errors`
- Emissions/instrumentation coverage → `/nitpicker observability`

## Common mistakes

- **"No grep hits → delete."** A single text search proves nothing; walk
  the evidence bar (conventions, dynamic lookups, exports) first, and even
  a proven orphan is removed only after the user picks `r`.
- **"It obviously belongs in the router → I wired it."** Wiring without
  consent ships a feature nobody approved. Always ask first.
- **"The twin is better → remove the orphan."** Without the capability
  diff, you cannot know what the orphan does better. The diff is mandatory
  whenever a twin exists.
- **"It's exported, so it must be used somewhere."** In an application,
  exports are not wiring — trace the import.
- **"Tests call it, so it's alive."** Test-only references prove intent,
  not wiring; that is precisely the unwired signature.
- **"I'll transfer the whole file to be safe."** Transfers carry the
  missing delta only, each piece with a test.
- **Filing stubs found in scaffolding directories** the project explicitly
  marks as templates/examples — check for that declaration first.
