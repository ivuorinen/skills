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

## Step 1 — Validate All Skills

Run `/validate-skills`. This validates both public skills (`skills/*/SKILL.md`) and
internal skills (`.claude/skills/*/SKILL.md`).

If any **errors** are reported: stop. Report the list of errors to the user. Do not
proceed until they are resolved.

Warnings must be reviewed; fix any that relate to skills being changed in this branch.

## Step 2 — Check Version Sync

```bash
uv run scripts/check-version-sync.py
```

All five files must agree on the same version: `package.json`,
`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
`.release-please-manifest.json`, and `pyproject.toml`.

If any file is out of sync: stop. Report which files differ and what their versions
are. Do not proceed.

## Step 3 — Security Scan

Run `/security-auditor`. If any Critical or High finding remains open after the scan:
stop. Report the findings to the user. Do not proceed.

## Step 4 — Documentation Accuracy

Run `/doc-auditor`. If any Critical finding remains open: stop. Report the findings.
High findings (missing API/boundary docs) must also be resolved before proceeding.
Medium and below may be deferred but must be tracked in `docs/audit/doc-findings.md`.

## Step 5 — Architecture Integrity

If `docs/audit/arch-profile.md` does not exist or is stale for the current branch,
run `/arch-detector` first to refresh it. Then run `/arch-auditor`. If any Critical
or High finding remains open: stop. Report the findings. Do not proceed.

## Step 6 — Exhaustive Code Review

Run `/nitpicker` in `release-gate` mode (threshold: High). If any Critical or High
finding remains open after fixes are applied: stop. Report the findings. Do not
proceed.

## Step 7 — Verify Conventional Commits

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

If any commit message does not follow conventional commits format: stop. Instruct the
user to amend the commit message before proceeding. Do not proceed until all commit
messages are valid — release-please generates `CHANGELOG.md` and the version bump
automatically from these messages when the PR merges to `main`.

Do **not** require or check for a manually-written `CHANGELOG.md` entry; release-please
manages the changelog.

## Step 8 — Confirm CI Is Green

Check `.github/workflows/validate-skills.yml` passed on the current commit. If CI is
failing: stop. Report which checks failed. Do not proceed.

## Gate Summary

After all steps pass, present this summary to the user:

```
✅ All release gates passed.

Steps completed:
  [✓] validate-skill.py — no errors
  [✓] check-version-sync.py — all 5 files agree on vX.Y.Z
  [✓] security-auditor — no Critical/High findings
  [✓] doc-auditor — no Critical/High findings
  [✓] arch-auditor — no Critical/High findings
  [✓] nitpicker release-gate — no Critical/High findings
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
