---
paths:
  - "docs/audit/findings/**"
  - "skills/nitpicker/scripts/findings*.py"
  - "skills/nitpicker/commands/_findings-store.md"
  - "tests/test_findings*.py"
---

# Findings Store

`AGENTS.md` states the store's shape and who may write it. This file holds the
detail a change to the store or its tooling needs.

Resolving a finding appends its record to the append-only
`docs/audit/findings/resolved.jsonl` ledger and deletes its
`<auditor>/open/<id>.md` file, so the tree does not accumulate resolved files.

`INDEX.md` is generated: the index (rebuilt by findings.py and by the
PostToolUse hook `validate-audit-findings-hook.py`) is tool output, not a file
to hand-edit. An in-store `.gitattributes`, self-written by findings.py, marks
the store `linguist-generated` so audit runs don't flood PR diffs.

`commands/_findings-store.md` maps every operation to its interface — an `np_*`
MCP tool or the CLI — and names the ones no tool wraps. Read it there rather
than keeping a second list here. `python3 skills/nitpicker/scripts/findings.py
--help` lists every subcommand.

IDs are content-hashed rather than hand-assigned. `new --force` re-opens a
resolved finding under the id it already had, dropping its ledger record; that
is the one route by which an id in the ledger comes back.

`migrate` converts 1.x `docs/audit/*-findings.md` documents. `migrate-resolved`
folds a legacy `<auditor>/resolved/*.md` tree into the ledger.

`export --format sarif|json|junit` (in `findings_export.py`) renders the store
for another system. The Static Analysis Results Interchange Format (SARIF) —
what a code-scanning UI ingests — omits resolved findings, since an alert on a
fixed defect is indistinguishable from a live one. JUnit maps open to failure
and resolved to pass, so a CI panel shows unfixed findings beside failing tests.

`new --location path:START-END` records where the evidence was read — START (the
first cited line) and END (the last) — plus a fingerprint of that source.
`recheck` re-computes every one, so `reverify` can skip a finding whose cited
bytes are unchanged rather than spend a model pass on it.

The fingerprint covers the cited line range, so an unrelated edit *above* it
reads as `changed`. That is the safe direction: it costs a re-check rather than
a missed change. `location` is deliberately outside the content-hashed id.

## Enforcement

Partly gated. The PostToolUse hook `validate-audit-findings-hook.py` validates
edited open findings and the ledger and regenerates the index;
`findings.py validate` runs in pre-commit and as `make audit-consistency`, and
`make index-check` fails an index that regeneration would change. A hand edit
that leaves the store valid and the index current passes all of them, so the
no-hand-edit rule in `AGENTS.md` stays agent discipline.
