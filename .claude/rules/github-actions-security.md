---
paths:
  - ".github/workflows/**"
---

# GitHub Actions Hygiene

After editing any file under `.github/workflows/` (or a composite action's `action.yml`), run `zizmor --pedantic .` when `zizmor` is installed (detect with `command -v zizmor`) — the repository root discovers both workflows and composite actions — and resolve every finding before committing. When `zizmor` is not installed, skip this step and record that it was skipped.
Pin every third-party action to a full commit SHA with a trailing version comment, never a mutable tag or branch.
Declare a least-privilege `permissions:` block — `permissions: {}` at the workflow top level — and grant each job only the scopes it uses, documenting each scope with a trailing comment.
Give every job a `name:`, and set a `concurrency:` group on each workflow.

zizmor (pre-commit + CI) enforces the SHA-pin, least-privilege-permissions, and injection clauses automatically. The `name:`/`concurrency:` clause is not in zizmor's check set — it is verified in review, so state it explicitly whenever adding or editing a job.

## Pre-commit revs

The same SHA-pinning discipline covers every `rev:` in `.pre-commit-config.yaml`. Those repositories execute arbitrary code inside the authoritative `Validate` job, and a `rev:` naming a tag is mutable — the tag can be repointed at new code without the pin changing. Pin each `rev:` to the tag's full 40-character commit SHA with a trailing `# vX.Y.Z` comment, exactly as the workflows pin actions. Resolve a SHA with `git ls-remote <repo-url> refs/tags/<tag>^{}` (fall back to `refs/tags/<tag>` when the dereferenced form is absent) and confirm it is 40 hex characters before writing it.

zizmor does not audit `.pre-commit-config.yaml`, so this clause is verified in review. Renovate keeps the pinned revs current.
