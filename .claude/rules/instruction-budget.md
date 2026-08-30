# Instruction Budget

`CLAUDE.md`, `AGENTS.md`, `.claude/CLAUDE.md` and `.claude/rules/*.md` are read
on every turn, whether or not the turn needs them. Claude Code spends part of
the window on its own instructions first — roughly 50 — so this set and the
harness draw on one budget.

## The limit

`skills/nitpicker/scripts/check-agent-instructions.py` counts list items and
imperative directives across the whole set. Above 150 it fails the gate; above
100 it reports. This repo sits at 102.

The count is of the *set*, not of any one file. A file that looks reasonable
alone still spends budget, which is why no per-file check finds this and why
splitting a long file into three short ones changes nothing on its own.

## Where content goes instead

| Content | Home |
| --- | --- |
| Applies to every turn | the always-loaded set |
| Applies to one path | `.claude/rules/<topic>.md` with `paths:` frontmatter |
| Applies to one task | a skill, loaded when its description triggers |
| Reference material | a file an instruction names, read on demand |

Moving a rule out of the always-loaded set does not weaken it. A path-scoped
rule still fires — it fires where it applies instead of everywhere, which is
what buys the budget back.

## Enforcement

Gated. `check-agent-instructions.py` runs in pre-commit and under `make check`,
and exits non-zero above the limit.

Two companion findings from the same tool report without blocking, because both
rest on judgement: `position_risk` for a directive titled in the middle of a
root file, and `cross_file_duplicate` for one directive stated in two files.
See [[counts-in-prose]] for the same drift in a different form.
