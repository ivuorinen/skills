# /nitpicker dead-code — Dead Code Hunt

Hostile hunt for code that is unreferenced or unreachable — with the deletion-safety discipline that no symbol is called dead until every reachability channel is ruled out. Assume the codebase hides both cruft that should be deleted and live code that only *looks* dead; prove which is which. Grep-shows-no-callers is a hypothesis, never a verdict.

## When to use

- Removing dead code, unused exports, unreachable branches, or orphaned files before a release or refactor
- When asked to "find dead code", "what can we delete", "clean up unused code", or "is this still used"
- After a feature removal or a big refactor, to find the code its deletion stranded
- When a grep-only cleanup is proposed — to replace it with a reachability-proven one

Out of scope, routed not dropped: an implementation that is incomplete or awaiting its first wiring routes to `/nitpicker unwired` (this command owns code that is complete and simply unreferenced or unreachable); unused, phantom, or duplicate **package dependencies** route to `/nitpicker deps`; speculative abstraction and dead flexibility — an interface with one implementation, a parameter read but always passed the same value, or a branch gated by a config flag the deployment can still enable — route to `/nitpicker complexity` (a branch whose condition is a literal or in-repo constant that can never change is this command's `dead-branch`, not dead flexibility); whether deleting a public symbol is a correct semver bump routes to `/nitpicker contract`; trivial intra-file lint items (an unused import, an unused local) are the project linter's, and this command owns what a per-file linter misses — cross-file reachability, deadness masked by a removed dynamic reference, and orphaned files.

## Reachability rule — the safety heart

A symbol is **dead** only when **every** reachability channel below is ruled out repo-wide — channels 1, 2, 3, and 5 for any symbol, additionally channels 4 and 7 for exports, with channel 6 the deletion-safety check rather than a liveness channel. A negative on one channel (no direct caller) proves nothing while another is unchecked. This checklist runs before any symbol is classified dead or deleted:

1. **Direct references** — calls, imports, and name uses across the whole repo, not just the defining file.
2. **String / dynamic references** — the symbol's name as a **string literal**: registries, dispatch tables, `getattr`/`globals()`/`__import__`, signal and event names, decorator-populated maps (`@register("charge")`). When the key or attribute name is **computed** — interpolated (`f"{prefix}_charge"`), concatenated, or read from config or a database — a literal grep proves nothing; trace how the key is built. A symbol reachable through a dynamically constructed name is live or **unconfirmed**, never dead.
3. **Reflection / entry points** — `setuptools` `entry_points`, `__main__`, plugin autodiscovery, framework decorators and route registries, and invocation from a build or CI target (a `Makefile` recipe, a shell script, a workflow `run:` step).
4. **Public-API surface** — re-exported in an `__init__`/index/barrel, listed in `__all__`, or documented: removal is a **breaking change**, not cleanup.
5. **Config / DI / IoC** — referenced by string in config, a service container, DI wiring, routes, or templates.
6. **Tests** — a deletion-safety check, **not** a production-liveness channel. A tests-only reference does not keep a symbol live: a non-exported symbol whose sole references are tests, with the production channels (1, 2, 3, 5) negative, is production-dead — delete it together with its now-purposeless tests. The safety check is the converse: do not delete a symbol whose tests are the last coverage of a path production still reaches through any other channel. A pure test utility with no production role that is itself unreferenced is out of this command's scope — route it as a one-line pointer to `/nitpicker tests`, never drop it silently.
7. **Cross-package / external consumers** — a monorepo sibling or a published-package importer this repo cannot see. A published-package public member is treated as having external consumers (channel 7 applies) unless it is explicitly private by package policy — underscore-prefixed, absent from `__all__`, or marked internal.

A symbol reachable through **any** channel is live. A candidate with **any channel unchecked or unverifiable** — the off-repo channels 4 and 7, or a computed key under channel 2 — is **unconfirmed**: filed at **Advisory** with the unchecked channels named in the finding title, its underlying class recorded in the body, never at a class severity that invites deletion, and never auto-deleted. Unconfirmed is a disposition, not a lower-effort verdict — either every channel is checked and the finding takes its class severity, or the finding stays Advisory until they are. Unconfirmed applies only to a channel that actually **bears** on the candidate: channels 4 and 7 bear only on **exported** symbols, and channel 2's computed-key caveat only where a key is genuinely computed. An `unreachable-code` or `dead-branch` finding is proven dead by **control flow** — and thus never unconfirmed on a reachability channel, keeping its class severity — **only when its condition is a literal or an in-repo constant with no external input**. A branch whose deadness depends on an externally-sourced config or environment value rests on channel 5: if any deployment can set that value, the branch is reachable — route it to `/nitpicker complexity` as dead flexibility, not dead-code; only a branch believed unreachable but resting on a channel-5 value this repo cannot verify is `unconfirmed`, never auto-deleted. A **non-exported** symbol with the production channels (1, 2, 3, 5) all negative is proven dead — channels 4 and 7 do not apply to it, channel 6 is a safety check not a liveness reference, and invoking any of them to park it at Advisory is a forbidden downgrade. Advisory is for genuine unverifiability, never a discretionary reduction of a proven finding.

## Defect classes

| Class | Definition | Evidence to construct |
| --- | --- | --- |
| **unreachable-code** | Statements after an unconditional `return`/`raise`/`break`/`continue`, or under an always-false condition — no path executes them | The dead statements, the control-flow proof no path reaches them, and whether they carry intended-but-stranded behavior |
| **dead-branch** | A conditional branch that can never be taken — a literal or in-repo-constant condition that can never change, a guard a prior guard subsumes, an unreachable `case` (a branch gated by an externally-settable config flag is `/nitpicker complexity`, not this) | The branch, the condition that excludes it, and the input that would be needed to reach it (none exists) |
| **unreferenced-symbol** | A non-exported function, class, constant, or module-level variable with zero references across the production channels (1, 2, 3, 5); channels 4 and 7 apply only to exports, and a tests-only reference (channel 6) leaves it production-dead, removed with its tests | The symbol and the negative result on each production channel |
| **unused-export** | A symbol exported or public but referenced nowhere the repo can see — removal is a breaking change, not a defect | The export, the empty in-repo reference set, and the consumer surface (channels 4 and 7) to confirm before removal |
| **orphaned-file** | A module or file no other file imports or references, and not an entry point or script | The file, no importer, and the negative on entry-point/CI/build/config references |
| **unused-parameter** | A function parameter never read in the body, not required by an interface, override, or signature contract | The parameter, its unread body, and proof no override or caller contract requires the slot |
| **unreferenced-asset** | A non-code file — template, fixture, migration, static asset — nothing references | The asset and the negative on string, template, config, build, computed-path, and autodiscovery/convention-directory references (a loader glob, a migrations directory, a `conftest` scan) |

**Evidence rule.** Every finding names the symbol or file, records the reachability-channel results that prove it dead (which channels were checked, all negative), and states what deleting it removes. Grep-shows-no-direct-caller is never sufficient evidence — it satisfies channel 1 alone. An `unreachable-code` finding additionally states whether the stranded code is inert cruft or **intended behavior a misplaced `return` killed**: for the latter, file the `unreachable-code` finding here at High (`correctness`) for the code that misleads and leaves the function returning a wrong result, and route a one-line pointer to `/nitpicker review` for the logic fix (the misplaced `return`) — do not re-file a separate correctness finding there, and never silently delete the stranded code. A symbol whose off-repo channels (public-API, cross-package) cannot be confirmed is filed `unused-export` naming the surface to confirm — never deleted on the in-repo negative alone.

## Process

Run this as a task list — one entry per step, every step closed before reporting. An unexecuted step is a coverage gap, and silence is approval.

1. **Enumerate the dead-code surface.** Scope: every file the project maintains; excluded are only vendored and generated code. Sweep repo-wide for each class — statements after `return`/`raise`, always-false branches, non-exported symbols, exports, importless files, unread parameters, unreferenced assets. Record counts per class. The task framing is not the category list; a hunt limited to what was pointed at is INCOMPLETE.
2. **Rule out reachability for each candidate.** For every candidate symbol or file, run all applicable channels of the Reachability rule repo-wide — channels 1, 2, 3, and 5 for any symbol, additionally 4 and 7 for exports, with channel 6 the deletion-safety check rather than a liveness channel. A candidate that survives one unchecked applicable channel is not yet dead. Record which channels were checked and their results.
3. **Classify and separate the risky removals.** A candidate with every channel negative and no off-repo surface is dead. A candidate that is a public export or has an unverifiable cross-package surface is `unused-export` — the finding names the surface, and removal is an owner/semver decision, not this command's to auto-apply.
4. **File findings** via the store protocol in `_conventions.md`, using `--auditor dead-code` (category `maintainability`; an `unreachable-code` finding that masks a bug is `correctness`). Route each out-of-scope defect as a one-line pointer to its command.
5. **Summarize and fix.** The summary states the run verdict — COMPLETE only when zero surface elements are unexamined, INCOMPLETE otherwise — and the per-class counts. Fix application and the commit gate follow `_conventions.md`, with the fix-scope override below.

## Severity guide

| Severity | Condition |
| --- | --- |
| High | Dead code that masks a bug: `unreachable-code` or `dead-branch` whose stranded code is the intended behavior — the function returns a wrong or stale result, or a guard meant to fire never does |
| Medium | A whole dead named construct a maintainer reads and trusts: an `orphaned-file`, a dead function or class (`unreferenced-symbol`), or an **inert** `unreachable-code`/`dead-branch` block that strands no behavior — cruft that misleads and rots |
| Low | Any other dead `unreferenced-symbol` that is not a function or class — a module-level variable, constant, type alias, or enum (regardless of the value's size or line count) — or an `unused-parameter` or an `unreferenced-asset`; no reader consequence |
| Advisory | `unused-export` whose removal is a semver/consumer decision, not a defect; or any **unconfirmed** candidate with channels unchecked — filed naming the surface or the unchecked channels, never deleted on the in-repo negative alone |

## Fix strategy

Every fix is a deletion of code proven dead, or a routed correctness fix; no behavior on a live path changes. After each removal, run the project's test suite (when none exists, record that) and confirm the build still resolves every reference. The `_conventions.md` fix prompt's `(a)ll` and `(c)ritical-and-high` options apply only the **Auto-applicable** list below; the **Requires explicit approval per change** and **Never auto-apply** categories are never covered by a blanket choice — each such deletion demands its own per-change confirmation even after `(a)ll` is chosen.

**Auto-applicable:**

- Delete `unreachable-code` or a `dead-branch` that is proven inert — no path reaches it and it carries no stranded intended behavior
- Delete an `unreferenced-symbol` whose production channels (1, 2, 3, 5) are all negative, removing any tests-only references with it, with the test suite green after removal
- Delete an `unreferenced-asset` with every string/template/config/build reference negative **and** no autodiscovery or convention-directory loader (a template loader, a fixture glob) and no computed path (channels 2–3) reaching its location

**Requires explicit approval per change:**

- Deleting an `unused-export` or any public symbol — a breaking change; confirm no consumer and the semver decision first
- Deleting an `orphaned-file` — confirm it is not an entry point, script, CI/build target, or config-referenced module
- Deleting an `unused-parameter` — a signature change; confirm no override or interface contract requires the slot and no caller depends on it
- Deleting anything whose reachability depends on a channel this repo cannot fully verify (cross-package, external consumers)

**Never auto-apply:**

- Deleting a symbol referenced by string, reflection, config, DI, or an entry point — it is live
- Deleting `unreachable-code` that carries intended-but-stranded behavior — route the correctness bug to `/nitpicker review`; deleting it hides the defect
- Deleting a public export without a consumer/semver decision
- Deleting on a grep-for-name negative alone, before the other applicable channels (2, 3, 5, and 4/7 for exports) are checked
- Deleting a migration, or any file a directory-convention loader scans by location (a migrations directory, a pytest `conftest` glob, a template-loader directory) — referenced by no literal string yet live; never auto-delete, and remove a proven-dead one only through the per-change approval gate

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

- **"Grep shows no callers, so it's dead — delete it."** Grep-for-name satisfies channel 1 alone. String-keyed dispatch, decorator registries, reflection, and public re-exports all have zero direct-name callers **by design** — a handler reached only through `HANDLERS[event["type"]]` and a `@register("charge")`-decorated route look dead to grep and are fully live. Rule out all applicable channels before the verdict.
- **"The name says `_legacy`, or it lives under `experimental/`, so it's obviously dead."** Names suggest, they never prove. A `_legacy_normalize` still populated into a registry is live. Verify references; the name changes nothing.
- **"A teammate already cleaned half the repo this way, so the method is fine."** Another engineer's unverified grep-deletions are not evidence of safety — if their method was grep-only, live code may already be silently broken. Widen the audit to check their deletions, do not inherit the shortcut.
- **"The release is tomorrow, delete it all tonight."** A deadline never authorizes an unverified deletion. Ship the provably-dead removals now (unreachable statements, fully-channel-negative private symbols); defer every public-export and orphaned-file removal to an owner decision. Delete-and-hope is how a release breaks.
- **"It's only a snippet / I can't grep the whole tree, so this is good enough."** Incomplete access lowers coverage, never the verification bar. A symbol whose channels you did not all check is `unconfirmed` and filed as such — it is never deleted, and the run verdict is INCOMPLETE, not a clean pass.
- **"I deleted what they pointed me at, I'm done."** The task framing is not the category list. Enumerate every class repo-wide in step 1; a framing-limited or sampled hunt is INCOMPLETE reported as done.
- **"Unused export — delete it."** Deleting a public or exported symbol is a breaking change, not cleanup. File `unused-export` at Advisory naming the consumer surface (channels 4 and 7); removal is a semver decision, never an auto-delete on the in-repo negative.
- **"Code after the `return` is just cruft — delete it."** Unreachable code after a `return` is often the intended computation stranded by a misplaced `return` — deleting it erases the evidence of a live bug and leaves the function returning the wrong result. Determine whether it was meant to run; if so, route the correctness fix to `/nitpicker review`, do not delete.
