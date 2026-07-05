# api-contract-auditor

Hostile audit of a project's *public contract surface*. Assumes the contract has drifted until every declared element — OpenAPI/Swagger paths and shapes, GraphQL schema, package exports and published types, documented CLI flags — is verified against the implementation (axis 1), and every surface change since the last release tag is classified breaking/non-breaking and checked against the semver bump the commits declare (axis 2). Every finding names the declared element (file:line), the implementation (file:line), the mismatch, and the consumer-visible consequence. Fixing drift means deciding which side is right — spec edits and code edits are separate, per-finding user approvals.

## When to Use

- "Does the spec match the code" / "audit the api contract" / "is this change breaking"
- Before a release, to prove no unlabeled breaking change is pending and the last shipped release did not break consumers under a minor/patch bump
- After a refactor that touched route handlers, resolvers, exports, or the CLI parser

**When NOT to use:**
- Prose documentation accuracy (README claims, guides, comments) → use [doc-auditor]
- Whether a commit message's label matches its diff text → use `commit-auditor`
- Architectural boundary violations → use [arch-auditor]

## api-contract-auditor vs. doc-auditor vs. commit-auditor

| | api-contract-auditor | doc-auditor | commit-auditor |
|---|---|---|---|
| Question | "Does the declared contract match the implementation, and does the surface change match the bump?" | "Is what the documentation *says* true of the code?" | "Does the commit label match the commit diff?" |
| Input | Specs, exports, published types, CLI parsers, git diff vs the release baseline | All prose docs, comments, docstrings, changelogs | Commit messages and their diffs |
| Unit | A declared surface element / a surface change | A documented claim | A commit |
| Output | `docs/audit/api-contract-auditor-findings.md` | `docs/audit/doc-findings.md` | its own findings file |

The two semver skills pair: `commit-auditor` checks the label against the diff; this skill checks the *surface* against the label. A breaking surface change riding an honest `fix:` commit is invisible to commit-auditor and a High here.

## What It Reads / Writes

| | |
|---|---|
| **Reads** | OpenAPI/Swagger/AsyncAPI files; GraphQL SDL/code-first schema; `package.json` `exports`/`main`/`types`/`bin`, published `.d.ts`, `__all__`, public headers; CLI `--help`/man text and argument parser definitions; framework route tables; git tags and the diff since the release baseline; commit messages since the baseline |
| **Writes** | `docs/audit/api-contract-auditor-findings.md` |

## How to Invoke

```
/api-contract-auditor
```

Inventories the declared surface from the project's own declarations — the definition of "public" is never guesswork — then verifies both axes in full. A sampled run has verdict INCOMPLETE.

## Finding Classes

| Axis | Classes |
|------|---------|
| declaration-drift | missing-implementation, undeclared-surface, shape-mismatch, status-code-mismatch, auth-mismatch, param-mismatch |
| semver-drift | removed-symbol, renamed-symbol, narrowed-input, widened-output, changed-default, stricter-validation, retyped-field |

## Process

```
0. Re-validate existing findings (re-verify each Open element; resolved → Fixed)
1. Inventory the declared surface — every source, every element, counts recorded; never sample
2. Axis 1: verify every declared element against its implementation, both directions
3. Axis 2: diff the surface against the last release tag (or first commit); classify each
   change breaking/non-breaking and check it against the declared bump
4. File findings — declared element, implementation, mismatch, consumer impact; write the file
5. Ask per finding: "Fix [AC-NNN]? (s)pec (c)ode (n)either" — which side is right is the
   user's call; spec and code edits are separate approvals
6. Ask: "Commit findings to git? (y/n)" — never commit silently
```

## Findings Format

```
# API Contract Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N elements/changes unexamined)
- Surface declared: openapi elements N | graphql fields N | exports N | cli flags N | routes N
- Verified: openapi elements N | graphql fields N | exports N | cli flags N | routes N
- Axis 2 baseline: <tag or first commit> | changes N | breaking N | declared bump: <major|minor|patch|none>

## Open Findings

### Critical

#### [AC-NNN] Short title
Status: Open
Axis: <declaration-drift|semver-drift>
Class: <see Finding Classes>
Declared: <the spec/export/flag element — file:line>
Implementation: <file:line, or "absent">
Mismatch: <what differs>
Consumer impact: <what a consumer built against the declaration sees break>
Semver: <breaking|non-breaking> vs declared bump <major|minor|patch|none> (axis 2 findings only)
Fix: <the spec-side edit AND the code-side edit — the user picks the side>
```

Finding ID format: `AC-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | A shipped release already broke consumers without a major bump — a breaking surface change sits behind a published minor/patch tag |
| High | A pending breaking change is unlabeled, or the spec promises an endpoint, field, type, status code, or auth requirement the implementation does not honor |
| Medium | Implemented-but-undeclared surface; an over-labeled bump; implementation more permissive than the declaration |
| Low | Drift on a deprecated element; naming/metadata mismatch with no consumer-visible behavior change |
| Advisory | A surface class with no declaration at all — a contract gap, not drift; contract-test opportunity |

## Related Skills

- [doc-auditor] — verifies *prose* documentation claims against the code; this skill verifies the *machine-readable contract*
- `commit-auditor` — checks the commit label against the diff; this skill checks the surface against the label (referenced by name; sibling skill)
- [arch-auditor] — architectural boundary violations
- [nitpicker] — whole-repo audit orchestrator

---

[doc-auditor]: ../doc-auditor/README.md
[arch-auditor]: ../arch-auditor/README.md
[nitpicker]: ../nitpicker/README.md
