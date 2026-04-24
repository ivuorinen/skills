# Hostile Audit Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create three new hostile audit skills — `arch-detector`, `arch-auditor`, and `doc-auditor` — following the design spec at `docs/superpowers/specs/2026-04-24-hostile-audit-skills-design.md`.

**Architecture:** Each skill is a standalone `SKILL.md` file with YAML frontmatter. Skills are self-contained prompt documents — no build system, no dependencies. All three share a common findings file format and write output to `docs/audit/`.

**Tech Stack:** Markdown, YAML frontmatter. No code compilation or test runner.

---

## Validation Checklist (run after each skill is written)

Before marking a task complete, verify all items:

- [ ] Frontmatter has `name` and `description` fields
- [ ] `description` starts with "Use when..."
- [ ] `description` is under 500 characters
- [ ] `description` does not summarize the skill's workflow
- [ ] `description` is written in third person
- [ ] All behaviors from the spec section are covered in the skill body
- [ ] Output path is `docs/audit/` (created if missing)
- [ ] Commit behavior: always ask, never silent
- [ ] Fix behavior: always ask, never silent
- [ ] Re-validation behavior is described (validate existing findings on re-run)
- [ ] No placeholder text (TBD, TODO, "implement later", etc.)
- [ ] Findings format matches the shared conventions spec (grouped by severity, Fixed section at bottom)

---

## Task 1: `arch-detector/SKILL.md`

**Files:**
- Create: `arch-detector/SKILL.md`

- [ ] **Step 1: Verify the file does not exist yet**

```bash
ls arch-detector/
```

Expected: directory is empty (no SKILL.md).

- [ ] **Step 2: Write `arch-detector/SKILL.md`**

Write the following content exactly:

```markdown
---
name: arch-detector
description: Use when you need to identify which architectural patterns a codebase uses, understand its structural boundaries, or generate an architecture profile before auditing. Triggers: "what architecture is this?", "detect the architecture", "profile this codebase", "what pattern does this follow?", "run arch-detector".
---

# Architecture Detector

## Overview

Profiles a codebase to identify which architectural patterns are in use, documents structural evidence for each, detects canonical combinations, and infers the compound structural rules that apply. Hostile — every pattern claim must be backed by concrete structural evidence.

## When to Use

- Before running `arch-auditor` to provide it with a profile
- When you need to understand the intended architecture of an unfamiliar codebase
- When `docs/audit/arch-profile.md` is missing or stale

**When NOT to use:** If `docs/audit/arch-profile.md` already exists and you only want to find violations, run `arch-auditor` directly — it detects inline when no profile is present.

## Individual Patterns Detected

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

## Combination Detection

Combinations are not additive — they produce compound structural rules that differ from any single pattern applied alone.

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

## Detection Process

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
- [Rule inferred from the combination — these are what arch-auditor validates against]
- [...]

## Ambiguities & Contradictions
[Conflicting signals; patterns present but combination rules already violated]

## Drift (if re-run)
[What changed since last profile — omit section on first run]
```

## Behavior

- If `docs/audit/arch-profile.md` already exists: re-detect and include a Drift section comparing to the prior profile
- After writing: ask *"Commit findings to git? (y/n)"* — never commit silently
```

- [ ] **Step 3: Run the validation checklist**

Check every item in the Validation Checklist at the top of this plan. Fix any failures before proceeding.

- [ ] **Step 4: Commit**

```bash
git add arch-detector/SKILL.md
git commit -m "feat: add arch-detector skill"
```

---

## Task 2: `arch-auditor/SKILL.md`

**Files:**
- Create: `arch-auditor/SKILL.md`

- [ ] **Step 1: Verify the file does not exist yet**

```bash
ls arch-auditor/
```

Expected: directory is empty (no SKILL.md).

- [ ] **Step 2: Write `arch-auditor/SKILL.md`**

Write the following content exactly:

```markdown
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

#### [ID] Short title
Fixed: YYYY-MM-DD
Notes: <what changed>

## Invalid

#### [ID] Short title
Notes: <why this finding was wrong>
```

## Rules

- No benefit of the doubt — if a violation exists, file it
- Every finding must include the exact file path and the import/pattern proving the violation
- No hedging — remove "might", "could", "potential"
- Silence = approval — if something is not flagged, that IS your approval
- Apply only minimal fixes — do not redesign systems or extract new abstractions beyond what the fix requires
```

- [ ] **Step 3: Run the validation checklist**

Check every item in the Validation Checklist at the top of this plan. Fix any failures before proceeding.

- [ ] **Step 4: Commit**

```bash
git add arch-auditor/SKILL.md
git commit -m "feat: add arch-auditor skill"
```

---

## Task 3: `doc-auditor/SKILL.md`

**Files:**
- Create: `doc-auditor/SKILL.md`

- [ ] **Step 1: Verify the file does not exist yet**

```bash
ls doc-auditor/
```

Expected: directory is empty (no SKILL.md).

- [ ] **Step 2: Write `doc-auditor/SKILL.md`**

Write the following content exactly:

```markdown
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
```

- [ ] **Step 3: Run the validation checklist**

Check every item in the Validation Checklist at the top of this plan. Fix any failures before proceeding.

- [ ] **Step 4: Commit**

```bash
git add doc-auditor/SKILL.md
git commit -m "feat: add doc-auditor skill"
```

---

## Task 4: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add three rows to the Existing Skills table**

Find the Existing Skills table in `CLAUDE.md`:

```markdown
| Skill | Trigger description |
|-------|---------------------|
| `adversarial-reviewer` | Hostile code review; assumes bugs exist and hunts for them |
| `nitpicker` | Comprehensive repository audit before release or for exhaustive PR review |
| `nitfixer` | Applies fixes from `./codereview.md` produced by Nitpicker |
```

Replace with:

```markdown
| Skill | Trigger description |
|-------|---------------------|
| `adversarial-reviewer` | Hostile code review; assumes bugs exist and hunts for them |
| `nitpicker` | Comprehensive repository audit before release or for exhaustive PR review |
| `nitfixer` | Applies fixes from `./codereview.md` produced by Nitpicker |
| `arch-detector` | Detects which architectural patterns a codebase uses; produces `docs/audit/arch-profile.md` |
| `arch-auditor` | Audits codebase for architectural violations against detected or declared patterns |
| `doc-auditor` | Verifies all documentation accuracy against the codebase; finds stale, incorrect, and missing docs |
```

- [ ] **Step 2: Verify the table renders correctly**

Read `CLAUDE.md` and confirm the table has 6 data rows and no formatting errors.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: register arch-detector, arch-auditor, doc-auditor in CLAUDE.md"
```

---

## Self-Review

### Spec coverage

| Spec requirement | Task |
|-----------------|------|
| Shared output dir `docs/audit/`, created if missing | Tasks 1–3 (each skill creates dir if missing) |
| `arch-profile.md` format with Detected Patterns, Combination, Rules, Ambiguities, Drift | Task 1 |
| All 19 individual patterns detected | Task 1 |
| All 8 canonical combinations with compound rules | Task 1 |
| 7-step detection process | Task 1 |
| arch-auditor uses arch-profile if present, detects inline if not | Task 2 |
| Violation catalogue (7 concern areas) | Task 2 |
| Severity model (Critical/High/Medium/Low) for both auditors | Tasks 2–3 |
| Single-shot behavior with re-validation of existing findings | Tasks 2–3 |
| Findings format grouped by severity, Fixed section at bottom | Tasks 2–3 |
| Rule field in arch-findings | Task 2 |
| Source and Claim fields in doc-findings | Task 3 |
| Fix types for doc-auditor (7 types, all auto-applicable after asking) | Task 3 |
| Ask before applying fixes | Tasks 2–3 |
| Ask before committing | Tasks 1–3 |
| CLAUDE.md updated | Task 4 |
