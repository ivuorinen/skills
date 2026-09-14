---
paths:
  - ".github/workflows/**"
  - ".pre-commit-config.yaml"
  - "renovate.json"
  - "**/action.yml"
---

# GitHub Actions Hygiene

After editing any file under `.github/workflows/` (or a composite action's `action.yml`), run `zizmor --pedantic .` when `zizmor` is installed (detect with `command -v zizmor`) — the repository root discovers both workflows and composite actions — and resolve every finding before committing. When `zizmor` is not installed, skip this step and record that it was skipped.
Pin every third-party action to a full commit SHA with a trailing version comment, never a mutable tag or branch.
Declare a least-privilege `permissions:` block — `permissions: {}` at the workflow top level — and grant each job only the scopes it uses, documenting each scope with a trailing comment.
Give every job a `name:`, and set a `concurrency:` group on each workflow.

zizmor (pre-commit + CI) enforces the SHA-pin, least-privilege-permissions, and injection clauses automatically. The `name:`/`concurrency:` clause is not in zizmor's check set — it is verified in review, so state it explicitly whenever adding or editing a job.

## Which checks actually gate

A workflow that runs on every pull request blocks nothing unless the `main`
ruleset names its check. That ruleset is server-side GitHub configuration and is
invisible from a checkout, so the required set is recorded here: `Validate`,
`Lint PR title`, `Lint commit messages`, `Analyze (python)`, `Analyze (actions)`.

The two `Analyze` legs are CodeQL. They are named per matrix leg because the
matrix expands the job name — requiring the bare `Analyze` matches no check run
and silently gates nothing, which is the failure the pair was added to fix.
Adding a language to the CodeQL matrix therefore adds a required check that does
not exist yet, and every PR blocks until the ruleset names it too.

Read the live set with `gh api repos/<owner>/<repo>/rulesets/<id>` rather than
trusting this paragraph; a copy in prose is a copy that can go stale.

## Pre-commit revs

The same SHA-pinning discipline covers every `rev:` in `.pre-commit-config.yaml`. Those repositories execute arbitrary code inside the authoritative `Validate` job, and a `rev:` naming a tag is mutable — the tag can be repointed at new code without the pin changing. Pin each `rev:` to the tag's full 40-character commit SHA with a trailing `# <tag>` comment, exactly as the workflows pin actions. Write the tag **verbatim as upstream publishes it**, not a normalised version string: `PyCQA/bandit` and `python-jsonschema/check-jsonschema` tag `1.9.4` and `0.37.4` with no `v` prefix, and `v1.9.4` does not exist. That comment is what `renovate.json`'s custom manager hands the `github-tags` datasource as `currentValue`, so a comment naming a tag that does not exist upstream silently stops updates for that repo. Resolve a SHA with `git ls-remote <repo-url> refs/tags/<tag>^{}` (fall back to `refs/tags/<tag>` when the dereferenced form is absent) and confirm it is 40 hex characters before writing it — that same lookup proves the tag name going into the comment is real.

zizmor does not audit `.pre-commit-config.yaml`, so this clause is verified in review.

The version comment is not machine-checked for workflows either. The pre-commit
zizmor hook runs `--offline`, and the check that compares a comment against the
tag its SHA resolves to (`ref-version-mismatch`) needs the network, so a `# v4`
left on a `v4.37.9` pin passes the gate. Confirm the comment with the same
`git ls-remote` lookup, or an online `zizmor --pedantic .`, whenever a pin moves.

**Accepted risk: hook dependencies float.** The SHA pin fixes a hook
repository's own code, not what its environment installs. No hook here carries
`additional_dependencies` pins, so pre-commit resolves each hook package's
dependencies from the package index when it builds the environment: the Python
hooks install through pip with ranged requirements, and markdownlint-cli2 pins
its direct dependencies without a lockfile. A newly published transitive
release can therefore run inside `Validate` and on a developer machine without
any pin changing. This is accepted rather than closed, because exact pins for
every hook's dependency tree would be a second lockfile per hook that nothing
here generates or updates. Revisit it if a hook environment is ever implicated,
or if Renovate gains a way to maintain those pins.

Renovate keeps these revs current only because `renovate.json` carries a custom
regex manager for them. The built-in `pre-commit` manager cannot: it reads `rev:`
verbatim, so it versions a tag but not a 40-character SHA, and it has no support
for taking the version from a trailing comment — that is a `github-actions`
manager feature. SHA-pinning therefore makes a rev invisible to the built-in
manager, which is the opposite of what this clause reads like. Observed on PR #94:
ruff moved in `pyproject.toml`, the `Makefile`, the hook and `uv.lock` while the
pre-commit rev stayed behind, failing `test_every_ruff_call_site_names_the_same_version`.
Removing that custom manager silently reverts every rev here to unmaintained.
