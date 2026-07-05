# commit-auditor

Hostile single-shot audit of commit-message discipline against the actual diffs. Release automation (release-please, semantic-release) reads only the message, so a mislabeled commit silently mis-versions the release. For every commit in the audit range (default: since the last release tag) it reads the full message AND the full diff and verifies the label against what actually changed — never the message alone, never the diff stat alone. Every finding cites the SHA, the quoted message, the contradicting hunks, and the version consequence: the bump release-please takes as-labeled versus the bump the diff earns. On approval, amends unpushed messages; pushed history is never rewritten — the fix is a documented correction commit (`Release-As:` footer or corrected-type restatement).

## When to Use

- "Audit the commits" / "check commit messages" / "verify conventional commits" / "run commit-auditor"
- Before a release, to prove release-please computes the right version from the range
- After a suspicious version bump — a major nobody intended, a shipped feature missing from the changelog
- Verifying a PR's commits or a squash-merge title against the full diff before merge

**When NOT to use:**
- Code defects inside the diffs → use [adversarial-reviewer]
- CI/CD workflow defects, including the release workflow's YAML → use [ci-auditor]
- Implementing PR review comments → use [cr-implementer]

## commit-auditor vs. cr-implementer vs. ci-auditor

| | commit-auditor | cr-implementer | ci-auditor |
|---|---|---|---|
| Question | "Does each commit message tell the truth about its diff?" | "Which PR review comments are valid, and implement them" | "Are the pipeline definitions exploitable or silently non-gating?" |
| Input | Commit messages + diffs in the audit range | GitHub PR review comments | `.github/workflows/**` and other pipeline YAML |
| Output | `docs/audit/commit-auditor-findings.md`; message amendments / correction commits on approval | Code changes + GitHub thread replies | `docs/audit/ci-auditor-findings.md`; workflow fixes on approval |

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Every commit message and diff in the audit range (`git log`, `git show`); the last release tag; the project's convention table (CLAUDE.md, CONTRIBUTING, release-please config — Conventional Commits when absent); remote refs (pushed/unpushed classification); PR commits via `gh` when given a PR |
| **Writes** | `docs/audit/commit-auditor-findings.md` |

## How to Invoke

```
/commit-auditor            # commits since the last release tag
/commit-auditor main..HEAD # explicit range
/commit-auditor 42         # commits of PR #42
```

Determines the audit range, loads the project's own commit convention, then verifies every commit in range — merge commits, squash merges, bot commits (renovate/dependabot) included.

## Defect Classes

| Class | Definition |
|-------|------------|
| **type-understatement** | A no-bump type (`chore:`, `docs:`, `refactor:`) whose diff adds user-facing behavior — the feature ships unreleased |
| **type-overstatement** | A `feat:` whose diff is a pure fix, refactor, or internal change — a noise minor bump |
| **unmarked-breaking** | The diff removes/renames public surface or changes behavior incompatibly, with no `!` and no `BREAKING CHANGE:` footer |
| **spurious-breaking** | A `!`/footer on a diff with no consumer-visible break — forces a bogus major |
| **scope-lie** | A squash-merge title describing only part of the diff |
| **malformed-convention** | A type outside the project's convention table, missing `: ` separator, or a footer release-please cannot parse |

## Process

```
0. Re-validate existing findings (amended/corrected → Fixed; wrong → Invalid)
1. Determine the audit range — user-given range/PR, else last release tag..HEAD; every commit examined, never a sample
2. Load the convention — the project's own table; Conventional Commits when absent
3. Verify every commit: full message vs full diff, against every defect class
4. Compute the version consequence — bump as-labeled vs corrected; classify pushed/unpushed
5. File findings — SHA, quoted message, contradicting hunks, version consequence, exact fix
6. Write docs/audit/commit-auditor-findings.md
7. Ask: "Apply fixes? (a)ll (c)ritical-and-high only (s)afe (n)o" — amend unpushed; propose corrections for pushed
8. Ask: "Commit findings to git? (y/n)" — never commit silently
```

A run is COMPLETE only when every commit in range is examined. Any unexamined commit is an
`- Unexamined:` Summary bullet and forces verdict INCOMPLETE.

## Findings Format

```
# Commit Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N commits unexamined)
- Range audited: <ref..ref> | commits enumerated: N | examined: N
- Convention source: <CLAUDE.md|CONTRIBUTING|release-please config|Conventional Commits (default)>
- Version consequence: as-labeled <none|patch|minor|major> | corrected <none|patch|minor|major>

## Open Findings

### Critical

#### [CM-NNN] Short title
Status: Open
Class: <type-understatement|type-overstatement|unmarked-breaking|spurious-breaking|scope-lie|malformed-convention>
Commit: <sha> "<quoted subject line>"
Pushed: <yes|no>
Problem: <what the label claims vs what the diff does>
Evidence: <the quoted message lines and the contradicting hunks>
Impact: <the bump release-please takes vs the bump the diff earns>
Fix: <the corrected message (unpushed) or the exact correction commit (pushed)>
```

Finding ID format: `CM-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | A wrong major or minor release would ship, or a breaking change would ship unmarked |
| High | The net bump diverges at minor/patch level — a due release is suppressed or an undue one forced |
| Medium | Label wrong but net bump unchanged — the changelog misfiles the entry; a commit hidden from release-please |
| Low | Scope/format defects whose only consequence is changelog wording |
| Advisory | Message hygiene with no version or changelog consequence |

## Related Skills

- [ci-auditor] — audits the pipeline YAML that runs the release; this skill audits the commits the release reads
- [cr-implementer] — implements PR review comments; this skill audits the commit messages themselves
- [adversarial-reviewer] — hunts code defects inside the diffs this skill only reads for labeling truth
- [nitpicker] — whole-repo audit orchestrator

---

[adversarial-reviewer]: ../adversarial-reviewer/README.md
[ci-auditor]: ../ci-auditor/README.md
[cr-implementer]: ../cr-implementer/README.md
[nitpicker]: ../nitpicker/README.md
