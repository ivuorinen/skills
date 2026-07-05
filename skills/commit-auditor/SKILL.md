---
name: commit-auditor
description: 'Hostile single-shot audit of commit-message discipline against the actual diffs — type-understatement, type-overstatement, unmarked and spurious breaking changes, squash-title scope-lies, and malformed convention that mis-version a release-please/semver release. Use when auditing commit messages before a release, after a suspicious version bump, or on a given range or PR. Triggers: "audit the commits", "check commit messages", "verify conventional commits", "run commit-auditor".'
---

# Commit Auditor

## Overview

Hostile audit of every commit message in a range against the diff it labels. It assumes every label lies until the hunks prove it. Release automation (release-please, semantic-release) reads only the message, so a mislabeled commit silently mis-versions the release: an understated feature ships unreleased, an unmarked breaking change rides out as a patch, a spurious `!` forces a bogus major. For every commit in range it reads the full message AND the full diff and verifies the label against what actually changed. Every finding cites the SHA, the quoted message, the contradicting hunks, and the version consequence — the bump release-please takes as-labeled versus the bump the diff earns. Writes `docs/audit/commit-auditor-findings.md`. Single-shot: re-validate existing findings, enumerate the range, verify every commit, file new findings, fix on approval, re-validate.

## When to Use

- Auditing commit messages against their diffs before a release, to prove release-please computes the right version
- After a suspicious version bump — a major nobody intended, a shipped feature missing from the changelog
- Verifying a PR's commits or a squash-merge title against the full diff before merge
- When asked to "audit the commits", "check commit messages", "verify conventional commits", or "run commit-auditor"

**When NOT to use:** For code defects inside the diffs, use `adversarial-reviewer`. For CI/CD workflow defects (including the release workflow's own YAML), use `ci-auditor`. For implementing PR review comments, use `cr-implementer`.

## Process

```
0. Re-validate existing findings
   If docs/audit/commit-auditor-findings.md exists, re-validate each finding with
   Status: Open:
   - Message amended or correction commit present (re-check the SHA and range) → move to Fixed
   - Finding was wrong, or the user marks it false positive → move to Invalid (record reason)
   - Still mislabeled → leave Open
1. Determine the audit range
   A user-given range or PR wins (`<base>..<head>`, or the PR's commits via
   `gh pr view <n> --json commits`). Default: commits since the last release tag —
   `$(git describe --tags --abbrev=0)..HEAD`. No tag exists → the full branch history.
   Record the range and commit count. Every commit in range is examined — merge
   commits, squash merges, bot commits (renovate/dependabot), release commits —
   never a sample. A run with unexamined commits has verdict INCOMPLETE.
2. Load the convention
   The project's own convention table is the standard: CLAUDE.md, CONTRIBUTING, or
   the release-please config (.release-please-config.json changelog-sections).
   Absent all of those, Conventional Commits. Record the source in the Summary.
3. Verify every commit: message vs diff
   For each commit read the full message (subject, body, footers) AND the full diff
   (`git show <sha>`). Judge the label only against the hunks — never from the
   message alone, never from the diff stat alone. Check every commit against every
   class in the Defect Classes table. Breaking is a defined test, not a judgment
   call: the diff removes or renames public surface (exported API, CLI flag, config
   key, output format, skill/plugin name) or changes documented behavior in a way an
   existing consumer observes as incompatible.
4. Compute the version consequence
   Derive the bump release-please takes for the range as-labeled and as-corrected,
   per the loaded convention (default map: feat → minor, fix → patch,
   `!`/`BREAKING CHANGE:` footer → major, every other type → none). The
   divergence sets severity. Classify each
   finding's commit as pushed (reachable from any remote ref —
   `git branch -r --contains <sha>`) or unpushed; the fix shape depends on it.
5. File findings
   Assign the next CM-NNN id. Every finding records class, the SHA, the quoted
   message, the contradicting hunks, the version consequence, and the exact fix.
   No finding without evidence — the contradicting hunks for the diff-vs-label
   classes, the quoted malformed line for malformed-convention; no fix without
   the exact corrected message or correction commit.
6. Write docs/audit/commit-auditor-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.
7. Present summary — run verdict (COMPLETE only if every commit in range was
   examined), version consequence as-labeled vs corrected — then ask:
   "Apply fixes? (a)ll  (c)ritical-and-high only  (s)afe  (n)o"
   - (a)ll / (c)ritical-and-high only: apply the matching Auto-applicable fixes.
   - (s)afe: amend unpushed commits only; propose pushed-history corrections
     without creating them.
   Apply in severity order (Critical first). After each fix, recompute the version
   consequence for the range; move confirmed fixes to Fixed.
8. Commit gate
   Amendments and correction commits are created only per the step-7 approval —
   never silently. Then ask: "Commit findings to git? (y/n)" and, on yes, stage
   only docs/audit/commit-auditor-findings.md.
```

### Defect Classes

| Class | What to flag | Fix shape |
|-------|--------------|-----------|
| **type-understatement** | A no-bump type (`chore:`, `docs:`, `refactor:`, `test:`, `ci:`) whose diff adds or changes user-facing behavior — a new feature, a bug fix, a shipped-surface change | Relabel `feat:`/`fix:`; pushed → empty correction commit restating the change under its earned type |
| **type-overstatement** | A `feat:` whose diff is a pure fix, refactor, or internal change; a `fix:` on a diff with no behavior change | Relabel to the type the diff earns |
| **unmarked-breaking** | The diff removes or renames public surface, or changes behavior incompatibly, with no `!` and no `BREAKING CHANGE:` footer | Add the `!`/footer; pushed → correction commit carrying the `BREAKING CHANGE:` footer |
| **spurious-breaking** | A `!` or `BREAKING CHANGE:` footer on a diff with no consumer-visible break (e.g. a bot's `chore(deps)!:` on an internal CI action bump) | Drop the marker; pushed → `Release-As: X.Y.Z` correction commit pinning the correct next version |
| **scope-lie** | A squash-merge title describing only part of the diff — the title says docs, the hunks also change code | Retitle to cover the whole diff; pushed → correction commit naming the omitted change under its earned type |
| **malformed-convention** | A type not in the project's convention table, a missing `: ` separator, or a footer not in the `BREAKING CHANGE: <desc>` form release-please parses | Rewrite the message into the convention shape |

## Findings Format

Output path: `docs/audit/commit-auditor-findings.md`

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
- Unexamined: <sha> — <why not examined>

## Open Findings

### Critical

#### [CM-NNN] Short title
Status: Open
Class: <type-understatement|type-overstatement|unmarked-breaking|spurious-breaking|scope-lie|malformed-convention>
Commit: <sha> "<quoted subject line>"
Pushed: <yes|no>
Problem: <what the label claims vs what the diff does>
Evidence: <the quoted message lines and the contradicting hunks (file + hunk); for malformed-convention, the quoted malformed line>
Impact: <the bump release-please takes vs the bump the diff earns>
Fix: <the exact corrected message (unpushed), or the exact correction commit — Release-As footer or corrected-type restatement (pushed)>

### High
[same structure — repeat for Medium, Low, Advisory]

## Fixed

### Pass N — YYYY-MM-DD

#### [CM-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <the amendment or correction commit applied, and the recomputed version consequence confirming the bump is right>

## Invalid

### Pass N — YYYY-MM-DD

#### [CM-NNN] Short title
Notes: <why the label matches the diff after all>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the other `## Summary` bullets after it. Keep the Total line in exactly that shape and insert no field between `Total:` and `Invalid:`. All fixed findings live under one `## Fixed` h2 and all invalid findings under one `## Invalid` h2, sub-divided by `### Pass N — YYYY-MM-DD` h3 headers — never `## Fixed — pass N` variants. Unexamined commits live as `Unexamined:` Summary bullets, never in a separate section.

Finding ID format: `CM-NNN` (zero-padded to 3 digits). Assign sequentially from the highest existing ID; never reuse an ID, even after a finding moves to Fixed or Invalid. On moving a finding to Fixed or Invalid, drop the `Status:` line.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | A wrong major or minor release would ship, or a breaking change would ship unmarked: spurious-breaking forcing a bogus major; unmarked-breaking riding out as minor or patch; the net as-labeled bump diverging from the corrected bump at major level |
| High | The net bump diverges at minor or patch level: type-understatement suppressing a due release (the feature or fix ships unreleased); type-overstatement forcing an undue release |
| Medium | The label is wrong but the net bump is unchanged (another commit in range already earns it) — the changelog misfiles the entry; malformed-convention hiding a commit from release-please without changing the bump |
| Low | A scope-lie or format defect whose only consequence is changelog wording; malformed scope syntax on a no-bump commit |
| Advisory | Message hygiene (tense, casing, body detail) with no version or changelog consequence |

## Fix Strategy

**Auto-applicable (ask first, apply only on approval):**
- Amend the message of an unpushed HEAD commit (`git commit --amend -m` with the corrected message)
- Reword a deeper unpushed commit (show old → new message per commit before applying)
- Rewrite a not-yet-merged squash-merge PR title to cover the whole diff

**Requires explicit approval per change:**
- Creating the empty correction commit for pushed history — `git commit --allow-empty` with a `Release-As: X.Y.Z` footer, or restating the mislabeled change under its earned type or `BREAKING CHANGE:` footer
- Any correction touching a commit already inside a tagged release (the correction shifts the next release, not the shipped one)

**Never auto-apply:**
- Rewriting pushed history — no amend, rebase, or force-push on any commit reachable from a remote ref, ever
- Changing code to make the diff match the message — code defects route to `adversarial-reviewer`
- Committing anything silently

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"The message says chore, so it's a chore."** The message is the thing on trial; it is not evidence for itself. Only the diff testifies. Read every hunk before accepting any label.

**"Bot commits are auto-generated — skip them."** Bots mislabel too: a Renovate `chore(deps)!:` on an internal CI action bump reads to release-please as a breaking change and forces a spurious major. Bot commits get the same message-vs-diff verification as human commits.

**"The diff is huge, I'll trust the title."** Big diffs are where scope-lies live — the squash title describes the headline change and the hunks smuggle in three more. Size raises scrutiny; it never lowers it.

**"Checking every commit since the tag is too many — merge commits are enough."** release-please reads every commit in the range, not just merges. Every commit is examined; a sampled run has verdict INCOMPLETE and says so — it never presents a subset as complete.

**"It's already pushed, so nothing can be done."** Pushed history is never rewritten — and it is always correctable: an empty follow-up commit with a `Release-As:` footer or the corrected type/footer restates the truth for release-please. "Pushed" changes the fix shape, never the finding.

**"Breaking is subjective, I won't flag it."** Breaking is the defined test in step 3: removed or renamed public surface, or a behavior change an existing consumer observes as incompatible. Apply the test and file the result; discomfort is not a severity.

**"commitlint passed, so the messages are fine."** Format linters check shape, not truth. A perfectly-formed `chore:` on a feature diff passes every linter and still ships the feature unreleased. Shape checks replace nothing; the message-vs-diff comparison is the audit.

**"The net bump is right anyway, so the label doesn't matter."** The net bump sets severity, not validity. A mislabeled commit still misfiles the changelog entry and misleads every future reader of the history; file it at the severity the net consequence earns.

**"A quick force-push fixes the pushed commit."** Never. Rewriting pushed history breaks every checkout, PR, and tag that references it. The pushed-history fix is a documented correction commit, proposed to the user — nothing else.

**"I described the correction, so the finding is handled."** A described fix is an Open finding. It moves to Fixed only after the amendment or correction commit exists and the recomputed version consequence for the range confirms the bump is right.
