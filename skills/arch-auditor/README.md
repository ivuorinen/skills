# arch-auditor

Audits a codebase for architectural violations against detected or declared patterns. Writes a structured findings report.

## When to Use

- After [arch-detector] has produced `docs/audit/arch-profile.md`
- When `docs/audit/arch-profile.md` already exists and you only want violation findings
- "Audit the architecture" / "find architecture violations" / "check layer boundaries"
- "Are there any DDD violations?" / "check hexagonal boundaries"

**When NOT to use:**
- When you do not yet know the architecture → run [arch-detector] first (or let arch-auditor detect inline, which produces weaker output)
- For full repository audit (tests, docs, config) → use [nitpicker] in architecture mode

## What It Reads / Writes

| | |
|---|---|
| **Reads** | `docs/audit/arch-profile.md` (optional but recommended), codebase |
| **Writes** | `docs/audit/arch-findings.md` |

## How to Invoke

```
/arch-auditor
```

Run [arch-detector] first for best results. arch-auditor can detect inline when no profile is present, but the profile gives it explicit structural rules to enforce.

## Violation Catalogue

| Concern | Violations hunted |
|---------|------------------|
| **Dependency direction** | Inner layer importing outer layer; domain importing infrastructure; application importing infrastructure directly instead of through ports |
| **DDD** | Anemic domain model (entities with no behavior, only getters/setters); business logic in application or infrastructure layer; repositories called directly from UI or API controllers |
| **Hexagonal** | Domain code depending on a specific framework or database driver; adapter directly calling another adapter; port interface not defined in the domain layer |
| **Clean Architecture** | Use case importing a concrete infrastructure class; entity depending on a use case |
| **CQRS** | Command handler reading state it does not own; query handler mutating state |
| **Event Sourcing** | Projection mutating the event store; business logic reconstructed outside the aggregate |
| **Microservices** | Direct database coupling across service boundaries; synchronous calls where events are required |
| **Vertical Slice** | Cross-slice import (feature A importing feature B internals) |
| **Layered** | Skipped layer (UI calling data access directly); circular layer dependency |
| **Cross-cutting** | Logging, metrics, or auth logic duplicated across layers instead of handled by middleware or decorators |
| **Naming** | Classes, files, or directories that contradict the detected pattern (e.g., `*Service` in a DDD domain layer without a domain-service role) |

## Severity Model

| Severity | Meaning |
|----------|---------|
| Critical | Direct dependency rule violation — inner layer imports outer layer |
| High | Business logic in wrong layer; missing required abstraction |
| Medium | Pattern inconsistency; weak boundary enforcement |
| Low | Naming inconsistency with detected patterns; missing domain event where expected |

## Single-Shot Behavior

```
1. Read docs/audit/arch-profile.md if present; detect patterns inline otherwise
2. If docs/audit/arch-findings.md exists: re-validate each OPEN finding
     - Resolved → move to Fixed (record date)
     - Was wrong → move to Invalid (record reason)
     - Still present → leave Open
3. Add new findings (assign next available ID — never reuse IDs)
4. Write docs/audit/arch-findings.md
5. Present summary; ask "Commit findings to git? (y/n)"
```

## Findings Format

```
# Architecture Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD
Pattern(s): <detected patterns>

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N

## Open Findings

### Critical

#### [ARCH-NNN] Short title
Concern: <dependency-direction|DDD|hexagonal|…>
Area: path/to/file.ts:42
Violation: <what rule is broken>
Evidence: <import or code excerpt>
Impact: <why this matters>
Fix: <concrete remediation>
```

Finding ID format: `ARCH-NNN` (zero-padded to 3 digits).

## Related Skills

- [arch-detector] — produces `docs/audit/arch-profile.md` consumed by this skill
- [nitpicker] — architecture mode invokes arch-detector then arch-auditor
- [doc-auditor] — reads `docs/audit/arch-profile.md` for architecture documentation accuracy
- [claude-rules-auditor] — reads `docs/audit/arch-findings.md` as input

---

[skill-source]: SKILL.md
[arch-detector]: ../arch-detector/README.md
[nitpicker]: ../nitpicker/README.md
[doc-auditor]: ../doc-auditor/README.md
[claude-rules-auditor]: ../claude-rules-auditor/README.md
