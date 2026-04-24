# Hostile Audit Skills — Design Spec
Date: 2026-04-24

## Context

The repository already contains three hostile audit skills: `adversarial-reviewer` (ad-hoc bug hunt), `nitpicker` (exhaustive audit → `docs/audit/arch-findings.md`), and `nitfixer` (applies nitpicker findings). This spec adds three new skills that extend hostile auditing into architecture and documentation domains.

Goals:
- Hostile posture: assume the repository is wrong until proven otherwise
- Actionable evidence: every finding includes a concrete proof and a minimal fix
- Auto-fix capable: skills ask before applying fixes, then implement them
- Technology-agnostic: no tool invocations, reasoning-based only
- Architecture-aware: detect and validate against known architectural patterns and their combinations

---

## Shared Conventions

### Output directory

All output goes to `docs/audit/`. Created automatically if missing.

### Output files

| Skill | Output file |
|-------|-------------|
| `arch-detector` | `docs/audit/arch-profile.md` |
| `arch-auditor` | `docs/audit/arch-findings.md` |
| `doc-auditor` | `docs/audit/doc-findings.md` |

### Findings file format

Used by `arch-auditor` and `doc-auditor`:

```
# [Skill] Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N

## Open Findings

### Critical

#### [ID] Short title
Category: <category>
Rule: <the structural rule violated, sourced from arch-profile if present>
Evidence: <concrete proof — file path, line, or pattern>
Fix: <minimal concrete change>

### High
...

### Medium
...

### Low
...

## Fixed

#### [ID] Short title
Fixed: YYYY-MM-DD
Notes: <what changed>

## Invalid

#### [ID] Short title
Notes: <why this finding was wrong>
```

### Re-validation behavior

If a findings file already exists, validate each `Open` finding before adding new ones:
- Issue resolved → move to `Fixed`
- Finding was wrong → move to `Invalid`
- Still present → leave as `Open`

New findings get the next available ID. IDs are never reused.

### Commit behavior

After writing or updating any file in `docs/audit/`, always ask:
> *"Commit findings to git? (y/n)"*

Never commit silently.

### Fix behavior

After presenting findings, always ask:
> *"Apply fixes now? (y/n)"*

If yes: apply fixes, re-validate, update findings file. Then ask about commit.

---

## Skill 1: `arch-detector`

### Purpose

Profile the codebase to identify which architecture(s) are in use, document the structural evidence for each, detect canonical combinations, and infer the compound structural rules that apply. Useful standalone and as input to `arch-auditor`.

### Individual patterns detected

| Pattern | Key signals |
|---------|-------------|
| DDD | `domain/`, `bounded-contexts/`, `*Entity`, `*ValueObject`, `*Aggregate`, `*Repository`, `*DomainService`, `*DomainEvent` |
| Hexagonal / Ports & Adapters | `ports/`, `adapters/`, `*Port`, `*Adapter`, driving/driven separation |
| Clean Architecture | `entities/`, `use-cases/`, `interface-adapters/`, `frameworks/`; strict inward dependency rule |
| Onion Architecture | Concentric naming: `core/`, `domain/`, `application/`, `infrastructure/`; no outward dependencies from inner rings |
| Layered / N-Tier | `presentation/`, `business/` or `service/`, `data/` or `persistence/`; top-to-bottom dependency |
| CQRS | `commands/`, `queries/`, `handlers/`, separate read/write models |
| Event Sourcing | Event store, `events/` as source of truth, projections, `*EventStore`, `*Projection` |
| Event-Driven | `events/`, `subscribers/`, `publishers/`, event bus, `*EventHandler` |
| Saga / Process Manager | `sagas/`, `process-managers/`, choreography or orchestration patterns |
| MVC | `models/`, `views/`, `controllers/` |
| MVVM | `models/`, `views/`, `viewmodels/` or `*ViewModel` |
| MVP | `models/`, `views/`, `presenters/` or `*Presenter` |
| Vertical Slice | `features/` with each slice containing all layers internally |
| Modular Monolith | Top-level modules each self-contained with internal layering |
| Microservices | Multiple independent service roots each with own domain and persistence |
| Repository Pattern | `repositories/`, data access abstraction over persistence |
| Pipe and Filter | `pipeline/`, `filters/`, `processors/`, chained transformation stages |
| Plugin / Extension | `plugins/`, `extensions/`, core + registered extension points |
| SOA | `services/` as primary organizational unit, service contracts |

### Combination detection

Combinations are not additive — they produce specific compound structural rules that differ from individual patterns applied independently.

| Combination | Additional signals | Compound rules inferred |
|---|---|---|
| DDD + Hexagonal | Ports in application layer, adapters in infrastructure | Domain must not know about ports; ports must fit domain needs, not tool APIs |
| DDD + CQRS | Separate command/query handlers, read models alongside domain | Commands mutate via domain; queries bypass domain to read models directly |
| DDD + Event Sourcing | Event store, projections, domain events as persistence | Aggregates emit events as source of truth; no direct state mutation |
| Hexagonal + CQRS | Command/query bus as primary driving adapter | Bus dispatches to handlers; handlers use ports to reach infrastructure |
| Explicit Architecture (DDD + Hexagonal + Onion + Clean + CQRS) | All of the above; Shared Kernel for cross-component events; screaming architecture component structure | All dependency rules apply simultaneously; components decouple via events not direct calls; Shared Kernel must stay minimal |
| Microservices + DDD | Multiple service roots each with domain/ | Each service is its own bounded context; cross-service = integration events only |
| Modular Monolith + DDD | Top-level modules each with internal layering | Modules share Shared Kernel; no direct cross-module domain imports |
| Clean + CQRS | Use cases split into commands/queries | Query use cases return DTOs; command use cases return void or a result ID |

### Detection process

1. Scan directory tree for structural signals
2. Scan naming conventions across files
3. Trace import/dependency direction to infer intended boundaries
4. Assign each detected pattern a confidence level: **High** (multiple strong signals), **Medium** (some signals, some ambiguity), **Low** (weak or inferred)
5. Identify canonical combination(s) formed by detected patterns
6. Infer compound structural rules for the combination
7. Flag contradictions: signals that suggest incompatible patterns

### Output: `docs/audit/arch-profile.md`

```
# Architecture Profile
Generated: YYYY-MM-DD

## Detected Patterns

### [Pattern Name] — [High|Medium|Low] confidence
Evidence:
- [specific directory, file, or naming signal]
- [dependency direction observation]

## Detected Combination
[Canonical combination name, or "Custom hybrid: DDD + Event-Driven"]

## Inferred Structural Rules
- Dependencies must point inward toward Domain
- Ports must live in Application layer, not Domain
- Commands must not return domain data
- Components must not import directly from other components
- [...]

## Ambiguities & Contradictions
[Conflicting signals; patterns present but their combination rules are violated]

## Drift (if re-run)
[What changed since last profile]
```

### Behavior

- If `docs/audit/arch-profile.md` already exists: re-detect and report drift from the prior profile
- Ask before committing

---

## Skill 2: `arch-auditor`

### Purpose

Audit the codebase for violations of the detected (or declared) architecture. Hostile — assumes violations exist and hunts for proof. Uses `docs/audit/arch-profile.md` if present; detects inline if not.

### Violation catalogue

| Concern | Violations hunted |
|---------|------------------|
| Dependency direction | Inner layer importing outer layer; domain importing infrastructure; application importing infrastructure directly instead of through ports |
| DDD | Anemic domain model (entities with no behavior); domain objects with infrastructure imports; application services containing domain logic; value objects with mutable state; aggregates with public setters (invariants unprotected); domain services depending on infrastructure |
| Hexagonal | Business logic inside adapters; adapters calling each other directly; ports defined in infrastructure instead of application layer; port interfaces that mimic tool API instead of fitting domain needs |
| CQRS | Commands returning domain data; queries with side effects; command and query handlers mixed in the same class; read model routed through domain instead of direct projection |
| Event Sourcing | Direct state mutation instead of event emission; event handlers containing business logic; missing projections for read models |
| Explicit Architecture | Components importing directly from other components (bypassing Shared Kernel or events); Shared Kernel containing domain-specific logic; Application Events not used for cross-component integration |
| General | Circular dependencies between layers or components; concrete classes used where interfaces are required; missing abstraction at a documented boundary |

### Severity model

| Severity | Meaning |
|----------|---------|
| Critical | Direct dependency rule violation — inner layer imports outer layer |
| High | Business logic in wrong layer; missing required abstraction |
| Medium | Pattern inconsistency; weak boundary enforcement |
| Low | Naming inconsistency with detected patterns; missing domain event where expected |

### Single-shot behavior

```
1. Load docs/audit/arch-profile.md if present; detect inline if not
2. If docs/audit/arch-findings.md exists:
     Re-validate each OPEN finding — mark FIXED or INVALID as appropriate
3. Audit codebase against structural rules
4. Add new findings (never reuse IDs)
5. Present findings summary
6. Ask: "Apply fixes now? (y/n)"
   - If yes: apply minimal fixes, update findings file
7. Write docs/audit/arch-findings.md
8. Ask: "Commit findings to git? (y/n)"
```

Each finding includes the violated rule (sourced from arch-profile if present), exact file path and import/pattern proving the violation, and a minimal concrete fix.

---

## Skill 3: `doc-auditor`

### Purpose

Hostile documentation review. Assumes every claim in every doc is wrong until verified against the codebase. Two-directional: docs→code (does code match the claim?) and code→docs (is this code undocumented?).

### Documentation scanned

- `README.md` at any directory level
- `docs/` directories (excluding `docs/audit/`)
- Inline comments and docstrings
- Architecture Decision Records (ADRs)
- Changelogs
- OpenAPI / Swagger / AsyncAPI specs
- Configuration file comments
- Test names and descriptions (they document expected behavior)

### Finding types

| Type | Description |
|------|-------------|
| Stale | References a function, class, module, file, or parameter that no longer exists or has been renamed |
| Incorrect | Documented behavior contradicts implementation — wrong parameters, wrong return type, wrong description |
| Missing | Public API, exported function, architectural boundary, or module with no documentation |
| Outdated architecture | Describes a structural pattern, layer, or component that has changed or been removed |
| Contradiction | Two documentation sources make conflicting claims about the same thing |
| Broken link | Internal link to a file, heading, or section that does not resolve |

### Severity model

| Severity | Meaning |
|----------|---------|
| Critical | Actively misleads — incorrect behavior description that would cause wrong usage |
| High | Missing documentation for a public API or architectural boundary |
| Medium | Stale reference, outdated architecture description, contradiction |
| Low | Broken internal link, minor inaccuracy, test name that misrepresents behavior |

### Fix types

| Fix | Applied automatically (after asking) |
|-----|--------------------------------------|
| Remove stale references | Yes |
| Update renamed identifiers | Yes |
| Fix broken internal links | Yes |
| Generate missing docs from code | Yes — inferred from signatures, types, and context |
| Update incorrect behavior descriptions | Yes — rewritten from actual implementation |
| Update architecture descriptions | Yes — rewritten from `docs/audit/arch-profile.md` if present |
| Resolve contradictions | Yes — picks the version consistent with code; flags for review |

### Single-shot behavior

```
1. Collect all documentation sources
2. If docs/audit/doc-findings.md exists:
     Re-validate each OPEN finding — mark FIXED or INVALID as appropriate
3. Audit all docs against codebase (both directions)
4. Add new findings (never reuse IDs)
5. Present findings summary
6. Ask: "Apply fixes now? (y/n)"
   - If yes: apply fixes, update findings file
7. Write docs/audit/doc-findings.md
8. Ask: "Commit findings to git? (y/n)"
```

---

## Implementation Order

1. `arch-detector` — foundational; its output improves the other two
2. `arch-auditor` — depends on detector's output (or detects inline)
3. `doc-auditor` — independent; can use arch-profile for architecture descriptions
