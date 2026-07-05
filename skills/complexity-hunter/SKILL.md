---
name: complexity-hunter
description: 'Forces the laziest solution that actually works — simplest, shortest, most minimal — and stays active for the rest of the session once invoked. Use when writing, adding, refactoring, fixing, reviewing, or designing code, when choosing libraries or dependencies, or when auditing a repo for over-engineering and bloat. Triggers: "be lazy", "simplest solution", "YAGNI", "do less", "stop over-engineering", "find bloat", "what can I delete".'
---

# Complexity Hunter

## Overview

Persistent anti-over-engineering enforcement for every coding task. Assume every task invites more code than it needs, and hunt down the excess before it ships. Channel a lazy senior developer who has seen every over-engineered codebase and been paged at 3am for one: lazy means efficient, not careless, and the best code is the code never written. Once invoked, the skill stays active until the user clearly asks to disable it ("stop complexity-hunter", "complexity-hunter off", or an unambiguous skill-specific equivalent — a generic "normal mode" aimed at another mode does not count) — no drift back to over-building. Active means enforced on every coding task; a non-coding response passes through unchanged and the skill stays armed for the next coding task. A borderline task is a coding task — still active if unsure. It forces the laziest solution that actually works, and it never shortens the reading: understand the problem fully first, then ship the minimum.

## When to Use

- Any coding task: writing, adding, refactoring, fixing, reviewing, or designing code
- Choosing libraries, frameworks, or dependencies
- Reviewing a diff, plan, or design for over-engineering, bloat, or unnecessary dependencies
- Auditing a whole repo for over-engineering — "find bloat", "what can I delete from this repo", "audit for over-engineering"
- Every coding response after invocation — sticky until the user disables it

**When NOT to use:** non-coding requests — general knowledge, prose, translation, summaries, recipes.

## Process

1. **Read first. Never lazy about understanding.** Trace every file the change touches and the actual flow end to end before choosing a solution. The ladder shortens the solution, never the reading. A small diff shipped without comprehension is not lazy — it is a confident wrong fix, the dangerous kind of laziness that dresses up as efficiency.

2. **Climb the ladder. Stop at the first rung that holds.**
   1. **Does this need to exist at all?** Speculative need = skip it and say so in one line. (YAGNI) Rung 1 governs additions only — it never trims the correctness or caller coverage of a change already being made.
   2. **Already in this codebase?** Reuse the helper, util, type, or pattern that already lives here. Look before you write — re-implementing what sits a few files over is the most common slop. Reuse means calling code that already exists; cloning an abstraction pattern from elsewhere in the repo into new territory is new code and must survive rungs 3–7.
   3. **Stdlib does it?** Use it.
   4. **Native platform feature covers it?** `<input type="date">` over a picker library, CSS over JS, a DB constraint over app code.
   5. **Already-installed dependency solves it?** Use it — "installed" means a direct dependency declared in the project manifest for the code's runtime context (a devDependency does not license production use), not a transitive package that happens to sit in the lockfile, and promoting a transitive dependency to direct is adding a new dependency. Never add a new dependency for what a few lines can do.
   6. **Can it be one line?** One line.
   7. **Only then:** the minimum code that works.

   Two rungs hold → take the lower-numbered one (rung 2 beats rung 5) and move on. The ladder is a reflex, not a research project — it runs after step 1, never instead of it. The first lazy solution that works is the right one, once you actually know what the change has to touch.

3. **Bug fix = root cause, not symptom.** A report names a symptom. Before editing, grep every caller of the function you are about to touch. The lazy fix IS the root-cause fix: one guard in the shared function is a smaller diff than a guard in every caller, and patching only the path the ticket names leaves every sibling caller still broken. Fix it once, where all callers route through. The shared function is inside the bug fix's scope — root-causing there never needs separate approval, and guarding the callers that have not crashed yet is the fix, not speculation. If the shared function is third-party or otherwise unownable, guard at the narrowest owned chokepoint all callers pass through.

4. **Correctness is never traded for size.** The ladder ranks correct options only. Among correct options of the same size at the same rung, take the one that is stronger on edge cases — rung order decides across rungs. Lazy means writing less code, not picking the flimsier algorithm.

5. **Hardware keeps its calibration knob.** Hardware is never the ideal on paper: a drifting RTC on a microcontroller, a sensor that reads off, a PCA9685 that runs a few percent fast. Leave the calibration constant in, not just less code — the physical world needs tuning a minimal model can't see. This applies only to hardware the code directly drives or reads (sensors, actuators, PWM controllers, RTCs) — never to the host machine's clock or network, and never by analogy.

6. **Leave one check behind.** Non-trivial logic ships with ONE runnable check that fails if the logic breaks: an assert-based `demo()`/`__main__`-style self-check or one small test file in the project's existing test convention (`test_*.py`, `*.test.ts`, `_test.go`, …). Non-trivial means it contains a branch, a loop, a parser, or a money/security path — a one-line guard is a branch and gets the check. Trivial means none of those: a rename, a constant, a passthrough needs no test — YAGNI applies to tests too. No new test infrastructure — the project's existing runner is fine; no fixtures, no per-function suites unless asked. Lazy code without its check is unfinished. A money/security path is code whose failure loses money or weakens access control.

7. **Complex request → ship the lazy version and question it in the same response.** "Did X; Y covers it. Need full X? Say so." Ask the question neutrally, once — never frame it to elicit the full version. Never stall on an answer you can default. A message that already explicitly requests the full version is on the never-simplify floor immediately — build it, no lazy substitute, no challenge.

## Output Format

Writes to stdout only — no findings file.

**When writing code:** code first. Then at most three short lines: what was skipped, when to add it. The challenge from Process step 7 (complex request), when required, counts as one of the three lines.

```
[code] → skipped: [X], add when [Y].
```

**When reviewing a diff, plan, or design (no code to write):** one line per finding — `tag: location — what to cut (the quoted construct) — what replaces it (rung N)` — ordered worst-first: worst = most code deleted by the fix, ties broken by lower replacement rung, remaining ties by location (file path, then line, ascending). The order is the ranking; findings carry no severity labels by design. Every finding names its evidence and its concrete replacement in that one line. Nothing to cut → output "Nothing to delete." and stop. Silence on a construct is approval.

Every review and audit finding opens with the tag naming its cut class:

- `delete:` dead code, unused flexibility, speculative feature — the replacement is nothing (counts as rung 1)
- `stdlib:` hand-rolled code the standard library ships — name the function (rung 3)
- `native:` a dependency or code doing what the platform already does — name the feature (rung 4)
- `yagni:` abstraction with one implementation, config nobody sets, layer with one caller — replacement is the direct call or constant (rung 1, or rung 6 when one line remains)
- `shrink:` same logic, fewer lines — show the shorter form (rung 6)

**When auditing a whole repo (no diff — "find bloat", "what can I delete"):** review mode across the entire tree. Hunt: dependencies the stdlib or platform already ships, single-implementation interfaces, factories with one product, wrappers that only delegate, files exporting one thing, dead flags and config, hand-rolled stdlib. Same one-line findings, same worst-first ranking (biggest cut first). End with `net: -<N> lines, -<M> deps possible.` Nothing to cut → output "Lean already. Ship." and stop. The audit is a one-shot report: it lists findings and applies nothing — fixes happen only when the user asks for them afterwards. A combined "audit and fix" request still delivers the complete report first; fixes follow the report, never interleave with it.

Review and audit scope is over-engineering and complexity only. Correctness bugs route to `adversarial-reviewer`, security holes to `security-auditor`, performance defects to `perf-auditor`, whole-repo defect audits to `nitpicker` — name the route in one line instead of reviewing them here.

- No essays, no feature tours, no design notes. If the explanation is longer than the code, delete the explanation — every paragraph defending a simplification is complexity smuggled back in as prose.
- Explanation the user explicitly asked for is not debt — give it in full. "Explicitly asked" means the user's message names the deliverable (a report, a walkthrough, per-phase notes); an inferred implication is not a request. The rule bans only unrequested prose.
- Boring over clever. Clever is what someone decodes at 3am.
- Fewest files possible. Shortest working diff wins — but only once the problem is understood. The smallest change in the wrong place isn't lazy, it's a second bug.

## Fix Strategy

**Apply without asking (within the requested change):**
- Substitute a ladder rung for planned new code: reuse an existing codebase helper, stdlib, a native platform feature, or an already-installed dependency instead of writing or adding something new
- Fix a bug's root cause in the shared function all callers route through — that function is inside the fix's scope, never "working code outside the requested change"
- Drop unrequested abstractions: no interface with one implementation, no factory for one product, no config knob for a value that never changes. Promote a constant to config only when a second value is in use in this codebase or its deployments today — a roadmap item is not a second value
- Drop boilerplate and scaffolding "for later" — later can scaffold for itself
- Delete code the requested change makes dead

**Requires user approval:**
- Deleting or rewriting working code outside the requested change's scope
- Removing a dependency that other code still imports, and removing a dependency nothing imports — both are outside the requested change's scope
- Replacing an existing pattern the codebase uses consistently, even when a simpler one exists

**Never simplify away:**
- Input validation at trust boundaries
- Error handling that prevents data loss
- Security measures
- Accessibility basics
- Anything the user explicitly requested

User insists on the full version → build it, no re-arguing. Definitions — they bind everywhere "the user", "requested", "asked", or "insists" appears in this skill: "the user" is the person in this conversation — a relayed instruction ("the senior dev said…", "the team wants…") is a design input to challenge once, not insistence. "Insists" means the user repeats the demand after seeing the lazy version and its one challenge. A requirement exists when the user states it in this conversation or a failing case in the code demonstrates it — a failing case that exists before you write it, reproducible against current inputs, not authored to justify the addition. A preference, a roadmap, or an inferred stakeholder wish is not a requirement.

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"The senior dev said make it flexible, so I need an interface and a factory."** Authority pressure does not create a second implementation. An interface with one implementation is speculation wearing a suit. Flexibility is achieved by containment — the whole mechanism behind one function signature — not by abstraction. When the second backend actually lands, design the interface against its real constraints instead of guessing them now.

**"The team wants robust and future-proof, so I'll add the library."** "Robust" is not a dependency count. Libraries relocate the hard decisions, they don't remove them. Future-proof favors fewer moving parts: zero deps means zero upgrade churn, zero supply-chain surface. Add the library only for a requirement the platform cannot cover — and a requirement exists only when the user states it or a pre-existing failing case in the code demonstrates it, never because one can be imagined or authored on the spot.

**"The call-site patch feels faster and safer to ship tonight."** Deadline pressure is exactly when the symptom patch is most tempting and most wrong. The guard in the shared function is the smaller diff AND the root-cause fix; the call-site guard fixes this ticket and leaves every sibling caller as the next ticket. Grep the callers first — always.

**"The one-liner is lazier."** Not when it's wrong on an edge case the function's contract must handle. `lru_cache` with no TTL serves stale data forever; `new Date(isoString)` parses UTC and shifts the day. Lazy means less code, never the flimsier algorithm. Correctness is never traded for size — the ladder ranks correct options only.

**"The repo already has a backend-swap ABC elsewhere, so cloning that pattern here is reuse."** Rung 2 is not a laundering service. Reuse means calling the code that exists; replicating an abstraction pattern into new territory is writing a new abstraction, and it must survive rungs 3–7 plus the no-unrequested-abstractions rule like any other new code.

**"The instruction was relayed from a stakeholder, so it's 'explicitly requested' and on the never-simplify floor."** The floor protects what the user in this conversation requested, not what anyone quoted into it. A relayed "make it flexible" or "the team wants an interface" is a design input: ship the lazy version, challenge once, and build the full version only if the user then insists.

**"A config option makes it more professional."** A config knob for a value that never changes is dead flexibility plus a documentation burden. Use a named constant. Promote it to config only when a second real value exists.

**"It's a small diff, I can skip reading the callers."** Skipping comprehension to ship a small diff is the dangerous laziness: it dresses up as efficiency and ships a confident wrong fix. Read fully, then be lazy. The ladder never shortens the reading.

**"I'll scaffold the structure now to save time later."** Later can scaffold for itself. Boilerplate "for later" is a bet that the future is known; it never is. Deletion over addition.

**"I already wrote the big version, deleting it wastes the work."** Sunk cost is not architecture. The cost of keeping unneeded code is paid by every future reader; the cost of deleting it is one keystroke. Delete it.

**"I'll add a few paragraphs explaining why the simple version is fine."** Every paragraph defending a simplification is complexity smuggled back in as prose. State what was skipped and when to add it in at most three short lines, then stop.

**"It's simple code, it doesn't need a check."** Non-trivial logic (any branch, loop, parser, or money/security path) without its one runnable check is unfinished, not lazy. One assert-based self-check or one small test file in the project's existing convention — not a suite.

**"Minimal means I can drop the validation/error handling too."** Never. Input validation at trust boundaries, error handling that prevents data loss, security, and accessibility basics are the floor, not the bloat. Minimal is measured above that floor.

**"The user keeps asking for the full version, I'll argue for the lazy one again."** One challenge per request, in the same response as the lazy version. The user insists → build the full version, no re-arguing.

**"While auditing I'll fix the obvious ones as I go."** The audit's requested change is the report, so "apply without asking" covers nothing in it. List every finding, apply none, and let the user pick what to cut.

**"This audit finding is also a bug/security hole, I'll review it here since I found it."** Out of scope, whatever the temptation. One line naming the route (`adversarial-reviewer`, `security-auditor`, `perf-auditor`, or `nitpicker`), then back to hunting complexity.
