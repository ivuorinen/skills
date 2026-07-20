# /nitpicker release-gate — Findings Threshold Gate

Pass/fail gate over the findings store. Writes nothing, fixes nothing.

## When to use

Release readiness checks, CI gates, "can we ship", "run the release gate".

## Behavior

```text
1. python3 findings.py list --status open
   CLI, not np_list_findings: the MCP tool has no exclude_baseline argument,
   so it cannot express the waiver this gate depends on.
   If docs/audit/findings/baseline.json exists, add --exclude-baseline so
   findings accepted by `/nitpicker baseline` are waived (they stay open). If
   baseline.json exists but does not parse, report "baseline unreadable — no
   findings waived" and gate on the full open set; never silently skip it.
2. Threshold: High, unless the extra instructions name another severity
   (e.g. "/nitpicker release-gate medium").
3. Any open finding at or above the threshold → report each (id, severity,
   auditor, title) and FAIL the gate.
4. None → report "release gate: PASS (threshold <level>)" with the open
   counts below threshold for visibility. When a baseline is in effect, report
   the baselined count too, so waived debt stays visible.
```

The gate never resolves, edits, or files findings — disputes with a finding
are settled by running its auditor command, not by the gate. It never lowers
the threshold or edits the baseline to pass; pre-existing debt is waived only
through `/nitpicker baseline`. The `changed-files` modifier does not apply: the
gate always reads the full open set, never a diff-scoped subset.
