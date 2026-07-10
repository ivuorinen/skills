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
