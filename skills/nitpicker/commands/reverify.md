# /nitpicker reverify — Findings-Store Re-Verification

Re-verifies every open finding in the store against the current code and gives
each an evidence-backed disposition: resolve the proven-fixed and proven-invalid,
keep the still-live open, flag the unverifiable for a human. It changes no code
and files no new findings — it only re-checks and resolves findings already on
record, keeping the store honest.

## When to use

- Before a release gate, so open findings reflect current code, not defects long
  since fixed
- After significant merges or refactors that may have fixed or moved earlier
  findings
- "re-verify the findings", "are these still valid", "clean up the findings
  store", "recheck open findings", "is the backlog current"

Not for finding new defects — that is the specific audit commands. `reverify`
only adjudicates what is already filed. When a defect has moved, it keeps the
finding open and records its current location in the report; it never files a
new finding.

`reverify` **uses** the findings store — it drives `np_list_findings` /
`np_resolve_finding` (else `findings.py list` / `resolve`) and the commit gate
exactly as `_conventions.md` defines. Two parts of that protocol are overridden:
it files **no new findings** (Run-protocol step 2 does not apply), and it applies
**no code fixes** (the `Apply fixes?` prompt does not apply — its only mutations
are finding resolutions). Everything else binds: run the Process as a task list,
redact evidence, and run the commit gate.

## The four dispositions

Re-read the current code at each finding's cited location — found by its quoted
Evidence, never by the stale line number — and assign exactly one:

- **still-live** — the defect, or its pattern, still exists in the current tree.
  Keep the finding **open**. If it moved, record the current location in the
  report — do not rewrite the finding file: the store has no update operation,
  and a finding's `area` is part of its content-hashed id, so a cross-file move
  cannot be edited in place (the owning auditor re-files it at the new area on
  its next run). Evidence: the still-present code.
- **fixed** — the defect was real and is now provably gone: the specific
  construct is absent **and** the surrounding code addresses the class (the
  concatenation is replaced by a parameterized query, not merely deleted and
  relocated). This is scoped to the finding's own cited location — confirm the
  finding's defect is fixed there; do not scan the repo for other instances of
  the class (that is the audit commands' job). Resolve `fixed`; the `--notes`
  cite the current code that proves it.
- **invalid** — re-examination shows the finding was **never a real defect** (a
  false positive). This is a claim about the finding's original correctness, not
  about code changing. Resolve `invalid`; the `--notes` give the technical
  reason it was wrong.
- **unverifiable** — the defect cannot be settled from the current tree: the
  cited location is gone and the defect cannot be located elsewhere, or
  confirmation needs off-repo state. **Do not resolve.** Keep the finding open,
  tagged unverifiable in the report, for a human to decide.

## Rules

- **Every open finding is adjudicated — no sampling.** List them all; give each a
  disposition backed by the current code. "Old, probably fixed" is not a
  disposition; age is not evidence. An unexamined finding stays open and is named
  in the report as un-reverified — never bulk-resolved. Pressure to "just clear
  the store" is refused and recorded.
- **`fixed` needs positive proof the defect class is gone, never just a missing
  line.** A grep that no longer matches the quoted snippet is a hint, not proof —
  read the current code and confirm the class is absent, not relocated or
  renamed. A defect that **moved** is still-live (record its new location in the
  report), never fixed.
- **A vanished location is not `invalid`.** `invalid` means the finding was wrong
  from the start. A deleted file or unrecognizably-rewritten code where the
  defect can no longer be found is **unverifiable** when you cannot tell, or
  **fixed** only when you can prove the defect's surface is genuinely removed
  (the whole feature was deleted). Never resolve a can't-find finding as invalid
  to clear it.
- **Search by the quoted Evidence, not the line number.** Cited line numbers
  drift after edits; the quoted code and its defect pattern are the anchor.
- **Resolution is per finding, with its own evidence.** Never batch-resolve a
  group on one judgement. Each `resolve` carries `--notes` citing the current
  code behind the decision, so the ledger stays auditable.

## Process

1. **List every open finding** (`status: open`; all auditors — narrow by
   `auditor` or area only if the extra instructions scope it). Copy the list
   into the task tracker, one entry per finding.
2. **Adjudicate each, in id order.** Read the finding's Evidence; locate the
   cited code in the current tree by its quoted snippet; assign one of the four
   dispositions with current-code evidence. Record the current location of a
   moved still-live defect.
3. **Resolve the settled ones** — resolve each `fixed` / `invalid` with `--notes`
   citing the current-code evidence. Leave still-live and unverifiable open.
4. **Refresh the index.**
5. **Report, then run the commit gate** — "Commit findings to git? (y/n)".

The store operations (list, resolve, index) and their MCP/CLI interface are
defined in `_conventions.md`; this command does not restate them.

## Output

```markdown
# Findings Re-Verification — <repo> (<date>)
Open findings re-verified: N

## Resolved
- <id> (<auditor>) — fixed — <current-code proof>
- <id> (<auditor>) — invalid — <why it was never a defect>

## Kept open
- <id> (<auditor>) — still-live — <current location, noted if moved>
- <id> (<auditor>) — unverifiable — <why it cannot be settled; needs human>

## Coverage
N/N open findings adjudicated — run verdict: COMPLETE.
Resolved: F fixed + I invalid. Kept open: L still-live + U unverifiable.
```

The Coverage line must sum to the open-finding count, and the run states a
verdict: **COMPLETE** when every open finding is adjudicated, **INCOMPLETE**
with the un-reverified ids listed when any was skipped. Every open finding is
examined — never a subset.

## Common mistakes

- **"These are old, the code moved, resolve them all fixed."** Age is not
  evidence; only current code is. Each `fixed` needs positive proof the defect
  class is gone. Refuse the bulk-close.
- **"The grep no longer matches, so it's fixed."** A missing snippet is a hint,
  not proof — read the code and confirm the class is gone, not relocated or
  renamed. A moved defect is still-live.
- **"The file was deleted, so the finding is invalid."** A vanished location is
  unverifiable (flag, keep open) or fixed (only if the defect's surface is
  provably removed) — never invalid. Invalid means the finding was wrong to
  begin with.
- **"30 findings, release in 20 minutes — spot-check a few."** Every open
  finding is adjudicated with its own current-code evidence; sampling silently
  keeps the rest un-reverified.
- **"Resolve fixed or invalid, whichever clears it."** `fixed` = the defect was
  real and is gone; `invalid` = it was never a defect. They are different
  claims; assign on the correct basis with the matching evidence.
