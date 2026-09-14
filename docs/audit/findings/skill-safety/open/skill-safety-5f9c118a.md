---
id: skill-safety-5f9c118a
auditor: skill-safety
severity: medium
category: security
area: .claude/skills/graphify/SKILL.md
status: open
found: 2026-09-13
location: .claude/skills/graphify/SKILL.md:203-206
location_sha: 478b96dbea30521d
---

# Vendored graphify hands fetched web content to subagents that hold Write and Bash

## Problem

The skill mandates extraction through general-purpose subagents specifically because they have Write and Bash, and its `add` flow fetches arbitrary URLs into `./raw` for those subagents to read.

## Evidence

> **MANDATORY: You MUST use the Agent tool here.**
>
> **IMPORTANT - subagent type:** Always use `subagent_type="general-purpose"`. ... General-purpose has Write and Bash access which the subagent needs.

The enforcement reviewer read `references/add-watch.md`, where `/graphify add <url>` fetches a webpage, tweet or PDF into `./raw` for semantic extraction.

## Impact

A prompt-injection payload in a fetched page is read by a subagent that can run shell commands and write files in this repository.

## Fix

Have extraction subagents return their JSON as text for the parent to write, with no Bash; or require owner confirmation for each URL passed to `add`. Record the deviation in `NOTICE`.
