---
id: agent-hooks-eaa13a08
auditor: agent-hooks
severity: medium
category: reliability
area: scripts/hooks
status: open
found: 2026-09-13
location: CLAUDE.md:221-223
location_sha: d5f72fe38fb8775d
---

# No hook stops findings-store MCP writes while shipped scripts are modified

## Problem

CLAUDE.md requires switching to the findings CLI after editing anything under `skills/*/scripts/`, because the running MCP server keeps executing the code it imported. Only a non-blocking `[warn]` prefix backs that mandate, and `np_process_sarif` carries no warning at all.

## Evidence

> So after editing anything under `skills/*/scripts/`, drive the findings store through `python3 skills/nitpicker/scripts/findings.py` for the rest of the session

The ledger records audit-9bc6eb39: a stale server's pre-fix `redact()` wrote an unredacted credential into the append-only ledger.

## Impact

An agent that misses the prose keeps writing permanent ledger records through code that no longer matches the working tree.

## Fix

Add a PreToolUse hook matching `mcp__nitpicker__np_(new_finding|resolve_finding|write_index|process_sarif)` and the plugin-scoped equivalents that exits 2 when `git status --porcelain -- skills/nitpicker/scripts` is non-empty, naming the CLI command to use instead.
