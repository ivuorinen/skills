# test-auditor

Hostile audit of the *test suite itself*. Assumes the tests are weaker than they look and proves it: hunts tests that cannot fail (assertion-free, tautological), tests that assert on mocks of the thing under test, over-mocking that severs the code path, flaky patterns (time/order/network dependence, sleeps, shared mutable state), untracked skips, coverage holes on money/security/data-loss paths, and mutation-blind spots where inverting a critical branch leaves the suite green. Every finding quotes the test code and names the concrete production defect the suite would let ship. It never rewrites application code — missing-coverage fixes add tests, never touch production source.

## When to Use

- "Audit the tests" / "find weak tests" / "do the tests actually test anything?"
- Before trusting a green CI run as a release signal
- After a bug shipped that the tests missed, or coverage is high but defects keep reaching production
- Before refactoring, to confirm the safety net holds

**When NOT to use:**
- Bugs in application code → use [adversarial-reviewer]
- Performance defects → use `perf-auditor` if present, else [nitpicker]
- Test-coverage review scoped to a single PR diff → use [pr-reviewer]

## test-auditor vs. adversarial-reviewer

| | test-auditor | adversarial-reviewer |
|---|---|---|
| Question | "Does the suite catch defects, or only look like it does?" | "What bugs are in this code?" |
| Subject | The test files and what they fail to cover | The application code itself |
| Output | Weak/flaky/tautological tests filed and fixed; missing tests added | Bugs in production code, hunted and reported |
| Touches production source | Never | Reviews it; fixes route through the user |

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Every test file; the test runner config and run command; production source on critical paths (money, security/auth, data-loss) to find what the tests fail to cover; suite run output |
| **Writes** | `docs/audit/test-auditor-findings.md`; test files only (on approval) — never application/production source |

## How to Invoke

```
/test-auditor
```

Maps and runs the suite first (aborting past 10 minutes), then audits every test file against the defect classes, checks critical paths for failing-capable coverage, and runs mutation spot-checks.

## Defect Classes

| Class | Definition |
|-------|------------|
| **assertion-free** | The test asserts nothing (or only that no exception was raised) |
| **tautological** | The test cannot fail — asserts a constant, asserts the value it just configured, or reimplements the logic and compares it to itself |
| **mock-of-subject** | The test mocks the unit under test, then asserts on the mock |
| **over-mocking** | Mocks sever the code path so no production code executes between arrange and assert |
| **flaky-pattern** | Sleep-based sync, wall-clock/timezone dependence, test-order dependence, live network calls, shared mutable state |
| **coverage-hole** | A money/security/data-loss path with no failing-capable test |
| **untracked-skip** | A disabled/skipped test with no issue ID or concrete re-enable condition |
| **mutation-blind** | A critical function survives a mutation spot-check — no test fails when a branch is inverted or a guard dropped |

## Process

```
0. Re-validate existing findings (test now proven failing-capable → Fixed)
1. Map and run the suite — abort past 10 minutes; a suite that did not run never stops the audit
2. Read every test file; classify against the defect classes
3. Enumerate critical paths; each needs a test that fails when the path breaks
4. Mutation spot-checks: ≥3 branching critical-path functions, one mental mutation each,
   name the test that fails — none fails → mutation-blind finding
5. File findings — every finding quotes the test code and names the defect missed
6. Write docs/audit/test-auditor-findings.md
7. Ask: "Apply fixes now? (y/n)" — fixes edit test files only, proven failing-capable
8. Ask: "Commit findings to git? (y/n)" — never commit silently
```

## Findings Format

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
```

Finding ID format: `TA-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | A money/security/data-loss path has no failing-capable test, or survives a mutation spot-check — a defect there ships silently |
| High | A weak test (assertion-free, tautological, mock-of-subject, over-mocking) guards a critical-path behavior no other failing-capable test covers |
| Medium | A flaky-pattern test; any untracked-skip |
| Low | A weak test on a non-critical path, or whose behavior another failing-capable test covers |
| Advisory | A weak assertion where a stronger one is checkable; a positive-case test with no negative-case sibling |

## Related Skills

- [adversarial-reviewer] — hunts bugs in the application code; test-auditor hunts weakness in the tests that were supposed to catch them
- [nitpicker] — whole-repo defect audit including tests; test-auditor goes deeper on suite quality alone
- [pr-reviewer] — reviews a single diff, including its test coverage

---

[adversarial-reviewer]: ../adversarial-reviewer/README.md
[nitpicker]: ../nitpicker/README.md
[pr-reviewer]: ../pr-reviewer/README.md
