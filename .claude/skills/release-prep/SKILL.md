---
name: release-prep
description: Use when preparing a release of this plugin — verifies skills, versions, changelog, and CI before tagging.
disable-model-invocation: true
---

# Release Prep Checklist

## Steps

1. **Validate all skills**
   ```bash
   uv run scripts/validate-skill.py
   ```
   All errors must be resolved. No blocking errors allowed.

2. **Check version sync**
   ```bash
   uv run scripts/check-version-sync.py
   ```
   All four files must agree on the same version.

3. **Review CHANGELOG.md** — confirm an entry exists for the version being released.

4. **Confirm CI is green** — check `.github/workflows/validate-skills.yml` passed on the current commit.

5. **Bump version if needed**
   ```bash
   ./scripts/bump-version.py [major|minor|patch]
   ```
   Use `minor` for new skills, `patch` for fixes, `major` for breaking changes.

6. **Stage and commit** (user does this manually):
   ```bash
   git add -A
   git commit -m "chore: release v<version>"
   git tag v<version>
   git push && git push --tags
   ```

## Conventional commit types

| Prefix | Version bump |
|--------|-------------|
| `feat:` | minor |
| `fix:` | patch |
| `feat!:` / `BREAKING CHANGE:` | major |
| `chore:`, `docs:`, `refactor:` | none |
