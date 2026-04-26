---
name: arch-auditor
description: Use when auditing a codebase for architectural violations, dependency rule breaches, layer boundary violations, or pattern inconsistencies. Triggers: "audit the architecture", "find architecture violations", "check layer boundaries", "run arch-auditor", "are there any DDD violations?", "check hexagonal boundaries".
---

# Architecture Auditor

## Overview

Hostile architectural audit. Assumes violations exist and hunts for proof. Validates the codebase against its detected (or declared) architecture. Every finding includes the violated rule, concrete evidence, and a minimal fix.

## When to Use

- After `arch-detector` has produced `docs/audit/arch-profile.md` (uses it if present)
- When you suspect architectural drift or layer boundary violations
- As a release gate check on architectural integrity

**When NOT to use:** If you don't yet know what architecture the project uses, run `arch-detector` first — it produces the profile this skill uses as its source of truth.

## Input

Load `docs/audit/arch-profile.md` if present — use its **Inferred Structural Rules** as the validation criteria. If absent, detect the architecture inline using the same signals as `arch-detector`, then proceed with the audit.

## Violation Catalogue

| Concern | Violations hunted |
|---------|------------------|
| **Dependency direction** | Inner layer importing outer layer; domain importing infrastructure; application importing infrastructure directly instead of through ports |
| **DDD** | Anemic domain model (entities with no behavior, only getters/setters); domain objects with infrastructure imports; application services containing domain logic; value objects with mutable state; aggregates with public setters that bypass invariants; domain services depending on infrastructure |
| **Hexagonal** | Business logic inside adapters; adapters calling each other directly (bypassing ports); ports defined in infrastructure instead of application layer; port interfaces that mimic tool API instead of fitting domain needs |
| **CQRS** | Commands returning domain data; queries with side effects; command and query handlers mixed in the same class; read model routed through domain instead of direct projection |
| **Event Sourcing** | Direct state mutation instead of event emission; event handlers containing business logic; missing projections for read models |
| **Explicit Architecture** | Components importing directly from other components (bypassing Shared Kernel or events); Shared Kernel containing domain-specific logic (must stay minimal); Application Events not used for cross-component integration |
| **General** | Circular dependencies between layers or components; concrete classes used where interfaces are required by the architecture; missing abstraction at a documented boundary |

## Severity Model

| Severity | Meaning |
|----------|---------|
| Critical | Direct dependency rule violation — inner layer imports outer layer |
| High | Business logic in wrong layer; missing required abstraction |
| Medium | Pattern inconsistency; weak boundary enforcement |
| Low | Naming inconsistency with detected patterns; missing domain event where expected |

## Single-Shot Behavior

```
1. Load docs/audit/arch-profile.md if present; detect inline if not
2. Create docs/audit/ if it does not exist
3. If docs/audit/arch-findings.md exists:
     Re-validate each OPEN finding:
     - Issue resolved → move to Fixed (record date)
     - Finding was wrong → move to Invalid (record reason)
     - Still present → leave as Open
4. Audit codebase against structural rules
5. Add new findings (assign next available ID — never reuse IDs)
6. Present findings summary
7. Ask: "Apply fixes now? (y/n)"
   If yes: apply minimal fixes, re-validate, update findings file
8. Write docs/audit/arch-findings.md
9. Ask: "Commit findings to git? (y/n)" — never commit silently
```

## Findings Format

```
# Architecture Audit Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N

## Open Findings

### Critical

#### [ID] Short title
Category: <dependency-direction|ddd|hexagonal|cqrs|event-sourcing|explicit-architecture|general>
Rule: <the structural rule violated, quoted from arch-profile.md if present>
Evidence: <exact file path and the import/pattern that proves the violation>
Fix: <minimal concrete change — move file, invert dependency, extract interface>

### High
[same structure]

### Medium
[same structure]

### Low
[same structure]

## Fixed

### Pass N — YYYY-MM-DD

#### [ID] Short title
Fixed: YYYY-MM-DD
Notes: <what changed>

## Invalid

### Pass N — YYYY-MM-DD

#### [ID] Short title
Notes: <why this finding was wrong>
```

## Rules

- No benefit of the doubt — if a violation exists, file it
- Every finding must include the exact file path and the import/pattern proving the violation
- No hedging — remove "might", "could", "potential"
- Silence = approval — if something is not flagged, that IS your approval
- Apply only minimal fixes — do not redesign systems or extract new abstractions beyond what the fix requires
- **Wrong section structure:** All fixed findings go under one `## Fixed` h2; all invalid findings go under one `## Invalid` h2. Sub-divide each by `### Pass N — YYYY-MM-DD` h3 headers. Never create `## Fixed — pass N` h2 variants. Never skip header levels (h2 → h4 with no h3 is a structural gap).
