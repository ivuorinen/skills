---
name: silent-failure-hunter
description: 'Hostile single-shot audit of application error handling — assumes failures are being swallowed and proves where: swallowed exceptions, fail-open defaults, overbroad catches, ignored error signals, masking fallbacks, silent retries, cause-destroying rethrows. Use when auditing error handling, catch blocks, fallbacks, or retries for silent failures, or after a failure surfaced late or never. Triggers: "find silent failures", "audit error handling", "what errors are we swallowing".'
---

# Silent Failure Hunter

## Overview

Hostile audit of application error handling. It assumes failures are being swallowed and proves where: it enumerates every error handler, ignored error signal, async call site, retry loop, and fallback branch, then for each constructs the concrete upstream failure and traces it to its observation point. A path where a real failure becomes silence — lost data, a fabricated success, an outage no operator sees — is a finding; a path that signals is not. It writes `docs/audit/silent-failure-hunter-findings.md` and, on approval, fixes each finding by changing the error path only — every fix leaves the happy path's inputs, outputs, and side effects untouched. Single-shot: re-validate existing findings, enumerate the surface, file new findings, optionally fix, re-validate.

Out of scope: fail-open hooks and unenforced rules on the Claude Code enforcement surface (route to `loophole-hunter`); general correctness bugs in the happy path (route to `adversarial-reviewer`); security vulnerabilities (route to `security-auditor`).

## When to Use

- Auditing error handling, catch blocks, fallback logic, or retry behavior for silent failures
- When asked to "find silent failures", "audit error handling", or "what errors are we swallowing"
- After an incident where a failure surfaced late or never — to find its siblings before they fire
- Before a release, to prove no failure path exits the system unobserved

**When NOT to use:** For fail-open hooks/rules in `.claude/`, use `loophole-hunter`. For happy-path logic bugs, use `adversarial-reviewer`. For vulnerabilities, use `security-auditor`.

## Process

Check every enumerated element against every applicable defect class. A finding is filed only with the quoted handler code, a concrete upstream failure, and an observable consequence.

| Class | Definition | Evidence to construct |
|-------|------------|------------------------|
| **swallowed-exception** | Empty catch, or catch-log-continue where the swallowed failure loses or corrupts data | The upstream failure and the data the caller believes was written or handled |
| **fail-open-default** | Error path returns a success value or default indistinguishable from a real result | The default value and the decision a caller makes on it as if it were real |
| **overbroad-catch** | `catch Exception` / bare `catch (e)` around logic that raises programming errors (TypeError, NameError, KeyError), converting bugs into handled failures | The programming error the guarded logic raises and the block masks |
| **ignored-error-signal** | A return code, error result, or errback discarded; an unawaited call or promise chain with no rejection path | The call site and the failure the discarded signal carried |
| **masking-fallback** | Fallback (cache-on-error, default config, secondary source) serving degraded data with no signal that the primary failed | The primary outage and the absence of any operator-reaching signal |
| **silent-retry** | Retry loop with no bound or no exhaustion signal, converting persistent failure into indefinite silence | The persistent failure and the nowhere its exhaustion is reported |
| **cause-destroyed** | Rethrow or error message that drops the original exception — no chaining, no context, catch-and-throw-new losing the stack | The original cause and the stripped message the operator gets instead |

**Evidence rule.** Every finding quotes the handler code, names the concrete upstream failure (what throws, times out, or returns the error), and states the observable consequence — what the caller, user, or on-call engineer never finds out about. A handler is a finding only when the scenario shows real harm; style is not harm. Logging alone is a finding only when the log provably reaches no one: level below the deployed threshold, destination nobody monitors, or a message that omits the data needed to act — but a log never converts data loss into handled: catch-log-continue on a path that loses or corrupts data is swallowed-exception no matter where the log goes. Deliberate degradation — documented, signalled (metric, alert, error field, or operator-reaching log), and bounded — is not a finding.

```
0. Re-validate existing findings
   If docs/audit/silent-failure-hunter-findings.md exists, re-validate each finding with
   Status: Open:
   - Error path now signals (re-trace the scenario — the failure surfaces) → move to Fixed
   - Finding was wrong (no real harm, or the degradation is deliberate) → move to Invalid
   - Still silent → leave Open

1. Enumerate the handler surface
   Scope: every file the project itself maintains — application code, scripts, and tools
   alike; excluded are only vendored/third-party and generated code. Within that scope,
   inventory every catch/except/rescue block, error callback and .catch(), async call site
   (unawaited calls, promise chains with no rejection path), call whose error-carrying
   return value is discarded, retry loop, and fallback branch. Record counts per category.
   This inventory is the coverage checklist — never proceed on a sample. Full examination
   of every element is the only COMPLETE outcome; any Unexamined element forces run
   verdict INCOMPLETE.

2. Trace every element to its observation point
   For each element: name what fails upstream (dependency outage, timeout, disk full,
   malformed input, programming error) and follow the failure until someone observes it —
   an operator-reaching log/metric/alert, or a failed response surfaced to the user or
   calling system. Receipt is not observation: an error propagated to a caller that
   discards it is still silent — follow it to the top of the stack. A trace that ends
   before observation is classified against the defect classes and filed.

3. File findings
   Assign the next SF-NNN id; record class, area, quoted handler code, scenario,
   consequence, and the exact error-path fix. Apply the Evidence rule to every entry.

4. Write docs/audit/silent-failure-hunter-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.

5. Present summary — state the run verdict (COMPLETE only if zero elements are
   Open-Unexamined) — then ask: "Fix silent failures? (a)ll  (c)ritical-and-high only  (s)afe  (n)o"
   - (a)ll / (c)ritical-and-high only: apply the matching Auto-applicable fixes.
   - (s)afe: apply only cause-chaining on existing rethrows and log level/destination
     corrections — no control-flow changes, no catch narrowing, no signal additions.
   Apply in severity order (Critical first). After each fix, run the project's test suite
   (when none exists, record that — its absence waives nothing else) and re-trace the
   scenario to show the failure now surfaces; a fix that alters
   happy-path behavior is reverted, not adjusted. Move proven fixes to Fixed.

6. Commit gate
   Fix edits to source files stay in the working tree unstaged — never stage or commit
   them silently. Then ask: "Commit findings to git? (y/n)" and, on yes, stage only
   docs/audit/silent-failure-hunter-findings.md.
```

## Findings Format

Output path: `docs/audit/silent-failure-hunter-findings.md`

```
# Silent Failure Hunter Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N elements unexamined)
- Surface enumerated: handlers N | async sites N | ignored-signal sites N | retries N | fallbacks N
- Examined: handlers N | async sites N | ignored-signal sites N | retries N | fallbacks N
- Open-Unexamined: N
- Unexamined: <element path:line> — <why not examined>

## Open Findings

### Critical

#### [SF-NNN] Short title
Status: Open
Class: <swallowed-exception|fail-open-default|overbroad-catch|ignored-error-signal|masking-fallback|silent-retry|cause-destroyed>
Area: <file path:line>
Handler: <the quoted handler code>
Scenario: <the concrete upstream failure — what throws, times out, or returns the error>
Consequence: <what the caller/user/on-call engineer never finds out about>
Fix: <the exact error-path change — the happy path stays untouched>

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

#### [SF-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <the error-path change, and the re-traced scenario that now surfaces>

## Invalid

### Pass N — YYYY-MM-DD

#### [SF-NNN] Short title
Notes: <why the harm is not real, or why the degradation is deliberate>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the
`Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the
other `## Summary` bullets after it. Keep the Total line in exactly that shape and insert no field
between `Total:` and `Invalid:`. All supplementary bullets (`Run verdict`, `Surface enumerated`,
`Examined`, `Open-Unexamined`, `Unexamined:`) follow the Total line; unexamined elements live as
`Unexamined:` Summary bullets, never in a separate section. `Open-Unexamined` equals the number of
`Unexamined:` bullets and is not part of the Open/Fixed/Invalid totals.

The per-finding `Status:` field is `Open` for an examined, still-silent finding; on moving a
finding to Fixed or Invalid, drop the `Status:` line. Step 0 re-validation re-checks every finding
with `Status: Open`. Finding ID format: `SF-NNN` (zero-padded to 3 digits). Assign sequentially;
never reuse ids.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | Data loss or corruption passes silently: swallowed exception on a write/persistence path; fail-open default that stores or returns fabricated data as real |
| High | An outage or failure is invisible to operators: masking fallback with no signal; unbounded signal-free retry on a dependency; error path no log, metric, or alert reaches |
| Medium | Overbroad catch masking programming errors; cause-destroying rethrow that blinds production debugging; ignored error signal with user-visible effect but no data loss |
| Low | Under-signalled failure — wrong log level, missing context, or delayed exhaustion signal — on a path with no data consequence |
| Advisory | Deliberate degradation that is signalled and bounded but undocumented; hardening where no concrete harm scenario exists yet |

## Fix Strategy

Every fix changes the error path only. The happy path's inputs, outputs, and side effects are identical before and after every fix — a fix that fails this test is reverted.

**Auto-applicable (ask first, apply only on approval):**
- Narrow an overbroad catch to the exception types the guarded operation raises
- Add cause chaining and context to an existing rethrow (`raise X from e`, `new Error(msg, { cause: e })`)
- Propagate a discarded error signal: check the return code, await the call, attach a rejection path that rethrows
- Add a bound and an exhaustion signal to a retry loop
- Add an operator-reaching failure signal (log, metric, error field) to a masking fallback, keeping the fallback
- Move a no-one-reaches log to a level and destination operators observe

**Requires explicit approval per change:**
- Changing a function's error contract — it starts throwing or returning an error where callers received a default
- Removing a fallback branch, or converting a fail-open default to fail-closed
- Adding new alerting or monitoring infrastructure

**Never auto-apply:**
- Any change to happy-path behavior
- Blanket try/except wrapping or inserting new catch blocks "for safety"
- Marking a finding Fixed without running the test suite and re-tracing the scenario
- Deleting or downgrading a finding to avoid fixing it

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

- **"It logs the error, so it's handled."** A log handles nothing unless it reaches someone who acts. Trace the level and destination: a debug line below the deployed threshold, into a file nobody monitors, is silence with extra steps. Logging is adequate only when it is emitted at the deployed level, to a monitored destination, with the data needed to act.
- **"Empty catch is idiomatic for cleanup code."** Exempt only after you read the guarded call and confirm its failure loses nothing — an empty catch around `close()` after a committed write qualifies; an empty catch around the write itself is a Critical. Idiom is verified per call, never presumed.
- **"I'll grep for 'catch' and call that the audit."** Three of the seven defect classes need no catch block: ignored-error-signal (including unawaited calls), silent-retry, masking-fallback. Enumerate all five surface categories in step 1; a catch-only sweep is an INCOMPLETE run misreported as complete.
- **"The fallback is graceful degradation."** Degradation is deliberate only when documented, signalled, and bounded — all three. A cache-on-error serving stale data with no operator-reaching signal is an invisible outage; file it as masking-fallback.
- **"Too many handlers to check them all, I'll sample."** Sampling is how the swallowed write survives the audit. Enumerate everything; genuine time exhaustion produces `Unexamined:` bullets and verdict INCOMPLETE, never a silent sample presented as done.
- **"Adding error handling everywhere is the fix."** Blanket try/except wrapping manufactures the exact defect this skill hunts. Every fix is surgical, tied to one finding, and changes only that finding's error path.
- **"A broad catch is defensive programming."** `catch Exception` around logic that raises TypeError converts your bugs into handled input errors. Defensive is catching what the operation throws; overbroad is also catching what you wrote wrong — file it.
- **"The retry will succeed eventually, no signal needed."** A retry with no bound or no exhaustion signal converts a persistent outage into indefinite silence while callers wait on a result that never comes. File it as silent-retry.
- **"It rethrows, so nothing is lost."** `throw new Error("failed")` destroys the cause, the stack, and the context the on-call engineer needs. A rethrow without chaining and context is cause-destroyed.
- **"This catch block is ugly — that's a finding."** Style is not harm. A finding requires the quoted handler, a concrete upstream failure, and an observable consequence; without a real-harm scenario there is no finding, whatever the code looks like.
- **"Fire-and-forget is intentional, skip the async sites."** Intent is proven, not presumed: deliberate fire-and-forget carries an explicit rejection path or a documented no-consequence note. An unawaited call whose rejection vanishes into the runtime is filed as ignored-error-signal.
- **"The happy path has a bug too, I'll fix it while I'm here."** Happy-path defects are out of this skill's write scope — record them and route to `adversarial-reviewer`. A fix that alters success-path behavior is reverted, whatever it improves.
