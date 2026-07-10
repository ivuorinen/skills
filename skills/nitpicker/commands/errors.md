# /nitpicker errors — Silent Failure Hunt

Hostile audit of application error handling: assume failures are being swallowed and prove where — every path where a real failure becomes silence (lost data, a fabricated success, an outage no operator sees) is a finding; a path that signals is not.

## When to use

- Auditing error handling, catch blocks, fallback logic, or retry behavior for silent failures
- When asked to "find silent failures", "audit error handling", or "what errors are we swallowing"
- After an incident where a failure surfaced late or never — to find its siblings before they fire
- Before a release, to prove no failure path exits the system unobserved
- Run standalone or by the `/nitpicker` default audit flow

Out of scope: fail-open hooks and unenforced rules on the agent enforcement surface route to `/nitpicker agent-loopholes`; general correctness bugs in the happy path to `/nitpicker review`; security vulnerabilities to `/nitpicker security`.

## Defect classes

| Class | Definition | Evidence to construct |
| --- | --- | --- |
| **swallowed-exception** | Empty catch, or catch-log-continue where the swallowed failure loses or corrupts data | The upstream failure and the data the caller believes was written or handled |
| **fail-open-default** | Error path returns a success value or default indistinguishable from a real result | The default value and the decision a caller makes on it as if it were real |
| **overbroad-catch** | `catch Exception` / bare `catch (e)` around logic that raises programming errors (TypeError, NameError, KeyError), converting bugs into handled failures | The programming error the guarded logic raises and the block masks |
| **ignored-error-signal** | A return code, error result, or errback discarded; an unawaited call or promise chain with no rejection path | The call site and the failure the discarded signal carried |
| **masking-fallback** | Fallback (cache-on-error, default config, secondary source) serving degraded data with no signal that the primary failed | The primary outage and the absence of any operator-reaching signal |
| **silent-retry** | Retry loop with no bound or no exhaustion signal, converting persistent failure into indefinite silence | The persistent failure and the nowhere its exhaustion is reported |
| **cause-destroyed** | Rethrow or error message that drops the original exception — no chaining, no context, catch-and-throw-new losing the stack | The original cause and the stripped message the operator gets instead |

**Evidence rule.** Every finding quotes the handler code, names the concrete upstream failure (what throws, times out, or returns the error), and states the observable consequence — what the caller, user, or on-call engineer never finds out about. A handler is a finding only when the scenario shows real harm; style is not harm. Logging alone is a finding only when the log provably reaches no one: level below the deployed threshold, destination nobody monitors, or a message that omits the data needed to act — but a log never converts data loss into handled: catch-log-continue on a path that loses or corrupts data is swallowed-exception no matter where the log goes. Deliberate degradation — documented, signalled (metric, alert, error field, or operator-reaching log), and bounded — is not a finding.

## Process

1. **Enumerate the handler surface.** Scope: every file the project itself maintains — application code, scripts, and tools alike; excluded are only vendored/third-party and generated code. Within that scope, inventory every catch/except/rescue block, error callback and `.catch()`, async call site (unawaited calls, promise chains with no rejection path), call whose error-carrying return value is discarded, retry loop, and fallback branch. Record counts per category. This inventory is the coverage checklist — never proceed on a sample. Full examination of every element is the only COMPLETE outcome; any unexamined element forces run verdict INCOMPLETE.
2. **Trace every element to its observation point.** For each element: name what fails upstream (dependency outage, timeout, disk full, malformed input, programming error) and follow the failure until someone observes it — an operator-reaching log/metric/alert, or a failed response surfaced to the user or calling system. Receipt is not observation: an error propagated to a caller that discards it is still silent — follow it to the top of the stack. A trace that ends before observation is classified against the defect classes and filed.
3. **File findings** via the store protocol in `_conventions.md`, using `--auditor errors` (category `reliability`). Each finding's Evidence carries the quoted handler code, the scenario (the concrete upstream failure), and the consequence; the Fix is the exact error-path change — the happy path stays untouched.
4. **Summarize and fix.** The summary states the run verdict (COMPLETE only if zero elements are unexamined) and the per-category surface counts. Fix application and the commit gate follow `_conventions.md`, with this override: the (s)afe option applies only cause-chaining on existing rethrows and log level/destination corrections — no control-flow changes, no catch narrowing, no signal additions. After each fix, run the project's test suite (when none exists, record that — its absence waives nothing else) and re-trace the scenario to show the failure now surfaces; a fix that alters happy-path behavior is reverted, not adjusted.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | Data loss or corruption passes silently: swallowed exception on a write/persistence path; fail-open default that stores or returns fabricated data as real |
| High | An outage or failure is invisible to operators: masking fallback with no signal; unbounded signal-free retry on a dependency; error path no log, metric, or alert reaches |
| Medium | Overbroad catch masking programming errors; cause-destroying rethrow that blinds production debugging; ignored error signal with user-visible effect but no data loss |
| Low | Under-signalled failure — wrong log level, missing context, or delayed exhaustion signal — on a path with no data consequence |
| Advisory | Deliberate degradation that is signalled and bounded but undocumented; hardening where no concrete harm scenario exists yet |

## Fix strategy

Every fix changes the error path only. The happy path's inputs, outputs, and side effects are identical before and after every fix — a fix that fails this test is reverted.

**Auto-applicable (via the batch prompt, apply only on approval):**

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
- Marking a finding fixed without running the test suite and re-tracing the scenario
- Deleting or downgrading a finding to avoid fixing it

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

- **"It logs the error, so it's handled."** A log handles nothing unless it reaches someone who acts. Trace the level and destination: a debug line below the deployed threshold, into a file nobody monitors, is silence with extra steps. Logging is adequate only when it is emitted at the deployed level, to a monitored destination, with the data needed to act.
- **"Empty catch is idiomatic for cleanup code."** Exempt only after you read the guarded call and confirm its failure loses nothing — an empty catch around `close()` after a committed write qualifies; an empty catch around the write itself is a Critical. Idiom is verified per call, never presumed.
- **"I'll grep for 'catch' and call that the audit."** Three of the seven defect classes need no catch block: ignored-error-signal (including unawaited calls), silent-retry, masking-fallback. Enumerate all five surface categories in step 1; a catch-only sweep is an INCOMPLETE run misreported as complete.
- **"The fallback is graceful degradation."** Degradation is deliberate only when documented, signalled, and bounded — all three. A cache-on-error serving stale data with no operator-reaching signal is an invisible outage; file it as masking-fallback.
- **"Too many handlers to check them all, I'll sample."** Sampling is how the swallowed write survives the audit. Enumerate everything; genuine time exhaustion produces unexamined items and verdict INCOMPLETE, never a silent sample presented as done.
- **"Adding error handling everywhere is the fix."** Blanket try/except wrapping manufactures the exact defect this command hunts. Every fix is surgical, tied to one finding, and changes only that finding's error path.
- **"A broad catch is defensive programming."** `catch Exception` around logic that raises TypeError converts your bugs into handled input errors. Defensive is catching what the operation throws; overbroad is also catching what you wrote wrong — file it.
- **"The retry will succeed eventually, no signal needed."** A retry with no bound or no exhaustion signal converts a persistent outage into indefinite silence while callers wait on a result that never comes. File it as silent-retry.
- **"It rethrows, so nothing is lost."** `throw new Error("failed")` destroys the cause, the stack, and the context the on-call engineer needs. A rethrow without chaining and context is cause-destroyed.
- **"Fire-and-forget is intentional, skip the async sites."** Intent is proven, not presumed: deliberate fire-and-forget carries an explicit rejection path or a documented no-consequence note. An unawaited call whose rejection vanishes into the runtime is filed as ignored-error-signal.
- **"The happy path has a bug too, I'll fix it while I'm here."** Happy-path defects are out of this command's write scope — record them and route to `/nitpicker review`. A fix that alters success-path behavior is reverted, whatever it improves.
