# /nitpicker plan — Adversarial Implementation Planning

Turn a change request into an implementation plan that survives hostile scrutiny before a line of code is written. Assumes every plan is naive — hiding unhandled failure modes, security holes, over-engineering, and false assumptions — until the audit lenses prove otherwise. Produces a plan document and stops: implementation never begins until the user gives explicit, separate approval.

## When to use

- "plan this", "make a plan for X", "how should we build Y", "design the implementation"
- Before starting any non-trivial feature, refactor, or migration
- Turning a brainstorm or a rough idea into an ordered, verifiable task list
- When a change touches security, data, migrations, public API, or concurrency, where a naive plan is expensive to unwind

Not for executing an already-approved plan — that is implementation, which this command gates, not performs. Not for auditing existing code: that is `/nitpicker review` or `/nitpicker audit`. Run standalone or by the `/nitpicker` default audit flow when the user asks to plan rather than review.

## The gate — read first

This command's deliverable is a **finalized, hardened plan**, never an implementation. Three rules bind every run and cannot be relaxed:

1. **No code before a valid go-ahead.** After the plan is presented, STOP. Do not create, edit, or delete any implementation file. Exactly one thing lifts the gate: a fresh statement from the user, made _after_ the finalized plan was presented and referring to that plan, that unambiguously authorizes writing implementation code (e.g. "implement it now", "start building"). Everything else is not the go-ahead — including:
   - the original request to _plan_ — planning is not building;
   - any prior "build X" or "implement X" instruction that predates the presented plan — an instruction given before the plan existed is superseded by the gate, not carried through it;
   - any approval, blanket "autonomous" consent, or "just do it" given before the plan was presented, whether in an earlier session, an earlier run, or earlier in this same run — re-present the plan and require a fresh reply;
   - approving or committing the plan document — that is agreement with the plan, not permission to code;
   - a sentence that merely contains a word like "go" or "approved" but refers to committing, revising, or anything other than starting implementation.

2. **Change size never relaxes the gate.** If a change is trivial enough that a full plan is overkill, the plan is short — a one-line plan is still presented and still gated. Deciding a change is "too small to plan" is not license to implement it directly.

3. **This overrides autonomous and goal-driven mode.** In auto or goal-driven development the goal of this command IS to produce and gate the plan — reaching a presented, gated plan is goal completion, not a step to rush past. This holds even when the outer goal is worded "implement X" or "ship X": within this command the gate converts that goal into "produce a gated plan and stop until the user approves". "Keep going to achieve the goal" does not license implementation here, exactly as the migration-consent gate in `_conventions.md` overrides autonomous and goal mode: silence, "later", or approval given before this plan was presented never count as the go-ahead.

## Mindset

- **Guilty until proven safe.** Every plan is assumed incomplete — hiding an unhandled error path, an unexamined trust boundary, an over-built abstraction, a migration that eats production, a false assumption about the inputs — until the lenses below prove otherwise.
- **Harden at plan time, not code time.** A gap caught in the plan costs a sentence; the same gap caught in review costs a rewrite.
- **The lazy plan wins.** Prefer the smallest plan that fully solves the stated problem. Question every task: does it need to exist?

## Process

Work these phases in order. Do not draft before the problem is understood, and do not finalize before the lenses have run.

### 1. Understand

- Restate the goal in one or two sentences. If the request is ambiguous or underspecified, ask the blocking questions now — never plan a misunderstood problem.
- Trace what the change touches end to end: the files, the data flow, the callers, the existing patterns it must fit.
- List the constraints (conventions, compatibility, deadlines) and the unknowns.

### 2. Draft

Decompose into an ordered list of **bite-sized tasks**, each a few minutes of work and independently verifiable. For each task record the exact files it touches, the change, and how it will be verified — the test or observable behavior that proves it works. Order tasks so each builds on already-verified ground.

### 3. Adversarial hardening

Run the draft through the lenses in the table below. This is the core of the command: a plan that skipped its relevant lenses is not hardened. Every lens is either run and recorded, or explicitly recorded as not-applicable **with the reason it does not apply** — a lens with no entry at all means the hardening is incomplete and the plan stays in draft. When a lens runs, record the concrete thing it examined (the specific file, boundary, task, or path) and what it changed; a bare "examined, no change" naming no subject does not count as having run the lens.

| Lens | Question it forces on the plan |
| --- | --- |
| `complexity` | Does any task need to exist? Is anything over-built, speculative, or reinventing what the codebase already has? Cut it. |
| `review` | What edge cases, boundary values, and error paths must each task handle? |
| `security` | What trust boundary does the change introduce or move? What input reaches a sink? |
| `errors` / `leaks` | What is the failure path of each new operation, and what releases the resources it acquires? |
| `migrations` | For schema or data changes: reversible, non-locking, safely ordered against deploy? What is the rollback? |
| `concurrency` | Does the change add shared state or an ordering assumption? |
| `contract` | Does it change a public surface? Is that change compatible, and does the intended version bump match? |
| `arch` | Does any task violate the codebase's boundaries or patterns? |
| `perf` | Does any task introduce N+1, unbounded growth, or per-item I/O at scale? |
| `tests` | Is every task's verification a real check, not a tautology? Are the critical paths covered? |
| `config` / `privacy` / `a11y` / `i18n` / `observability` | Apply when the change touches configuration, personal data, UI, locale, or the signals the system emits. |

Every gap a lens surfaces is resolved **in the plan** — a revised task, an added task, or an explicitly accepted risk — never deferred to "we will handle it during implementation".

### 4. Finalize

Assemble the plan document. It must carry the restated goal, the ordered task list with per-task verification, the lenses that ran and what each changed, a rollback or abort story, and an **Open questions & accepted risks** section naming every assumption made and every risk knowingly accepted. Unresolved _blocking_ unknowns keep the plan in draft — they never license starting implementation.

### 5. Gate

Present the plan and STOP. Offer revision. Wait for explicit approval before any implementation.

## Output

Write the plan to `docs/plans/<YYYY-MM-DD>-<slug>.md` (create `docs/plans/` if absent). Derive `<slug>` from the change request as a short kebab-case identifier — lowercase letters, digits, and hyphens only, with any path separators or `..` stripped — never the raw request string, so the plan stays inside `docs/plans/`. This command writes a plan, not findings: it does not touch the findings store or run `findings.py`. Structure:

```text
# Plan: <title>
Date: YYYY-MM-DD
Status: DRAFT — awaiting approval to implement

## Goal
<one or two sentences>

## Scope & constraints
<what it touches; what must not change>

## Tasks
1. <task> — files: <paths> — verify: <the check that proves it>
2. ...

## Adversarial hardening
- complexity: <what was examined, what was cut or simplified>
- security: <...>
- <each applicable lens and its outcome>

## Rollback / abort
<how to undo if it goes wrong mid-rollout>

## Open questions & accepted risks
- <assumption or accepted risk, and why it is acceptable>
```

With the `inline` modifier, present the same structure in the response instead of writing the file. The gate still applies — `inline` does not weaken it.

After writing: ask "Commit the plan to git? (y/n)" — never commit silently. Committing the plan is not approval to implement.

## Common mistakes

- Starting to implement because the plan "looks obviously right" — the gate is unconditional; finalizing the plan is where this command ends.
- Treating the request to plan, a standing "build X" instruction from before the plan existed, a same-run "just do it", or approval of the plan document as the implementation go-ahead — the go-ahead is a fresh, explicit statement made after the plan is presented.
- Matching a bare "go" or "approved" out of context — it authorizes implementation only when the sentence unambiguously says to start writing code.
- Continuing into implementation in auto or goal-driven mode "to finish the goal" — producing the gated plan IS the goal.
- Hardening the plan silently, or with hollow "examined, no change" lines that name no subject — each lens entry must name what it examined and what it changed, or record why the lens does not apply; a missing entry keeps the plan in draft.
- Skipping clarifying questions and burying the guesses as silent assumptions instead of recording them as Open questions.
- Padding the plan with tasks that do not need to exist — run the `complexity` lens before finalizing.
