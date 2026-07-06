---
name: release-prep
description: Use when validating that all changes in the current branch are ready to be included in a release PR managed by release-please automation.
disable-model-invocation: true
---

# Release Prep Checklist

Validates that the repository is in a clean, releasable state. Does **not** create
tags, bump versions, or push commits — release-please automation manages all of that
from `main`. The only action this skill takes beyond validation is offering to open a
PR, and only after every gate passes and the user explicitly approves.

Run these steps in order. **Stop immediately and report findings to the user if any
step fails.** Do not proceed to the next step.

## Step 1 — Validate All Skills and Version Sync

Run `/validate-skills`. This validates both public skills (`skills/*/SKILL.md`) and
internal skills (`.claude/skills/*/SKILL.md`), and also runs the version-sync check
(`scripts/check-version-sync.py`).

If any **errors** are reported from skill validation: stop. Report the list of errors
to the user. Do not proceed until they are resolved.

Warnings must be reviewed; fix any that relate to skills being changed in this branch.

If version sync fails: stop. Report which files differ and what their versions are.
Do not proceed.

## Step 2 — Security Scan

Run `/security-auditor`. If any Critical or High finding remains open after the scan:
stop. Report the findings to the user. Do not proceed.

## Step 3 — Documentation Accuracy

Run `/doc-auditor`. If any Critical finding remains open: stop. Report the findings.
High findings (missing API/boundary docs) must also be resolved before proceeding.
Medium and below may be deferred but must be tracked in `docs/audit/doc-findings.md`.

## Step 4 — Architecture Integrity

If `docs/audit/arch-profile.md` does not exist or is stale for the current branch,
run `/arch-detector` first to refresh it. Determine staleness from Git metadata, not
filesystem mtime (which git checkouts do not preserve): the profile is stale when
the most recent commit touching it
(`git log -1 --format=%ct -- docs/audit/arch-profile.md`) is older than the branch's
oldest commit (`git log --format=%ct main..HEAD | tail -1`), or — if git has no
record of the file — when the `Generated:` date inside it predates that commit.
Then run `/arch-auditor`. If any Critical or High finding remains open: stop. Report
the findings. Do not proceed.

## Step 5 — Exhaustive Code Review

Run `/nitpicker` in `release-gate` mode (threshold: High). If any Critical or High
finding remains open after fixes are applied: stop. Report the findings. Do not
proceed.

## Step 6 — Enforcement Surface Loopholes

Run `/loophole-hunter`. This audits the repository's own Claude Code enforcement surface
(`.claude/rules/`, hook scripts, `.claude/settings.json` wiring, permissions, and every
`SKILL.md`) for bypassable or unenforced constraints. If any Critical or High finding
remains open after fixes are applied: stop. Report the findings. Do not proceed.

## Step 7 — Hook Coverage

Run `/hooks-enforcer`. This audits hook *coverage* against the repository's evidence base
(current hook wiring, the `docs/audit/*-findings.md` history, git history, and project
memory) for recurring failures no hook guards and context-discipline gaps where large-output
work bypasses a context-saving tool. If any Critical or High finding remains open after fixes
are applied: stop. Report the findings. Do not proceed.

## Step 8 — Performance

Run `/perf-auditor`. This hunts N+1 queries, O(n²)+ hotspots on real data paths, sync-blocking
calls in async contexts, unbounded caches/queues/retries, missing pagination, and chatty
per-item I/O. If any Critical or High finding remains open after fixes are applied: stop. Report
the findings. Do not proceed.

## Step 9 — Test-Suite Strength

Run `/test-auditor`. This audits the test suite itself for assertion-free and tautological tests,
mocks of the unit under test, severed code paths, flaky patterns, untracked skips, and coverage
holes on money/security/data-loss paths. If any Critical or High finding remains open after fixes
are applied: stop. Report the findings. Do not proceed.

## Step 10 — Dependency Health

Run `/dep-auditor`. This audits dependency health beyond CVEs — unused, phantom, duplicate,
heavyweight, unmaintained, license-conflicting, drifted, and misclassified dependencies. If any
Critical or High finding remains open after fixes are applied: stop. Report the findings. Do not
proceed.

## Step 11 — Error Handling

Run `/silent-failure-hunter`. This audits application error handling for swallowed exceptions,
fail-open defaults, overbroad catches, ignored error signals, masking fallbacks, silent retries,
and cause-destroying rethrows. If any Critical or High finding remains open after fixes are
applied: stop. Report the findings. Do not proceed.

## Step 12 — Migration Safety

Run `/migration-auditor`. This audits database schema and data migrations for destructive ops
with no rollout story, irreversible downs, long-lock operations, missing FK indexes, schema-model
drift, unbatched data migrations, and deploy-order breaks. If any Critical or High finding remains
open after fixes are applied: stop. Report the findings. Do not proceed.

## Step 13 — Observability

Run `/observability-auditor`. This audits the emitted signal surface for dark paths, missing
correlation IDs, level misuse, unfireable alerts, cardinality bombs, PII in logs, silent jobs, and
context-free errors. If any Critical or High finding remains open after fixes are applied: stop.
Report the findings. Do not proceed.

## Step 14 — API Contract

Run `/api-contract-auditor`. This audits the declared public contract surface (OpenAPI/GraphQL
specs, package exports, published types, CLI flags) against the implementation, and every surface
change since the last release tag against the semver bump the commits declare. If any Critical or
High finding remains open after fixes are applied: stop. Report the findings. Do not proceed.

## Step 15 — Accessibility

Run `/a11y-auditor`. This audits the UI layer against WCAG 2.2 AA — missing alternatives,
unlabeled controls, keyboard-unreachable handlers, focus loss, ARIA misuse, contrast violations,
structure breaks, and motion hazards. A repo with no UI surface returns the explicit verdict "no
auditable UI surface". If any Critical or High finding remains open after fixes are applied: stop.
Report the findings. Do not proceed.

## Step 16 — CI/CD Pipeline

Run `/ci-auditor`. This audits CI/CD pipeline definitions for unpinned actions, over-broad token
permissions, script injection via untrusted interpolation, privileged-trigger misuse, secrets
leakage, non-gating checks, masked failures, missing concurrency, cache poisoning, and self-hosted
runner exposure. If any Critical or High finding remains open after fixes are applied: stop. Report
the findings. Do not proceed.

## Step 17 — Commit Discipline

Run `/commit-auditor`. This audits every commit message on the branch against its actual diff for
type-understatement, type-overstatement, unmarked and spurious breaking changes, squash-title
scope-lies, and malformed convention that mis-version a release-please release. If any Critical or
High finding remains open after fixes are applied: stop. Report the findings. Do not proceed.

## Step 18 — Concurrency Safety

Run `/concurrency-auditor`. This hunts data races, non-atomic check-then-act, deadlock-ordering, lost updates, unsafe publication, and shared-state-across-await. If any Critical or High finding remains open after fixes are applied: stop. Report the findings. Do not proceed.

## Step 19 — Internationalization

Run `/i18n-auditor`. This audits the localization surface for hardcoded user-facing strings, locale-unsafe number/currency/date formatting, timezone-naive datetimes, mistranslating concatenation, and missing plural rules; a repo with no localization surface returns the explicit no-surface verdict. If any Critical or High finding remains open after fixes are applied: stop. Report the findings. Do not proceed.

## Step 20 — Resource Lifecycle

Run `/resource-leak-auditor`. This hunts acquire-without-guaranteed-release on failure paths — unclosed handles, pool connections not returned on error, listener/subscription leaks, orphaned tasks, and temp-artifact leaks. If any Critical or High finding remains open after fixes are applied: stop. Report the findings. Do not proceed.

## Step 21 — Configuration

Run `/config-auditor`. This audits application/runtime configuration for undocumented vars, missing startup validation, unsafe production defaults, config drift, committed secrets, and string coercion traps. If any Critical or High finding remains open after fixes are applied: stop. Report the findings. Do not proceed.

## Step 22 — Verify Conventional Commits

Confirm every commit on this branch follows the conventional commits format that
release-please uses to determine the version bump and generate release notes:

- `feat:` — new feature (minor bump)
- `fix:` — bug fix (patch bump)
- `feat!:` or `BREAKING CHANGE:` footer — breaking change (major bump)
- `chore:`, `docs:`, `refactor:` — no version bump

Check the commit log with:

```bash
git log main..HEAD --oneline
```

If any commit message does not follow conventional commits format: stop. Instruct the user to fix all non-conforming messages using:

```bash
git rebase -i main
# Mark each bad commit as 'reword' to rename it.
```

Do not proceed until all commit messages are valid — release-please generates
`CHANGELOG.md` and the version bump automatically from these messages when the PR
merges to `main`.

Do **not** require or check for a manually-written `CHANGELOG.md` entry; release-please
manages the changelog.

## Step 23 — Confirm CI Is Green

Check `.github/workflows/validate-skills.yml` passed on the current commit. If CI is
failing: stop. Report which checks failed. Do not proceed.

## Gate Summary

After all steps pass, present this summary to the user:

```
✅ All release gates passed.

Steps completed:
  [✓] validate-skills — no skill errors; all 5 version files in sync at vX.Y.Z
  [✓] security-auditor — no Critical/High findings
  [✓] doc-auditor — no Critical/High findings
  [✓] arch-auditor — no Critical/High findings
  [✓] nitpicker release-gate — no Critical/High findings
  [✓] loophole-hunter — no Critical/High enforcement-surface findings
  [✓] hooks-enforcer — no Critical/High hook-coverage findings
  [✓] perf-auditor — no Critical/High findings
  [✓] test-auditor — no Critical/High findings
  [✓] dep-auditor — no Critical/High findings
  [✓] silent-failure-hunter — no Critical/High findings
  [✓] migration-auditor — no Critical/High findings
  [✓] observability-auditor — no Critical/High findings
  [✓] api-contract-auditor — no Critical/High findings
  [✓] a11y-auditor — no Critical/High findings
  [✓] ci-auditor — no Critical/High findings
  [✓] commit-auditor — no Critical/High findings
  [✓] concurrency-auditor — no Critical/High findings
  [✓] i18n-auditor — no Critical/High findings
  [✓] resource-leak-auditor — no Critical/High findings
  [✓] config-auditor — no Critical/High findings
  [✓] conventional commits — all commits on branch use valid format
  [✓] CI — validate-skills.yml passing

Release-please automation will create the Release PR when these changes are merged
to main. No manual version bump or tagging is needed.
```

Then ask:

> **Create a PR for these changes? (y/n) [default: n]**

If the user answers `n` or gives no answer: stop. Inform the user that no PR was
created and the branch is ready whenever they choose to open one.

If the user answers `y`: open a PR using the conventional commit messages on the
branch to populate the title and description. Do **not** bump versions, create tags,
or push commits beyond what is already staged.

## What This Skill Does NOT Do

- Does not bump version numbers (release-please reads conventional commits and bumps
  automatically when the release PR is merged)
- Does not create git tags (release-please creates the tag when the Release PR merges)
- Does not push commits or tags
- Does not create a GitHub Release (release-please creates it after the tag)
