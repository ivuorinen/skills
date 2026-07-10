---
id: audit-d6cf30cd
auditor: audit
severity: advisory
category: reliability
area: skills/nitpicker/scripts/findings.py:167
status: open
found: 2026-07-10
---

# 32-bit content-hash id gives a per-auditor birthday-collision ceiling

## Problem

`finding_id` truncates the SHA-256 to 8 hex chars (32 bits) within each auditor namespace, so collision probability becomes non-negligible at large per-auditor finding counts.

## Evidence

`return f"{auditor}-{digest[:8]}"` (line 168-169). At roughly 77k findings for a single auditor the 32-bit birthday-collision probability crosses 50%. The collision is *detected* — `new_finding` raises "id collision with different finding" (line 521) rather than overwriting — so this is a capacity ceiling, not corruption.

## Impact

At very large scale a distinct finding can be rejected because its id collides with an existing one. Not reachable at any realistic audit volume.

## Fix

Widen the truncation (e.g. `digest[:12]`) if large per-auditor volumes are ever expected; otherwise leave as-is — the ceiling is documented here.
