---
name: nitpicker
description: Use when performing a comprehensive repository audit, reviewing code before a release, checking a PR for all bugs and defects, or when asked to "review the whole codebase", "audit this", "find all problems", "exhaustive review", or run a release gate check. Finds defects and optionally applies fixes in a single run.
---

# Nitpicker

## Overview

Adversarial, exhaustive whole-repository code review with integrated fixing. Assumes the code is incorrect until proven otherwise. Audits code, tests, documentation, and configuration for defects — then optionally applies fixes in the same run.

## When to Use

- Full repository audit before a release
- PR review when you want every defect found, not just obvious ones
- Release gate enforcement (fail if findings exceed threshold)
- When asked to "tear this apart", "find everything wrong", or "exhaustive review"

**When NOT to use:** For a focused security-only scan, use `adversarial-reviewer` instead. For architecture boundary violations specifically, use `arch-auditor`.

## Review Scope

Nitpicker must analyze:

- Code correctness and logic
- Security and trust boundaries
- Reliability and operational safety
- Maintainability and architecture
- Performance characteristics
- Test coverage and effectiveness
- Documentation accuracy and completeness
- Convention adherence (repo, language, framework)

## Severity Levels

| Level | Meaning |
|-------|---------|
| Critical | Correctness or security failure; must be fixed |
| High | Significant risk or defect |
| Medium | Quality or reliability concern |
| Low | Minor issue or smell |
| Advisory | Informational, no action required |

## Modes

| Mode | Behavior |
|------|----------|
| default | Full repository review |
| inline | Return findings in response instead of file; do NOT write `docs/audit/nitpicker-findings.md` |
| changed-files | Limit review to modified files + their dependencies |
| security | Invoke `/security-auditor`; incorporate its findings; focus remaining review on security and trust boundaries |
| tests | Focus on test quality |
| docs | Invoke `/doc-auditor`; incorporate its findings; focus remaining review on documentation accuracy and completeness |
| architecture | Invoke `/arch-detector` (if `docs/audit/arch-profile.md` is absent or stale), then invoke `/arch-auditor`; incorporate its findings; focus remaining review on design and boundary violations |
| release-gate | Fail if any findings at or above the threshold exist (default threshold: High) |

### Mode delegation detail

Modes `security`, `docs`, and `architecture` are incompatible with `inline` mode. If
`inline` is combined with any of these, treat the combined mode as `inline` only: run
the full internal review without invoking specialist skills, and return findings in
the response. Never write `docs/audit/nitpicker-findings.md` when `inline` is active,
regardless of which other mode flags are present.

In `security` mode (without `inline`), run `/security-auditor` first. Read
`docs/audit/security-findings.md` after it completes. Incorporate all open
Critical/High findings directly into the Nitpicker findings file (deduplicated by
area and problem statement). Do not re-run the same scanner checks; extend the review
with trust-boundary and auth logic analysis that the scanner does not cover.

In `docs` mode (without `inline`), run `/doc-auditor` first. Read
`docs/audit/doc-findings.md` after it completes. Incorporate all open Critical/High
findings. Extend with coverage of inline code comments, example code correctness, and
cross-reference accuracy.

In `architecture` mode (without `inline`), run `/arch-detector` if
`docs/audit/arch-profile.md` does not exist or is stale. Determine staleness from
Git metadata, not filesystem mtime (which git checkouts do not preserve): the
profile is stale when the most recent commit touching it
(`git log -1 --format=%ct -- docs/audit/arch-profile.md`) is older than the branch's
oldest commit (`git log --format=%ct main..HEAD | tail -1`), or — if git has no
record of the file — when the `Generated:` date inside it predates that commit.
Then run `/arch-auditor`. Read `docs/audit/arch-findings.md` after it completes.
Incorporate all open Critical/High findings. Extend with module coupling analysis
and layering violations not covered by arch-auditor.

## Single-Shot Behavior

```
1. Create docs/audit/ if it does not exist
2. If docs/audit/nitpicker-findings.md exists:
     Re-validate each OPEN finding:
     - Issue resolved → move to Fixed (record date)
     - Finding was wrong → move to Invalid (record reason)
     - Still present → leave as Open
3. If in security/docs/architecture mode AND NOT inline mode: invoke specialist skill and read its output file per Mode delegation detail. Then review remaining scope per mode.
4. Add new findings (assign next available ID — never reuse IDs)
5. Present findings summary
6. Ask: "Apply fixes? (a)ll  (c)ritical-and-high only  (s)afe — no refactors  (n)o"
   If a/c/s: apply fixes in severity order (Critical first), then re-run in
   changed-files mode to confirm finding count decreases, re-validate, update file
7. If NOT in inline mode: Write docs/audit/nitpicker-findings.md
8. Ask: "Commit findings to git? (y/n)" — never commit silently
```

## Fix Strategy

When applying fixes:

- Prefer minimal diffs
- Use idiomatic language and framework patterns
- Replace broken logic with correct implementations
- Add or update tests for each fix
- Update documentation when behavior changes
- Remove dead or harmful code when necessary

## Safety Rules

- Do not introduce unnecessary abstractions
- Do not change public APIs unless required
- Do not silently ignore findings — every skipped finding is marked in the file with a reason
- Do not weaken tests to make them pass
- Do not introduce regressions
- Fail if a Critical issue cannot be safely resolved

## Findings Format

```
# Nitpicker Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N

## Open Findings

### Critical

#### [ID] Short title
Category: <correctness|security|reliability|maintainability|performance|tests|docs|conventions>
Area: <path-or-scope>
Problem: <direct description>
Evidence: <proof or failing scenario>
Impact: <why this matters>
Fix: <concrete remediation>

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

#### [ID] Short title
Fixed: YYYY-MM-DD
Notes: <what changed>

## Invalid

### Pass N — YYYY-MM-DD

#### [ID] Short title
Notes: <why this finding was wrong>
```

## Rules

- No compliments
- No hedging without evidence — if something looks wrong, say it's wrong
- Silence means approval — if you don't flag it, that IS your approval
- All findings must include evidence
- Prefer concrete failing scenarios over abstract warnings
- Prefer exact fixes over general advice
- Validate documentation against implementation
- Validate tests against actual behavior

## Common Mistakes

**Hedging without proof:** "This might cause issues if..." — if you can't construct the failing scenario, don't file the finding.

**Filing a finding with no fix:** Every finding must have a concrete remediation, not "consider refactoring".

**Weakening tests to pass:** If a test fails after a fix, the fix is wrong. Investigate, don't adjust the assertion.

**Applying lower severity before Critical/High are done:** Severity order exists because lower fixes may conflict with higher-priority structural changes.

**Approving by omission then later adding findings:** Decide during the review pass. Silence = approval.

**Flagging style when content is correct:** Severity must reflect actual risk, not preference.

**Wrong section structure:** All fixed findings go under one `## Fixed` h2; all invalid findings go under one `## Invalid` h2. Sub-divide each by `### Pass N — YYYY-MM-DD` h3 headers. Never create `## Fixed — pass N` h2 variants. Never skip header levels (h2 → h4 with no h3 is a structural gap that the audit-findings hook will flag and autofix).
