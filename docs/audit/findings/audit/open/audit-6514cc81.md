---
id: audit-6514cc81
auditor: audit
severity: medium
category: reliability
area: GitHub ruleset "main" (repos/ivuorinen/skills) — required_status_checks
status: open
found: 2026-07-20
---

# Only "Validate" is a required check; a non-conventional PR title merges and breaks the release signal

## Problem

The active `main` ruleset lists `required_status_checks` = `["Validate"]` only. The `Lint PR title` job (pr-title.yml) and the `Lint commit messages` job (validate-skills.yml) are not required contexts, so a red X on either does not block merge.

## Evidence

`gh api repos/ivuorinen/skills/rulesets/15530545` → the `required_status_checks` rule's contexts are `["Validate"]`. The repo depends on "squash subject = PR title" for its release signal (`.pre-commit-config.yaml` commit-lint + release-please). A PR titled `update stuff` fails `pr-title` but passes `Validate`, so the merge is allowed; the squash subject `update stuff` is unparseable and release-please ships no version bump.

## Impact

The one gate protecting the conventional-commit release signal is advisory. A merged non-conventional title silently prevents a release from versioning correctly.

## Fix

Add `Lint PR title` (and, if relied on, `Lint commit messages`) to the ruleset's `required_status_checks` contexts so a red title check blocks merge.
