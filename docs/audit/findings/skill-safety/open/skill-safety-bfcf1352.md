---
id: skill-safety-bfcf1352
auditor: skill-safety
severity: low
category: security
area: .claude/skills/graphify
status: open
found: 2026-09-28
location: .claude/skills/graphify/SKILL.md
---

# Residual risk: installed agent configuration was read in the acting context because no tool-restricted reader exists

## Problem

The skill-safety Reading protocol requires a reader holding file-read tools only. Every available subagent type carries Bash, so the vendored graphify unit, and the machine-local trees on the owner's explicit choice, were read by agents holding shell and write tools (isolation rule 3).

## Evidence

Agent tool listing: Explore holds 'All tools except Agent, Artifact, …, Edit, Write, NotebookEdit', so Bash is included. No payload was confirmed, so rule 4 was not triggered.

## Impact

Attacker-authorable text reached an agent holding Bash and repo write access during the audit.

## Fix

Provide a read-only reader agent definition (tools: Read, Grep, Glob) for skill-safety runs.
