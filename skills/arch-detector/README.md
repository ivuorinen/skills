# arch-detector

Detects which architectural patterns a codebase uses and produces `docs/audit/arch-profile.md` with inferred structural rules.

## When to Use

- Before running [arch-auditor] to give it an explicit profile to enforce
- When `docs/audit/arch-profile.md` is missing or stale
- "What architecture is this?" / "detect the architecture" / "profile this codebase"
- "What pattern does this follow?" / "run arch-detector"

**When NOT to use:**
- When `docs/audit/arch-profile.md` already exists and you only want violations → run [arch-auditor] directly (it detects inline but produces weaker findings without the profile)

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Repository directory tree, file naming, import patterns, configuration files |
| **Writes** | `docs/audit/arch-profile.md` |

## How to Invoke

```
/arch-detector
```

No arguments required. Scans the entire repository.

## Individual Patterns Detected

| Pattern | Key signals |
|---------|-------------|
| DDD | `domain/`, `bounded-contexts/`, `*Entity`, `*ValueObject`, `*Aggregate`, `*Repository`, `*DomainService`, `*DomainEvent` |
| Hexagonal / Ports & Adapters | `ports/`, `adapters/`, `*Port`, `*Adapter`, driving/driven separation |
| Clean Architecture | `entities/`, `use-cases/`, `interface-adapters/`, `frameworks/` |
| CQRS | Separate command/query models, `commands/`, `queries/`, `*Command`, `*Query` |
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
| SOA | `services/` as primary organizational unit |
| Layered / N-Tier | Distinct `presentation/`, `business/`, `data/` or `dal/` layers |
| Microkernel | Core + plugin registry, `core/` + `plugins/` |

## Canonical Combinations

Some patterns co-occur predictably:

| Combination | Typical pairing |
|-------------|----------------|
| DDD + Hexagonal | Domain-driven design with ports & adapters boundary enforcement |
| DDD + CQRS | Aggregates on command side; projections / read models on query side |
| DDD + Event Sourcing | Aggregates emit domain events stored as source of truth |
| DDD + CQRS + Event Sourcing | Full event-driven DDD stack |
| Clean Architecture + Repository | Use cases depend on repository interfaces, not concrete implementations |
| Microservices + Event-Driven | Services communicate via events, not direct calls |
| Modular Monolith + Vertical Slice | Top-level modules each structured as vertical slices |
| MVC + Repository | Classic web app with data access abstraction |

## Detection Process

```
1. Walk the directory tree; collect all path segments and file names
2. Score each pattern by matching signals (high / medium / low confidence)
3. Identify canonical combinations present
4. Infer structural rules (which directories may import which)
5. Write docs/audit/arch-profile.md
6. Present summary of detected patterns and confidence levels
```

## Output: arch-profile.md

```markdown
# Architecture Profile
Generated: YYYY-MM-DD

## Detected Patterns
- DDD (High confidence)
- Hexagonal / Ports & Adapters (High confidence)

## Inferred Structural Rules
- `domain/` must not import from `adapters/` or `infrastructure/`
- `application/` must not import from `adapters/` directly
- `ports/` interfaces must be defined inside `domain/`
...

## Evidence
[key files and directories that drove each conclusion]
```

If no catalogued pattern matches with Medium or higher confidence, the profile is written with `Detected: none` and `Confidence: none — manual review required`.

## Staleness

`docs/audit/arch-profile.md` is considered stale when the most recent commit touching it predates the branch's oldest commit. [arch-auditor] and [nitpicker] (architecture mode) check staleness from Git metadata, not filesystem mtime.

## Related Skills

- [arch-auditor] — reads the profile this skill produces; run after arch-detector
- [nitpicker] — architecture mode invokes arch-detector if the profile is missing or stale
- [doc-auditor] — reads `docs/audit/arch-profile.md` for architecture documentation accuracy

---

[skill-source]: SKILL.md
[arch-auditor]: ../arch-auditor/README.md
[nitpicker]: ../nitpicker/README.md
[doc-auditor]: ../doc-auditor/README.md
