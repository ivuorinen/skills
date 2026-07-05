---
name: test-auditor
description: 'Hostile audit of the test suite itself — assumes the tests are weaker than they look and proves it: tautological tests, mocked-out subjects, flaky patterns, untracked skips, coverage holes on critical paths, and mutation-blind spots. Use when verifying the test suite actually catches defects, before trusting a green CI run, or after a bug shipped that tests missed. Triggers: "audit the tests", "run test-auditor", "do the tests actually test anything?", "find weak tests".'
---

# Test Auditor

## Overview

Hostile audit of the test suite itself. It assumes every test is weaker than it looks and proves it: a green suite is the null result, not evidence of quality. It hunts tests that cannot fail, tests that assert on mocks of the thing under test, mocking that severs the code path so production code never runs, flaky patterns, untracked skips, coverage holes on money/security/data-loss paths, and mutation-blind spots where inverting a critical branch leaves the suite green. Every finding quotes the test code and names the concrete production defect the suite would let ship. Findings are about tests only — it never rewrites application code; missing-coverage fixes add tests, never touch production source. Single-shot: re-validate existing findings, map and run the suite, audit each defect class, spot-check mutations, file findings, optionally fix tests, re-validate.

## When to Use

- Verifying the test suite actually catches defects — before trusting a green CI run as a release signal
- After a bug shipped that the tests missed, or coverage is high but defects keep reaching production
- Before refactoring, to confirm the safety net holds
- When asked to "audit the tests", "find weak tests", or "do the tests actually test anything?"

**When NOT to use:** For bugs in application code, use `adversarial-reviewer` — this skill audits tests, not the code they exercise. For performance defects, use `perf-auditor` if present, else `nitpicker`. For test-coverage review scoped to a single PR diff, use `pr-reviewer`.

## Process

```
0. Re-validate existing findings
   If docs/audit/test-auditor-findings.md exists, re-check each finding with Status: Open:
   - Test strengthened/added and proven failing-capable → move to Fixed (record date)
   - Finding was wrong (the test does fail on the defect) → move to Invalid (record why)
   - Still weak → leave Open

1. Map and run the suite
   Locate every test file, the runner, and the run command. Start the suite; abort past
   10 minutes. Record pass/fail and runtime — or the abort/failure reason — in the Summary.
   A suite that did not run never stops the audit; it only marks claims unverified (step 5).

2. Audit every test against the defect classes
   Read every test file. Classify defects:
   - assertion-free: the test asserts nothing (or only that no exception was raised)
   - tautological: the test cannot fail — asserts a constant, asserts the value it just
     configured, or reimplements the production logic and compares it to itself
   - mock-of-subject: the test mocks or stubs the unit under test, then asserts on the mock
   - over-mocking: mocks sever the code path so no production code executes between
     arrange and assert
   - flaky-pattern: sleep-based synchronization, wall-clock/timezone dependence,
     test-order dependence, live network calls, shared mutable state across tests
   - untracked-skip: a disabled/skipped/commented-out test with no tracked reason — a
     tracked reason names an issue ID or a concrete re-enable condition; prose alone
     ("flaky", "fix later") is untracked

3. Audit coverage holes on critical paths
   Enumerate the code paths where a defect costs money, breaks security/auth, or loses
   data. For each, identify the test that fails when that path breaks. A critical path
   with no failing-capable test is a coverage-hole finding — this step audits production
   code for what the tests fail to cover; it never modifies it.

4. Mutation spot-checks
   Pick at least 3 functions on critical paths that contain branching logic — all of
   them when fewer than 3 such branching functions exist. Never count branchless
   getters or pass-throughs toward the minimum.
   For each, mentally apply one mutation — invert a branch condition, drop a guard clause,
   change a boundary operator — and name the specific test that fails under it. No test
   fails → mutation-blind finding citing the function, the mutation, and the surviving
   suite. Verify by reading the tests' assertions, not by trusting test names.

5. File findings
   Assign the next TA-NNN id. Every finding quotes the test code verbatim and states the
   concrete defect the suite would miss. When the claim is runtime-verifiable and the
   suite runs, verify it (run the one test, or the suite) before filing. When the suite
   does not run, file the finding anyway with "unverified" stated in its Evidence.

6. Write docs/audit/test-auditor-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.

7. Present summary, then ask: "Apply fixes now? (y/n)"
   If yes: apply fixes per Fix Strategy in severity order (Critical first), prove each
   per Fix Strategy, re-run the affected tests, move proven findings to Fixed.

8. Ask: "Commit findings to git? (y/n)" — never commit silently.
```

## Findings Format

Output path: `docs/audit/test-auditor-findings.md`

```
# Test Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Suite executed: yes (N passed / N failed, Ns) | no (<why>)
- Test files audited: N of N
- Critical paths examined: N | with failing-capable test: N
- Mutation spot-checks: N functions | survived by suite: N

## Open Findings

### Critical

#### [TA-NNN] Short title
Status: Open
Class: <assertion-free|tautological|mock-of-subject|over-mocking|flaky-pattern|coverage-hole|untracked-skip|mutation-blind>
Test: <test file path and test name, or the uncovered production path for coverage-hole>
Evidence: <the quoted test code, or for coverage-hole the critical path and the absence>
Defect missed: <the concrete production defect this suite lets ship>
Fix: <the exact assertion, test change, or new test to add — tests only>

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

#### [TA-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <the test change, and the failing-capability proof>

## Invalid

### Pass N — YYYY-MM-DD

#### [TA-NNN] Short title
Notes: <why the test does catch the defect after all>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and
rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding
entries and re-emits the other `## Summary` bullets after it. Keep the Total line in exactly
that shape and insert no field between `Total:` and `Invalid:` — any value you type into it
is overwritten. All supplementary bullets follow the Total line. All fixed findings go under
one `## Fixed` h2 and all invalid findings under one `## Invalid` h2, sub-divided by
`### Pass N — YYYY-MM-DD` h3 headers — never `## Fixed — pass N` h2 variants, never h2 → h4
with no h3. The per-finding `Status:` field is `Open`; on moving a finding to Fixed or Invalid,
drop the `Status:` line. Step 0 re-validation re-checks every finding with `Status: Open`.
Finding ID format: `TA-NNN` (zero-padded to 3 digits). Assign sequentially; never reuse ids.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | A money, security/auth, or data-loss path has no failing-capable test (coverage-hole), or survives a mutation spot-check (mutation-blind) — a defect there ships silently |
| High | An assertion-free, tautological, mock-of-subject, or over-mocking test guarding a critical-path behavior that no other failing-capable test covers — the safety net is decorative exactly where it matters |
| Medium | A flaky-pattern test (sleep, clock, order, network, shared state) whose intermittent failure trains the team to ignore red; any untracked-skip |
| Low | An assertion-free, tautological, mock-of-subject, or over-mocking test whose behavior is on a non-critical path or is covered by another failing-capable test |
| Advisory | A weak assertion where a stronger one is checkable (asserts non-null where the exact value is known); a positive-case test with no negative-case sibling |

## Fix Strategy

All fixes edit test files only. Application/production source is never modified — not to make a test pass, not to add a hook for testability, not for any reason.

**Auto-applicable (ask first, apply only on approval):**
- Add the missing assertion to an assertion-free test when the expected value is derivable from the code under test's current behavior
- Repoint a mock-of-subject test's assertions onto the real unit's output, keeping mocks only at its dependencies
- Replace sleep-based synchronization with the framework's await/poll/fake-clock mechanism
- Add a new test for a coverage-hole or mutation-blind finding

**Requires explicit approval per change:**
- Deleting a tautological or redundant test
- Un-skipping a disabled test, or adding a tracked reason to a skip
- Restructuring shared fixtures to remove order dependence or shared mutable state

**Never auto-apply:**
- Any edit to application/production source
- Weakening an assertion, widening a tolerance, or adding a skip to make a test pass
- Marking a finding Fixed without the failing-capability proof: run the changed/new test and
  show it passes, then perturb its expected value inside the test file, show it fails, and
  restore it. A fix without this proof stays Open.

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"Coverage is 90%, so the suite is fine."** Coverage counts executed lines, not verified behavior. An assertion-free test marks every line it touches as covered while catching nothing. Coverage numbers are inadmissible as evidence of suite quality; only failing-capable tests count.

**"These tests pass, so they work."** A test that cannot fail always passes. Green is the null result — the audit's whole premise. Judge each test by what makes it fail, not by whether it passes.

**"Mutation-checking every function is too slow, so I'll skip it entirely."** The floor is 3 critical-path functions per run (step 4). Exhaustiveness is not required; zero is not permitted. Skipping the spot-checks skips the only step that measures whether the suite detects anything.

**"I'll only look at test files, not what they fail to cover."** Step 3 audits production code for what the tests miss. A perfect set of test files guarding half the critical paths is a Critical finding, invisible to any audit that never leaves the test directory.

**"The mock setup is idiomatic, so it's fine."** Idiom is inadmissible. A beautifully structured mock of the unit under test verifies the mock library. Trace what production code actually executes between arrange and assert; when the answer is none, file over-mocking regardless of style.

**"The skip has a comment, so it's tracked."** A tracked reason names an issue ID or a concrete re-enable condition. "Flaky, fix later" is prose, not tracking — file untracked-skip.

**"Running the suite is out of scope for a static audit."** Step 1 starts the run unconditionally — not-knowing-the-runtime is what the 10-minute abort is for — and step 5 verifies runtime-verifiable claims before filing. An unverified "this test cannot fail" that turns out wrong is a junk finding; verification is what separates this audit from opinion.

**"The sleep is needed for async."** Sleep-based synchronization races the scheduler and fails intermittently under load. The framework's await/poll/fake-clock mechanism exists for this; file flaky-pattern and fix with it.

**"I found a production bug — I'll fix it while I'm here."** Out of scope. Note it, route it to `adversarial-reviewer`, and leave production source untouched. This skill's writes are test files and the findings file, nothing else.

**"Lots of assertions means strong tests."** Asserting the value you configured on a mock three lines up is tautological at any count. Weigh assertions by whether a production defect changes their outcome, never by how many there are.

**"The suite is huge, so I'll audit a representative sample."** Step 2 reads every test file; the Summary's `Test files audited: N of N` line exposes anything less. When time genuinely runs out, report the files not audited in the Summary and present the run as partial — never present a sample as the audit.

**"The findings are obvious from reading, no need to quote the code."** A finding without the quoted test code and the named defect it misses is unfalsifiable and gets discarded. Quote the code verbatim; name the defect concretely (step 5). No quote, no finding.
