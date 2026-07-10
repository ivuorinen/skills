---
name: release-prep
description: Use when validating that all changes in the current branch are ready to be included in a release PR managed by release-please automation.
disable-model-invocation: true
---

# Release Prep Checklist

Validates that the repository is in a clean, releasable state. Does **not**
create tags, bump versions, or push commits — release-please automation
manages all of that from `main`. The only action beyond validation is
offering to open a PR, and only after every gate passes and the user
explicitly approves.

Run the steps in order. **Stop immediately and report findings to the user
if any step fails.** Do not proceed to the next step.

## Step 1 — Validate Skills and Version Sync

Run `/validate-skills`. It validates the public skill (router + command
files) and internal skills, plus the version-sync check
(`scripts/check-version-sync.py`). Any error: stop and report. Warnings
touching files changed in this branch must be fixed.

## Step 2 — Audit Gates

Run each gate command in this order. A gate passes when no Critical or High
finding remains open in the findings store after fixes are applied
(`python3 skills/nitpicker/scripts/findings.py list --status open`).
Any gate with an open Critical/High finding: stop and report.

| Gate                    | Command                                                                                                                                        |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Security                | `/nitpicker security`                                                                                                                          |
| Documentation accuracy  | `/nitpicker docs` (Critical and High must be resolved; Medium and below may be deferred as open findings)                                      |
| Architecture            | `/nitpicker arch` (refreshes the profile via `/nitpicker arch-profile` when missing or stale — staleness per that command's git-metadata rule) |
| Exhaustive review       | `/nitpicker audit`                                                                                                                             |
| Enforcement loopholes   | `/nitpicker agent-loopholes`                                                                                                                   |
| Hook coverage           | `/nitpicker agent-hooks`                                                                                                                       |
| Performance             | `/nitpicker perf`                                                                                                                              |
| Test-suite strength     | `/nitpicker tests`                                                                                                                             |
| Dependency health       | `/nitpicker deps`                                                                                                                              |
| Error handling          | `/nitpicker errors`                                                                                                                            |
| Migration safety        | `/nitpicker migrations`                                                                                                                        |
| Observability           | `/nitpicker observability`                                                                                                                     |
| API contract            | `/nitpicker contract`                                                                                                                          |
| Accessibility           | `/nitpicker a11y`                                                                                                                              |
| CI/CD pipeline          | `/nitpicker ci`                                                                                                                                |
| Commit discipline       | `/nitpicker commits`                                                                                                                           |
| Concurrency safety      | `/nitpicker concurrency`                                                                                                                       |
| Internationalization    | `/nitpicker i18n`                                                                                                                              |
| Resource lifecycle      | `/nitpicker leaks`                                                                                                                             |
| Configuration           | `/nitpicker config`                                                                                                                            |
| Data privacy            | `/nitpicker privacy`                                                                                                                           |
| Unwired implementations | `/nitpicker unwired`                                                                                                                           |

No-surface verdicts ("no auditable UI surface", "no localization surface",
"no personal-data surface") pass their gate.

## Step 3 — Release Gate

Run `/nitpicker release-gate`. It fails on any open finding at High or above
across all auditors — this is the aggregate backstop after the per-gate
fixes. If it fails: stop and report.

## Step 4 — Verify Conventional Commits

Confirm every commit on this branch follows the conventional commits format
release-please uses for version bumps and release notes:

- `feat:` — minor bump; `fix:` — patch bump
- `feat!:` or `BREAKING CHANGE:` footer — major bump
- `chore:`, `docs:`, `refactor:` — no bump

```bash
git log main..HEAD --oneline
```

Any non-conforming message: stop; instruct the user to reword via
`git rebase -i main`. Do **not** require a manual `CHANGELOG.md` entry —
release-please manages the changelog.

## Step 5 — Confirm CI Is Green

Check `.github/workflows/validate-skills.yml` passed on the current commit.
Failing CI: stop and report which checks failed.

## Gate Summary

After all steps pass, present:

```text
✅ All release gates passed.

  [✓] validate-skills — no skill errors; all 5 version files in sync at vX.Y.Z
  [✓] all audit gates — no open Critical/High findings (see INDEX.md)
  [✓] /nitpicker release-gate — PASS (threshold High)
  [✓] conventional commits — all commits on branch use valid format
  [✓] CI — validate-skills.yml passing

Release-please automation will create the Release PR when these changes are
merged to main. No manual version bump or tagging is needed.
```

Then ask:

> **Create a PR for these changes? (y/n) [default: n]**

`n` or no answer: stop; inform the user no PR was created. `y`: open a PR
using the branch's conventional commit messages for title and description.
Do **not** bump versions, create tags, or push beyond what is staged.

## What This Skill Does NOT Do

- Does not bump version numbers, create git tags, or push commits/tags
- Does not create a GitHub Release (release-please does, after the tag)
