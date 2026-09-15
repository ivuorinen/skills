---
paths:
  - "scripts/**"
  - "skills/**"
---

# Suppression Markers

Two scanners run over `skills/` and `scripts/`, and each has its own marker:
`# nosec` for bandit, `# nosemgrep` for opengrep. `make opengrep` gates the
second, and `scripts/check-opengrep.py` is the tool.

opengrep is the scanner Codacy reports code findings from, and its ruleset lived
only in the Codacy UI — so a finding was invisible from a checkout and
reproducible only by pushing. Two commits went to configuring bandit before the
owner pointed out which engine was actually reporting. `make opengrep` runs
`r/python.lang.security.audit`, the namespace that reproduces those findings
(`p/python` returns nothing here; it omits the `-audit` rule variants).

**A `# nosemgrep` marker only counts on the finding's own line or the line
directly above it.** One line further up is ignored silently — no warning, no
diff, the finding just quietly comes back. A reason comment therefore belongs
*above* the marker: one placed between the marker and the code separates the
two, and the suppression stops applying.

So the gate also runs a second pass with `--disable-nosem` and fails on any
marker that lines up with no revealed finding. That catches the misplaced marker
and the leftover one that outlived its call. Nothing else checks this; Codacy
does not.

Two things worth knowing before trusting a clean run:

- Staleness is judged only against the configured namespace, so suppressing a
  rule outside it means widening `CONFIG` first, or the marker reads as stale.
- Markers outside the scanned roots are judged neither way; the count is printed
  rather than passed over silently.

A scan error fails the gate. opengrep skips a file it cannot parse, so a parse
error means unscanned code, and reporting the remainder as clean would hide it.
This is also why the gate runs opengrep rather than semgrep: semgrep 1.172.0
cannot parse a `match` statement and drops the whole file, and this repo uses
them.

Locally the target skips when opengrep is absent; under CI it fails instead,
because a gate that skips silently is not a gate. The `Validate` workflow
installs a version-pinned, digest-verified binary before `make check`.

## Enforcement

Gated for `# nosemgrep`: `make opengrep` fails on a marker that suppresses no
finding, which covers the misplaced reason comment. A `# nosec` marker has no
staleness pass.
