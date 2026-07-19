# /nitpicker baseline — Accepted-Findings Ratchet

Snapshot the current open findings as an accepted baseline so `release-gate`
fails only on findings filed after it — adopting the toolkit on a repo with
pre-existing debt without deleting, falsifying, or hiding a single real finding.

## When to use

Turning the release gate on for the first time against a mature repo that
already has findings; "baseline the findings", "accept the current findings",
"ratchet the gate", "grandfather existing debt", "only fail on new findings". A
repo with no open findings has nothing to baseline — say so and stop.

## Mindset

Every pre-existing finding stays a real, open, visible finding. A baseline
waives it from the gate, never from the truth. The forbidden move — in all its
disguises — is making the gate pass by changing what the store says instead of
accepting the debt honestly. A finding at a new area or title gets a new id, so
genuine new problems are never in the baseline and block the gate. Ids hash
auditor+area+title (not the finding body): a regression reusing an
already-baselined auditor+area+title reuses that id, and `findings.py` refuses
to file it as a duplicate — it surfaces as a file-time error, never a silent
waive.

## Procedure

```text
1. Set the baseline:
     python3 findings.py baseline
   Writes docs/audit/findings/baseline.json = every currently-open finding id
   plus the date. Commit it: `chore: baseline pre-existing findings`.
2. Gate on new findings only:
     python3 findings.py list --status open --exclude-baseline
   release-gate reads this: any open finding at or above the threshold whose id
   is NOT baselined fails the gate; baselined debt is waived.
3. Pay down debt: resolve each as `fixed` (`np_resolve_finding`, else
   `findings.py resolve <id> --status fixed`) as it is truly
   fixed — it leaves open/ and drops out of the gate on its own.
4. Do not re-baseline to "clean up". A resolved finding drops from the gate
   whether or not it stays in the baseline (step 3), so a stale baselined id is
   inert. `findings.py baseline` refuses to overwrite an existing baseline —
   reset only via `--clear` then a fresh baseline, or `--force` after reviewing
   the baseline.json diff.
```

## Rules

- The baseline records ids only. It never changes a finding's status, severity,
  area, or body. A baselined finding is still `open` and still in the store.
- Adding an id to the baseline is a committed, diffable change a human reviews.
  Waiving a finding is possible but never silent and never automatic.
- The ratchet only tightens. `findings.py baseline` refuses to overwrite an
  existing baseline; resetting it (`--clear`, or `--force` on a reviewed diff)
  is a deliberate human act, never an automatic re-run.
- The gate threshold is orthogonal to the baseline. Do not lower or raise the
  threshold to hide a finding you could baseline instead.

## Common mistakes

Each is the same forbidden move — make the check pass without changing the truth
it checks:

- Resolving pre-existing findings as `invalid` or `fixed` to clear the gate: a
  false ledger record. They are neither wrong nor fixed — baseline them.
- Lowering the gate threshold, or raising it out of reach, so the debt no
  longer trips it — this also blinds the gate to new findings at that level.
- `git rm`, `git mv` out of `open/`, editing a severity down, or gitignoring
  the store to keep findings out of the checkout.
- CI `continue-on-error`, `|| true`, or `if: false` on the gate step — a gate
  wired to always pass is not a gate.
- Running the gate only over changed files so pre-existing findings fall out of
  scope — baselining by omission, unreviewable.
- Re-baselining on every run so any new finding is instantly absorbed — the
  ratchet must only tighten, never reset forward.
