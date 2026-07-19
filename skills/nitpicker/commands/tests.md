# /nitpicker tests — Test Suite Audit

Hostile audit of the test suite itself: assumes every test is weaker than it looks and proves it — a green suite is the null result, not evidence of quality. Findings are about tests only; fixes add or strengthen tests, never touch production source.

## When to use

- Verifying the test suite actually catches defects — before trusting a green CI run as a release signal
- After a bug shipped that the tests missed, or coverage is high but defects keep reaching production
- Before refactoring, to confirm the safety net holds
- When asked to "audit the tests", "find weak tests", or "do the tests actually test anything?"

Not for: bugs in application code (`/nitpicker review` — this command audits tests, not the code they exercise), performance defects (`/nitpicker perf`), or test-coverage review scoped to a single PR diff (`/nitpicker pr`).

## Defect classes

| Class | Definition |
| --- | --- |
| assertion-free | The test asserts nothing (or only that no exception was raised) |
| tautological | The test cannot fail — asserts a constant, asserts the value it just configured, or reimplements the production logic and compares it to itself |
| mock-of-subject | The test mocks or stubs the unit under test, then asserts on the mock |
| over-mocking | Mocks sever the code path so no production code executes between arrange and assert |
| flaky-pattern | Sleep-based synchronization, wall-clock/timezone dependence, test-order dependence, live network calls, shared mutable state across tests |
| coverage-hole | A money/security/data-loss path with no failing-capable test |
| untracked-skip | A disabled/skipped/commented-out test with no tracked reason — a tracked reason names an issue ID or a concrete re-enable condition; prose alone ("flaky", "fix later") is untracked |
| mutation-blind | A critical function survives a mutation spot-check — no test fails when a branch is inverted or a guard dropped |

## Process

1. Re-validate open findings per `_conventions.md` — a finding is `fixed` only when the test is strengthened/added AND proven failing-capable; `invalid` when the test does fail on the defect after all (say why).
2. Map and run the suite. Locate every test file, the runner, and the run command. Start the suite; abort past 10 minutes. Record pass/fail and runtime — or the abort/failure reason — in the summary. A suite that did not run never stops the audit; it only marks claims unverified (step 5).
3. Audit every test file against the defect classes above.
4. Audit coverage holes on critical paths. Enumerate the code paths where a defect costs money, breaks security/auth, or loses data. For each, identify the test that fails when that path breaks. A critical path with no failing-capable test is a coverage-hole finding — this step reads production code for what the tests fail to cover; it never modifies it.
5. Mutation spot-checks. Pick at least 3 functions on critical paths that contain branching logic — all of them when fewer than 3 exist. Never count branchless getters or pass-throughs toward the minimum. For each, mentally apply one mutation — invert a branch condition, drop a guard clause, change a boundary operator — and name the specific test that fails under it. No test fails → mutation-blind finding citing the function, the mutation, and the surviving suite. Verify by reading the tests' assertions, not by trusting test names.
6. File findings via the store protocol in `_conventions.md`, using `--auditor tests` and `--category tests`. Fold the domain fields into the finding body: Problem names the defect class and the test (file path and test name, or the uncovered production path for coverage-hole); Evidence quotes the test code verbatim (or, for coverage-hole, names the critical path and the absence); Impact names the concrete production defect the suite would let ship; Fix is the exact assertion, test change, or new test to add — tests only. When the claim is runtime-verifiable and the suite runs, verify it (run the one test, or the suite) before filing. When the suite does not run, file anyway with "unverified" stated in Evidence.
7. Present the summary, including: suite executed (pass/fail counts and runtime, or why not), test files audited N of N, critical paths examined and how many have a failing-capable test, mutation spot-checks run and how many the suite survived.
8. Offer fixes per `_conventions.md`; apply per the Fix strategy below in severity order and prove each before resolving.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | A money, security/auth, or data-loss path has no failing-capable test (coverage-hole), or survives a mutation spot-check (mutation-blind) — a defect there ships silently |
| High | An assertion-free, tautological, mock-of-subject, or over-mocking test guarding a critical-path behavior that no other failing-capable test covers |
| Medium | A flaky-pattern test whose intermittent failure trains the team to ignore red; any untracked-skip |
| Low | A weak test whose behavior is on a non-critical path or is covered by another failing-capable test |
| Advisory | A weak assertion where a stronger one is checkable (asserts non-null where the exact value is known); a positive-case test with no negative-case sibling |

## Fix strategy

All fixes edit test files only. Application/production source is never modified — not to make a test pass, not to add a hook for testability, not for any reason.

**Auto-applicable:**

- Add the missing assertion to an assertion-free test when the expected value is derivable from the code under test's current behavior
- Repoint a mock-of-subject test's assertions onto the real unit's output, keeping mocks only at its dependencies
- Replace sleep-based synchronization with the framework's await/poll/fake-clock mechanism
- Add a new test for a coverage-hole or mutation-blind finding

Requires explicit approval per change:

- Deleting a tautological or redundant test
- Un-skipping a disabled test, or adding a tracked reason to a skip
- Restructuring shared fixtures to remove order dependence or shared mutable state

Never:

- Any edit to application/production source
- Weakening an assertion, widening a tolerance, or adding a skip to make a test pass
- Resolving a finding as fixed without the failing-capability proof: run the changed/new test and show it passes, then perturb its expected value inside the test file, show it fails, and restore it. A fix without this proof stays open.

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

- **"Coverage is 90%, so the suite is fine."** Coverage counts executed lines, not verified behavior. An assertion-free test marks every line it touches as covered while catching nothing. Coverage numbers are inadmissible as evidence of suite quality; only failing-capable tests count.
- **"These tests pass, so they work."** A test that cannot fail always passes. Judge each test by what makes it fail, not by whether it passes.
- **"Mutation-checking every function is too slow, so I'll skip it entirely."** The floor is 3 critical-path functions per run. Exhaustiveness is not required; zero is not permitted.
- **"I'll only look at test files, not what they fail to cover."** Step 4 audits production code for what the tests miss. A perfect set of test files guarding half the critical paths is a Critical finding, invisible to any audit that never leaves the test directory.
- **"The mock setup is idiomatic, so it's fine."** Idiom is inadmissible. A beautifully structured mock of the unit under test verifies the mock library. Trace what production code actually executes between arrange and assert; when the answer is none, file over-mocking regardless of style.
- **"The skip has a comment, so it's tracked."** A tracked reason names an issue ID or a concrete re-enable condition. "Flaky, fix later" is prose, not tracking — file untracked-skip.
- **"Running the suite is out of scope for a static audit."** Step 2 starts the run unconditionally — not knowing the runtime is what the 10-minute abort is for. An unverified "this test cannot fail" that turns out wrong is a junk finding.
- **"The sleep is needed for async."** Sleep-based synchronization races the scheduler and fails intermittently under load. File flaky-pattern; fix with the framework's await/poll/fake-clock mechanism.
- **"I found a production bug — I'll fix it while I'm here."** Out of scope. Note it, route it to `/nitpicker review`, and leave production source untouched. This command's writes are test files and the findings store, nothing else.
- **"Lots of assertions means strong tests."** Asserting the value you configured on a mock three lines up is tautological at any count. Weigh assertions by whether a production defect changes their outcome, never by how many there are.
- **"The suite is huge, so I'll audit a representative sample."** Read every test file; the summary's `Test files audited: N of N` line exposes anything less. When time genuinely runs out, report the files not audited and present the run as partial — never present a sample as the audit.
- **"The findings are obvious from reading, no need to quote the code."** A finding without the quoted test code and the named defect it misses is unfalsifiable and gets discarded. No quote, no finding.
