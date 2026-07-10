# /nitpicker arch-profile — Architecture Detection

Profiles a codebase to identify which architectural patterns are in use, documents structural evidence for each, detects canonical combinations, and infers the compound structural rules that apply. Hostile — every pattern claim must be backed by concrete structural evidence. Writes a profile, not findings: the output is `docs/audit/arch-profile.md`.

## When to use

- Before running `/nitpicker arch` to provide it with a profile
- When you need to understand the intended architecture of an unfamiliar codebase
- When `docs/audit/arch-profile.md` is missing or stale
- When asked "what architecture is this?", "detect the architecture", "profile this codebase", or "what pattern does this follow?"

If the profile already exists and you only want violations, run `/nitpicker arch` directly — it detects inline when no profile is present.

## Individual patterns detected

| Pattern                      | Key signals                                                                                                              |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| DDD                          | `domain/`, `bounded-contexts/`, `*Entity`, `*ValueObject`, `*Aggregate`, `*Repository`, `*DomainService`, `*DomainEvent` |
| Hexagonal / Ports & Adapters | `ports/`, `adapters/`, `*Port`, `*Adapter`, driving/driven separation                                                    |
| Clean Architecture           | `entities/`, `use-cases/`, `interface-adapters/`, `frameworks/`; strict inward dependency rule                           |
| Onion Architecture           | Concentric naming: `core/`, `domain/`, `application/`, `infrastructure/`; no outward dependencies from inner rings       |
| Layered / N-Tier             | `presentation/`, `business/` or `service/`, `data/` or `persistence/`; top-to-bottom dependency                          |
| CQRS                         | `commands/`, `queries/`, `handlers/`, separate read/write models                                                         |
| Event Sourcing               | Event store, `events/` as source of truth, projections, `*EventStore`, `*Projection`                                     |
| Event-Driven                 | `events/`, `subscribers/`, `publishers/`, event bus, `*EventHandler`                                                     |
| Saga / Process Manager       | `sagas/`, `process-managers/`, choreography or orchestration patterns                                                    |
| MVC                          | `models/`, `views/`, `controllers/`                                                                                      |
| MVVM                         | `models/`, `views/`, `viewmodels/` or `*ViewModel`                                                                       |
| MVP                          | `models/`, `views/`, `presenters/` or `*Presenter`                                                                       |
| Vertical Slice               | `features/` with each slice containing all layers internally                                                             |
| Modular Monolith             | Top-level modules each self-contained with internal layering                                                             |
| Microservices                | Multiple independent service roots each with own domain and persistence                                                  |
| Microkernel                  | Core + plugin registry, `core/` + `plugins/`                                                                             |
| Repository Pattern           | `repositories/`, data access abstraction over persistence                                                                |
| Pipe and Filter              | `pipeline/`, `filters/`, `processors/`, chained transformation stages                                                    |
| Plugin / Extension           | `plugins/`, `extensions/`, core + registered extension points                                                            |
| SOA                          | `services/` as primary organizational unit, service contracts                                                            |

## Combination detection

Combinations are not additive — they produce compound structural rules that differ from any single pattern applied alone.

| Combination                                                    | Additional signals                                                                                     | Compound rules inferred                                                                                                     |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| DDD + Hexagonal                                                | Ports in application layer, adapters in infrastructure                                                 | Domain must not know about ports; ports must fit domain needs, not tool APIs                                                |
| DDD + CQRS                                                     | Separate command/query handlers, read models alongside domain                                          | Commands mutate via domain; queries bypass domain to read models directly                                                   |
| DDD + Event Sourcing                                           | Event store, projections, domain events as persistence                                                 | Aggregates emit events as source of truth; no direct state mutation                                                         |
| Hexagonal + CQRS                                               | Command/query bus as primary driving adapter                                                           | Bus dispatches to handlers; handlers use ports to reach infrastructure                                                      |
| Explicit Architecture (DDD + Hexagonal + Onion + Clean + CQRS) | All of the above; Shared Kernel for cross-component events; screaming architecture component structure | All dependency rules apply simultaneously; components decouple via events not direct calls; Shared Kernel must stay minimal |
| Microservices + DDD                                            | Multiple service roots each with domain/                                                               | Each service is its own bounded context; cross-service = integration events only                                            |
| Modular Monolith + DDD                                         | Top-level modules each with internal layering                                                          | Modules share Shared Kernel; no direct cross-module domain imports                                                          |
| Clean + CQRS                                                   | Use cases split into commands/queries                                                                  | Query use cases return DTOs; command use cases return void or a result ID                                                   |

## Detection process

1. Scan directory tree for structural signals (directory names, file organization)
2. Scan naming conventions across files (class names, interface names, file name suffixes)
3. Trace import/dependency direction to infer intended boundaries
4. Assign each detected pattern a confidence level:
   - **High** — multiple strong, unambiguous signals
   - **Medium** — some signals, some ambiguity
   - **Low** — weak or inferred signal only
5. Identify which canonical combination(s) the detected patterns form
6. Infer the compound structural rules that apply to the combination
7. Flag contradictions: signals that suggest incompatible patterns coexisting

## Output

Create `docs/audit/` if the directory does not exist. Write to `docs/audit/arch-profile.md`:

```markdown
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
- [Rule inferred from the combination — these are what /nitpicker arch validates against]
- [...]

## Ambiguities & Contradictions
[Conflicting signals; patterns present but combination rules already violated]

## Drift (if re-run)
[What changed since last profile — omit section on first run]
```

## Behavior

- If `docs/audit/arch-profile.md` already exists: re-detect and include a Drift section comparing to the prior profile.
- The profile is stale when the most recent commit touching it predates the branch's oldest commit — check staleness from git metadata, not filesystem mtime.
- If no catalogued pattern matches with ≥ Medium confidence, write the profile with `Detected: none` and `Inferred Structural Rules: none` and flag it `Confidence: none — manual review required`. Do not invent rules.
- After writing: ask "Commit the profile to git? (y/n)" — never commit silently.
