# /nitpicker docs — Documentation Audit

Hostile documentation review: assumes every claim in every doc is wrong until verified against the codebase. Two-directional — docs→code (does code match the claim?) and code→docs (is this code undocumented?).

## When to use

- When documentation may have drifted from the codebase, or after a significant refactor
- Before a release to verify docs accuracy
- When onboarding reveals confusion about what's documented vs. what's real
- When asked to "audit the docs", "find stale documentation", "verify docs against code", "is the documentation accurate?", or "find missing docs"

For architecture-specific documentation drift, run `/nitpicker arch` instead — it validates structural claims against the detected architecture. Read `docs/audit/arch-profile.md` if present; it improves architecture-description accuracy checks (run `/nitpicker arch-profile` first when architecture docs need checking and no profile exists).

## Documentation scanned

- `README.md` at any directory level
- `docs/` directories (excluding `docs/audit/` — this skill's own output)
- `CONTRIBUTING.md`, changelogs, and similar project-level docs
- Inline comments and docstrings
- Example code blocks inside documentation
- Architecture Decision Records (ADRs)
- OpenAPI / Swagger / AsyncAPI specs
- Configuration file comments
- Test names and descriptions (they document expected behavior)
- Cross-references between documents (links, `See also:` sections)

## Finding types

| Type | Description |
| --- | --- |
| Stale | References a function, class, module, file, or parameter that no longer exists or has been renamed |
| Incorrect | Documented behavior contradicts implementation — wrong parameters, wrong return type, wrong description of what the code does |
| Missing | Public API, exported function, architectural boundary, or module with no documentation |
| Outdated architecture | Describes a structural pattern, layer, or component that has changed or been removed |
| Contradiction | Two documentation sources make conflicting claims about the same thing |
| Broken link | Internal link to a file, heading, or section that does not resolve |

## Severity guide

| Severity | Meaning |
| --- | --- |
| Critical | Actively misleads — incorrect behavior description that would cause wrong usage of the code |
| High | Missing documentation for a public API or architectural boundary |
| Medium | Stale reference, outdated architecture description, contradiction |
| Low | Broken internal link, minor inaccuracy, test name that misrepresents behavior |
| Advisory | Informational note about the docs; no action required |

## Process

1. Re-validate open findings per `_conventions.md`.
2. Collect all documentation sources (see Documentation scanned above); read `docs/audit/arch-profile.md` if present.
3. Audit all docs against the codebase in both directions.
4. File findings via the store protocol in `_conventions.md`, using `--auditor docs` and `--category docs`. Fold the domain fields into the finding body: Problem names the finding type and quotes the exact claim being challenged; Evidence states what the code actually does — file path and relevant detail; Impact states why the inaccuracy matters; Fix is the minimal correction. The finding's area is the document containing the claim.
5. Present the summary and offer fixes per `_conventions.md`.

## Fix types

All are applied only after the `_conventions.md` apply-fixes prompt:

| Fix | How |
| --- | --- |
| Remove stale references | Delete the dead reference |
| Update renamed identifiers | Rename to the current identifier |
| Fix broken internal links | Repoint to the resolving target |
| Generate missing docs from code | Inferred from signatures, types, and context |
| Update incorrect behavior descriptions | Rewritten from the actual implementation |
| Update architecture descriptions | Rewritten from `docs/audit/arch-profile.md` if present |
| Resolve contradictions | Pick the version consistent with code; note the resolution |

## Rules

- No benefit of the doubt — every doc claim is a suspect until verified.
- Every finding includes the source document path and the exact claim being challenged.
- Apply only minimal fixes — correct the claim, do not rewrite the document.
- Do not flag style or tone — only factual accuracy and completeness.
