# /nitpicker release-gate — Findings Threshold Gate

Pass/fail gate over the findings store. Writes nothing, fixes nothing.

## When to use

Release readiness checks, CI gates, "can we ship", "run the release gate".

## Behavior

```text
1. python3 findings.py list --status open
2. Threshold: High, unless the extra instructions name another severity
   (e.g. "/nitpicker release-gate medium").
3. Any open finding at or above the threshold → report each (id, severity,
   auditor, title) and FAIL the gate.
4. None → report "release gate: PASS (threshold <level>)" with the open
   counts below threshold for visibility.
```

The gate never resolves, edits, or files findings — disputes with a finding
are settled by running its auditor command, not by the gate.
