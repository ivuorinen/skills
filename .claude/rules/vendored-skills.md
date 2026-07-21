# Vendored Skills

A vendored skill is authored by someone else and installed into this repo rather
than written by us — `graphify`, installed via `/graphify`, is the current
example. Vendored skills do not follow our SKILL.md conventions, and the
validators never hold them to those conventions.

## Skip mechanism

`scripts/validate-skill.py` skips vendored skills by directory name through its
`VENDORED_SKILLS` allowlist. A vendored skill's SKILL.md is never validated —
not through auto-discovery, not when passed as an explicit argument. The
validator prints a `SKIP` line for each one so the omission stays visible.

## Governance

`VENDORED_SKILLS` is human-curated and owner-approved. It contains only vendored
skills the repo owner has explicitly approved. `graphify` is the sole approved
entry.

An agent never adds an entry to `VENDORED_SKILLS` on its own. A non-authored
skill that appears in the repo requires the owner's explicit confirmation before
its name goes on the allowlist. The `test_allowlist_contains_only_approved_entries`
test in `tests/test_validate_skill.py` pins the exact set; a new entry fails that
test until the owner approves it. Resolve a failure by removing the unapproved
entry or by obtaining approval — never by editing the test to match.

The allowlist and the test that pins it live in the same tree the agent edits,
so the assertion alone is not a control — a two-line diff satisfies both.
The intended human gate is `.github/CODEOWNERS` owning `scripts/validate-skill.py`
and `tests/test_validate_skill.py`, so a human sees every allowlist change.

That gate is now LIVE: `.github/CODEOWNERS` is tracked in git, and the active
`main` ruleset sets `require_code_owner_review` true, so a code-owner review is
required on every PR that touches the allowlist or its pinning test — an agent
cannot widen `VENDORED_SKILLS` without a human on the review.

## Provenance

Vendored content is redistributed under its upstream license, never under this
repo's. A vendored skill carries `<skill-dir>/LICENSE` containing the verbatim
upstream license text and copyright notice, and an entry in the root `NOTICE`
naming the upstream repository, author, version, and SPDX identifier. Both
exist before the skill's name goes on `VENDORED_SKILLS`;
`test_vendored_skills_carry_a_license` in `tests/test_validate_skill.py`
enforces the LICENSE half.

The same obligation covers adapted content, not only wholly vendored skills:
whenever an "Adapted from" line is added to a command file, that upstream gets
a `NOTICE` entry. A prose credit names the author but reproduces neither the
copyright notice nor the permission notice MIT requires be carried in all
copies.

## Keeping vendored content out of scans

`.claude/skills/.graphifyignore` excludes the symlinked `nitpicker/*` skill from
graphify's own scanning, so the shipped skill is not scanned twice. `.gitignore`
excludes graphify's generated output (`graphify-out/cost.json`,
`graphify-out/cache/`) from version control.
