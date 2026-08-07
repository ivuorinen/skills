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

The same SHA-pinning discipline covers every `rev:` in `.pre-commit-config.yaml`. Those repositories execute arbitrary code inside the authoritative `Validate` job, and a `rev:` naming a tag is mutable — the tag can be repointed at new code without the pin changing. Pin each `rev:` to the tag's full 40-character commit SHA with a trailing `# <tag>` comment, exactly as the workflows pin actions. Write the tag **verbatim as upstream publishes it**, not a normalised version string: `PyCQA/bandit` and `python-jsonschema/check-jsonschema` tag `1.9.4` and `0.37.4` with no `v` prefix, and `v1.9.4` does not exist. That comment is what `renovate.json`'s custom manager hands the `github-tags` datasource as `currentValue`, so a comment naming a tag that does not exist upstream silently stops updates for that repo. Resolve a SHA with `git ls-remote <repo-url> refs/tags/<tag>^{}` (fall back to `refs/tags/<tag>` when the dereferenced form is absent) and confirm it is 40 hex characters before writing it — that same lookup proves the tag name going into the comment is real.

zizmor does not audit `.pre-commit-config.yaml`, so this clause is verified in review.

Renovate keeps these revs current only because `renovate.json` carries a custom
regex manager for them. The built-in `pre-commit` manager cannot: it reads `rev:`
verbatim, so it versions a tag but not a 40-character SHA, and it has no support
for taking the version from a trailing comment — that is a `github-actions`
manager feature. SHA-pinning therefore makes a rev invisible to the built-in
manager, which is the opposite of what this clause reads like. Observed on PR #94:
ruff moved in `pyproject.toml`, the `Makefile`, the hook and `uv.lock` while the
pre-commit rev stayed behind, failing `test_every_ruff_call_site_names_the_same_version`.
Removing that custom manager silently reverts every rev here to unmaintained.
