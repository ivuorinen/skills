# /nitpicker arch — Architecture Audit

Hostile architectural audit: assumes violations exist and hunts for proof, validating the codebase against its detected (or declared) architecture.

## When to use

- After `/nitpicker arch-profile` has produced `docs/audit/arch-profile.md` (uses it if present)
- When you suspect architectural drift or layer boundary violations
- When asked to "audit the architecture", "find architecture violations", "check layer boundaries", "are there any DDD violations?", or "check hexagonal boundaries"

If you don't yet know what architecture the project uses, run `/nitpicker arch-profile` first — it produces the profile this command uses as its source of truth.

## Input

Load `docs/audit/arch-profile.md` if present — use its **Inferred Structural Rules** as the validation criteria. If absent, detect the architecture inline using the same signals as `/nitpicker arch-profile`, then proceed with the audit.

## Violation catalogue

| Concern | Violations hunted |
| --- | --- |
| Dependency direction | Inner layer importing outer layer; domain importing infrastructure; application importing infrastructure directly instead of through ports |
| DDD | Anemic domain model (entities with no behavior, only getters/setters); domain objects with infrastructure imports; application services containing domain logic; value objects with mutable state; aggregates with public setters that bypass invariants; domain services depending on infrastructure; repositories called directly from UI or API controllers |
| Hexagonal | Business logic inside adapters; adapters calling each other directly (bypassing ports); ports defined in infrastructure instead of application layer; port interfaces that mimic tool API instead of fitting domain needs |
| Clean Architecture | Use case importing a concrete infrastructure class; entity depending on a use case |
| CQRS | Commands returning domain data; queries with side effects; command and query handlers mixed in the same class; read model routed through domain instead of direct projection |
| Event Sourcing | Direct state mutation instead of event emission; event handlers containing business logic; missing projections for read models; projection mutating the event store |
| Explicit Architecture | Components importing directly from other components (bypassing Shared Kernel or events); Shared Kernel containing domain-specific logic (must stay minimal); Application Events not used for cross-component integration |
| Microservices | Direct database coupling across service boundaries; synchronous calls where events are required |
| Vertical Slice | Cross-slice import (feature A importing feature B internals) |
| Layered | Skipped layer (UI calling data access directly); circular layer dependency |
| Cross-cutting | Logging, metrics, or auth logic duplicated across layers instead of handled by middleware or decorators |
| General | Circular dependencies between layers or components; concrete classes used where interfaces are required by the architecture; missing abstraction at a documented boundary; names that contradict the detected pattern (e.g., `*Service` in a DDD domain layer without a domain-service role) |

## Severity guide

| Severity | Meaning |
| --- | --- |
| Critical | Direct dependency rule violation — inner layer imports outer layer |
| High | Business logic in wrong layer; missing required abstraction |
| Medium | Pattern inconsistency; weak boundary enforcement |
| Low | Naming inconsistency with detected patterns; missing domain event where expected |
| Advisory | Informational structural observation; no action required |

## Process

1. Load `docs/audit/arch-profile.md` if present; detect inline if not.
2. Re-validate open findings per `_conventions.md`.
3. Audit the codebase against the structural rules and the violation catalogue.
4. File findings via the store protocol in `_conventions.md`, using `--auditor arch` and `--category maintainability`. Fold the domain fields into the finding body: Problem names the concern (dependency-direction, ddd, hexagonal, cqrs, event-sourcing, explicit-architecture, general, …) and quotes the structural rule violated — from `arch-profile.md` when present; Evidence is the exact file path and the import/pattern that proves the violation; Impact states the boundary or invariant the violation erodes; Fix is the minimal concrete change — move file, invert dependency, extract interface.
5. Present the summary and offer fixes per `_conventions.md`.

## Rules

- No benefit of the doubt — if a violation exists, file it.
- Every finding includes the exact file path and the import/pattern proving the violation.
- Apply only minimal fixes — do not redesign systems or extract new abstractions beyond what the fix requires.
