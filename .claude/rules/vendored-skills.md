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

## Keeping vendored content out of scans

`.claude/skills/.graphifyignore` excludes the symlinked `nitpicker/*` skill from
graphify's own scanning, so the shipped skill is not scanned twice. `.gitignore`
excludes graphify's generated output (`graphify-out/cost.json`,
`graphify-out/cache/`) from version control.
