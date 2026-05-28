# adversarial-reviewer

Hostile code review. Assumes every line is guilty until proven innocent. Hunts for concrete, reproducible bugs — not theoretical concerns.

## When to Use

- "Review this code" / "find bugs" / "audit this for correctness"
- "Tear this apart" / "what's wrong with this?"
- Stress-testing a PR for logic errors and security issues before merging
- Any scenario where you want every defect found, not just obvious ones

**When NOT to use:**
- Scanner-based CVE / secrets / dependency audit → use [security-auditor]
- Full repository audit across code, tests, docs, and config → use [nitpicker]
- PR review in copy-paste GitHub comment format → use [pr-reviewer]

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Code or content passed as argument; whole files if paths are given |
| **Writes** | stdout only — no findings file is created |

## How to Invoke

```
/adversarial-reviewer [file or description]
```

Pass a file path, a diff, or a description of what to review. If nothing is supplied, the most recently changed files in the working tree are reviewed.

## Mindset

- Guilty until proven innocent — every line is a suspect
- No compliments — say what is wrong, not what is right
- No hedging — if something looks wrong, say it is wrong; construct the failing scenario
- Silence means approval — anything not flagged is implicitly approved

## Review Checklist

Work through these seven categories in order. Skip a category only if the codebase contains no constructs it covers.

### 1. Logic Errors
Off-by-one, wrong operator, wrong precedence, inverted condition, missed branch, early return that skips work, late return that over-executes.

### 2. Edge Cases & Boundaries
`null` / `undefined` / empty collection / zero / max value / negative input / Unicode / duplicate calls / first and last element / single-element collection.

### 3. Error Handling
Swallowed exceptions, missing `await` on async calls, overbroad `catch` that masks distinct failures, no cleanup in error path, error value discarded silently.

### 4. State & Concurrency
Race conditions, TOCTOU (time-of-check / time-of-use), stale closures, missing synchronisation on shared mutable state, incorrect assumption about execution order.

### 5. Security
Injection (SQL, command, template), missing authentication or authorisation check, trust boundary violation, secret or PII exposed in logs or error messages, unsafe deserialization.

### 6. Data Integrity
Unvalidated input reaching a persistence layer, partial write with no rollback, constraint violation not caught at the application layer, implicit type coercion producing wrong values.

### 7. Resource Management
Unclosed file handles or connections, unbounded collection growth, missing timeout on network or I/O call, goroutine / thread leak.

## Output Format

One block per bug, ordered Critical → High → Medium → Low:

```
**BUG: [short title]**
File: path/to/file.ts:42
Category: [category from checklist]
Severity: CRITICAL | HIGH | MEDIUM | LOW

[What is wrong — one or two sentences, no filler]

Trigger: [concrete input or sequence that hits the bug]

Fix: [minimal code change or approach]
```

## Severity Guide

| Level | Meaning |
|-------|---------|
| CRITICAL | Data loss, remote code execution, authentication bypass, persistent corruption |
| HIGH | Crash under reachable input, privilege escalation, silent data corruption |
| MEDIUM | Incorrect output for specific inputs, unhandled error leaking details |
| LOW | Minor logic flaw, unreachable dead code, missing edge-case guard |

## Process

1. Read the target code fully before filing any findings
2. For each bug, construct a concrete trigger scenario — if you cannot, do not file it
3. Order findings Critical first
4. If a finding would require rewriting the function to fix, say so — do not prescribe a full rewrite in the fix field
5. Stop when every category has been checked; do not add speculative findings to pad count

## Related Skills

- [nitpicker] — exhaustive whole-repository audit including tests, docs, and config
- [security-auditor] — scanner-based security audit (CVEs, secrets, dependencies)
- [pr-reviewer] — PR review formatted for GitHub PR comments

---

[skill-source]: SKILL.md
[nitpicker]: ../nitpicker/README.md
[security-auditor]: ../security-auditor/README.md
[pr-reviewer]: ../pr-reviewer/README.md
