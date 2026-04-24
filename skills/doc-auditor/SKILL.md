---
name: doc-auditor
description: Use when verifying documentation accuracy against the codebase, finding stale or missing docs, detecting incorrect behavior descriptions, or applying documentation improvements. Triggers: "audit the docs", "find stale documentation", "verify docs against code", "run doc-auditor", "is the documentation accurate?", "find missing docs".
---

# Documentation Auditor

## Overview

Hostile documentation review. Assumes every claim in every doc is wrong until verified against the codebase. Two-directional: docs→code (does code match the claim?) and code→docs (is this code undocumented?). Every finding includes the document source, the false or missing claim, and a concrete fix.

## When to Use

- When documentation may have drifted from the codebase
- Before a release to verify docs accuracy
- When onboarding reveals confusion about what's documented vs. what's real
- After a significant refactor

**When NOT to use:** For architecture-specific documentation drift, run `arch-auditor` instead — it validates structural claims against the detected architecture.

## Documentation Scanned

- `README.md` at any directory level
- `docs/` directories (excluding `docs/audit/` — its own output)
- Inline comments and docstrings
- Architecture Decision Records (ADRs)
- Changelogs
- OpenAPI / Swagger / AsyncAPI specs
- Configuration file comments
- Test names and descriptions (they document expected behavior)

## Finding Types

| Type | Description |
|------|-------------|
| **Stale** | References a function, class, module, file, or parameter that no longer exists or has been renamed |
| **Incorrect** | Documented behavior contradicts implementation — wrong parameters, wrong return type, wrong description of what the code does |
| **Missing** | Public API, exported function, architectural boundary, or module with no documentation |
| **Outdated architecture** | Describes a structural pattern, layer, or component that has changed or been removed |
| **Contradiction** | Two documentation sources make conflicting claims about the same thing |
| **Broken link** | Internal link to a file, heading, or section that does not resolve |

## Severity Model

| Severity | Meaning |
|----------|---------|
| Critical | Actively misleads — incorrect behavior description that would cause wrong usage of the code |
| High | Missing documentation for a public API or architectural boundary |
| Medium | Stale reference, outdated architecture description, contradiction |
| Low | Broken internal link, minor inaccuracy, test name that misrepresents behavior |

## Fix Types

| Fix | Applied automatically after asking |
|-----|--------------------------------------|
| Remove stale references | Yes |
| Update renamed identifiers | Yes |
| Fix broken internal links | Yes |
| Generate missing docs from code | Yes — inferred from signatures, types, and context |
| Update incorrect behavior descriptions | Yes — rewritten from actual implementation |
| Update architecture descriptions | Yes — rewritten from `docs/audit/arch-profile.md` if present |
| Resolve contradictions | Yes — picks the version consistent with code; notes the resolution |

## Single-Shot Behavior

```
1. Collect all documentation sources (see Documentation Scanned above)
2. Create docs/audit/ if it does not exist
3. If docs/audit/doc-findings.md exists:
     Re-validate each OPEN finding:
     - Issue resolved → move to Fixed (record date)
     - Finding was wrong → move to Invalid (record reason)
     - Still present → leave as Open
4. Audit all docs against codebase (both directions)
5. Add new findings (assign next available ID — never reuse IDs)
6. Present findings summary
7. Ask: "Apply fixes now? (y/n)"
   If yes: apply fixes, re-validate, update findings file
8. Write docs/audit/doc-findings.md
9. Ask: "Commit findings to git? (y/n)" — never commit silently
```

## Findings Format

```
# Documentation Audit Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N

## Open Findings

### Critical

#### [ID] Short title
Category: <stale|incorrect|missing|outdated-architecture|contradiction|broken-link>
Source: <path to the document containing the claim>
Claim: <the exact claim made in the document>
Evidence: <what the code actually does — file path and relevant detail>
Fix: <minimal correction>

### High
[same structure]

### Medium
[same structure]

### Low
[same structure]

## Fixed

#### [ID] Short title
Fixed: YYYY-MM-DD
Notes: <what changed>

## Invalid

#### [ID] Short title
Notes: <why this finding was wrong>
```

## Rules

- No benefit of the doubt — every doc claim is a suspect until verified
- Every finding must include the source document path and the exact claim being challenged
- Silence = approval — if something is not flagged, that IS your approval
- Apply only minimal fixes — correct the claim, do not rewrite the document
- Do not flag style or tone — only factual accuracy and completeness
