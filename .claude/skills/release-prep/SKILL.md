---
name: release-prep
description: Use when preparing a release of this plugin — verifies skills, versions, changelog, and CI before tagging.
disable-model-invocation: true
---

# Release Prep Checklist

Run these steps in order. Every step must pass before proceeding to the next.

## Step 1 — Validate All Skills

```bash
uv run scripts/validate-skill.py
```

All errors must be resolved. Warnings must be reviewed; fix any that relate to skills
being released in this version.

## Step 2 — Check Version Sync

```bash
uv run scripts/check-version-sync.py
```

All five files must agree on the same version: `package.json`,
`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
`.release-please-manifest.json`, and `pyproject.toml`.

## Step 3 — Security Scan

Run `/security-auditor`. Fix or document every Critical and High finding before
proceeding. A release with an open Critical security finding is blocked.

## Step 4 — Documentation Accuracy

Run `/doc-auditor`. Fix every Critical finding (actively misleads) and every High
finding (missing API/boundary docs). Medium and below may be deferred but must be
tracked in `docs/audit/doc-findings.md`.

## Step 5 — Architecture Integrity

If `docs/audit/arch-profile.md` does not exist or is older than the current release
cycle, run `/arch-detector` first. Then run `/arch-auditor`. Fix every Critical and
High finding before proceeding.

## Step 6 — Exhaustive Code Review

Run `/nitpicker` in `release-gate` mode (threshold: High). The release is blocked if
any Critical or High findings remain open after fixes are applied.

## Step 7 — Review CHANGELOG

Confirm an entry exists for the version being released with accurate feature and fix
descriptions. Run `/doc-auditor` inline on CHANGELOG.md if the release notes are
substantive.

## Step 8 — Confirm CI Is Green

Check `.github/workflows/validate-skills.yml` passed on the current commit. Do not
tag a release with a failing CI run.

## Step 9 — Bump Version (if needed)

```bash
./scripts/bump-version.py [major|minor|patch]
```

| Prefix | Version bump |
|--------|-------------|
| `feat:` | minor |
| `fix:` | patch |
| `feat!:` / `BREAKING CHANGE:` | major |
| `chore:`, `docs:`, `refactor:` | none |

## Step 10 — Stage and Commit

User does this manually:

```bash
git add -A
git commit -m "chore: release v<version>"
git tag v<version>
git push && git push --tags
```

## Release Gate Summary

A release is **blocked** if any of the following are open:

- [ ] Validation errors from `validate-skill.py`
- [ ] Version sync mismatch
- [ ] Critical or High security findings (security-auditor)
- [ ] Critical documentation findings (doc-auditor)
- [ ] Critical or High architecture violations (arch-auditor)
- [ ] Critical or High code findings (nitpicker release-gate)
- [ ] Missing CHANGELOG entry for this version
- [ ] Failing CI on the current commit
