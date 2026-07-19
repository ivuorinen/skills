# Commit Types

The commit type drives release-please, so it is a version declaration, not a
label. Pick it from what a *consumer* of the installed skill sees after the
change, never from how much work the change took.

## Which type

`feat:` — a new command, a new shipped capability, or a new gate wired into
`make check` or CI. A new enforcement gate is a feature: it changes what
passes the build for everyone who pins this repo.

`fix:` — repaired behaviour in something that already shipped. Nothing new.

`docs:` / `chore:` / `refactor:` / `ci:` — changes confined to `.claude/rules/`,
`CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`, `CONTRIBUTING.md`,
CI workflows, or the findings store. No path under `skills/` changed, so no
installed consumer sees a difference and no version bump is warranted.

`feat!:` / a `BREAKING CHANGE:` footer — a change that breaks an existing
consumer invocation. A workflow-only or CI-only dependency bump is never
breaking: it touches no published surface, so it carries no `!`. Strip the `!`
from any dependency-bot commit that touches only `.github/`.

## One commit, several types

Use the highest applicable type for the whole commit: a PR that adds a
validator and repairs a bug is `feat:`. Split the commit when the parts can
land separately — the release signal this repo depends on degrades once
multi-concern `fix:` commits become normal.

## Enforcement

`/nitpicker commits` audits for exactly these breaches. Nothing gates commit
type at commit time, so this rule is applied by the author and caught in
review; a wrong type that has already landed is corrected in the CHANGELOG
rather than by rewriting history.
