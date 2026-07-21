---
id: audit-29fe757a
auditor: audit
severity: low
category: security
area: GitHub ruleset "main" (repos/ivuorinen/skills) — bypass_actors
status: open
found: 2026-07-21
---

# Ruleset bypass_actors grants the admin role bypass_mode "always", allowing direct unvalidated pushes to main

## Problem

The active `main` ruleset carries `bypass_actors: [{RepositoryRole admin, bypass_mode: "always"}]`. `always` (not `pull_request`) means that role can push directly to `main`, bypassing the required `Validate` check, code-owner review, signature, and linear-history rules entirely — not just waive PR review.

## Evidence

`gh api repos/ivuorinen/skills/rulesets/15530545` → `bypass_actors: [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}]` (actor_id 5 = admin). commit-gate-integrity.md presents "a merge that bypasses [Validate] lands on main unvalidated" as a thing to prevent.

## Impact

A holder of the admin role can land a commit on `main` (e.g. widening `VENDORED_SKILLS`) with no check run. Admin always-bypass is a common GitHub default, hence Low, but it contradicts the repo's own stated gate-integrity control.

## Fix

Narrow the bypass to `pull_request` mode (or remove it) so even privileged actors route through the required check; keep any break-glass path in `pull_request` mode so review/checks still apply on merge.
