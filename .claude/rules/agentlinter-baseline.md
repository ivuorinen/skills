---
paths:
  - ".agentlinter-baseline.json"
  - "scripts/check-agentlinter.py"
---

# The Agentlinter Baseline

Codacy's other engine is Agentlinter, which lints `CLAUDE.md`, `AGENTS.md`,
`.claude/rules/` and the command files. `make agentlinter` reproduces it from a
checkout, closing the gap `make opengrep` closed for the first engine.
`scripts/check-agentlinter.py`'s docstring carries the rest: the pinned version,
the mandatory `--local`, and why the gate parses `--json` (it exits 0 regardless).

It gates against `.agentlinter-baseline.json`, not on severity: every `critical`
it reported here was a false positive, so a severity gate would fail forever on
noise. A new diagnostic fails the build — fix it, or accept it with `make
agentlinter-update`. An entry that stops firing is reported and fails nothing.

Every baselined rule carries a written justification in that file's `reasons`
map; the gate fails on one that does not, and `--update` preserves them. Without
it a baseline cannot be told from a list of things nobody read. Every entry was
audited against source when it was recorded; `git log` on the baseline file
dates each audit.

## Enforcement

Gated. `make agentlinter` fails on a diagnostic missing from the baseline and on
a baselined rule with no `reasons` entry. Whether a justification is true is
checked in review.
