---
name: api-contract-auditor
description: 'Audits the declared public contract surface (OpenAPI/GraphQL specs, package exports, published types, CLI flags) against the implementation, and every surface change since the last release tag against its declared semver bump. Use when checking spec-vs-code drift, classifying pending surface changes as breaking, or gating a release on contract compatibility. Triggers: "audit the api contract", "does the spec match the code", "is this change breaking", "run api-contract-auditor".'
---

# API Contract Auditor

## Overview

Hostile audit of the project's public contract surface. It assumes the contract has drifted until every declared surface element is verified against the implementation, and every surface change since the last release tag is verified against the compatibility label the commits declare. Two axes. Axis 1 — declaration vs implementation: OpenAPI/Swagger paths, methods, parameters, request/response shapes, status codes, and auth requirements vs the actual route handlers; GraphQL schema vs resolvers; published TypeScript types and library exports vs runtime behavior; documented CLI flags vs the argument parser. Axis 2 — surface change vs semver: every removed or renamed exported symbol, function, or endpoint, narrowed parameter type, widened return type, changed default, removed or retyped response field, and stricter validation on an existing input since the last release tag, each classified breaking or non-breaking and checked against the version bump the commit messages declare. Single-shot: re-validate existing findings, inventory the declared surface, verify both axes, file findings, run the per-finding fix gate, ask before committing.

Out of scope: prose documentation accuracy is `doc-auditor`'s surface; whether a commit message's label matches its diff is `commit-auditor`'s surface — cross-reference it by name in findings when both fire. The two semver skills pair: `commit-auditor` checks the label against the diff, this skill checks the surface against the label. Internal or private API churn is not a contract and is never filed.

## When to Use

- Verifying an OpenAPI/Swagger/GraphQL spec, package export list, published type declarations, or documented CLI flags against the implementation
- Before a release, to prove no unlabeled breaking change is pending and the last shipped release did not break consumers under a minor/patch bump
- After a refactor that touched route handlers, resolvers, exports, or the CLI parser
- When asked "does the spec match the code", "is this change breaking", or to "audit the api contract"

**When NOT to use:** For prose documentation accuracy (README claims, guides, comments), use `doc-auditor`. For whether a commit message's label matches its diff text, use `commit-auditor`. For architectural boundary violations, use `arch-auditor`.

## Process

### Contract Surface

The definition of "public" comes from the project's own declarations, never from guesswork. Inventory every declaration source present and record the element count per source. An element in any of these is public, whatever a comment or a teammate calls it.

| Source | Declared elements |
|--------|-------------------|
| OpenAPI / Swagger / AsyncAPI files | Paths, methods, parameters, request/response schemas, status codes, security requirements |
| GraphQL SDL or code-first schema | Types, fields, arguments, nullability, and the resolvers bound to them |
| Package manifest + type surface | `package.json` `exports`/`main`/`types`/`bin`, published `.d.ts`, `__all__`, public headers, re-export barrels |
| CLI | Flags and subcommands in `--help` text and man pages vs the argument parser definition |
| Route tables | Framework route registrations — inventoried with or without a spec; a spec-less route surface is the Advisory contract-gap |

### Change Classes (Axis 2)

| Change since the baseline | Compatibility |
|---------------------------|---------------|
| Removed or renamed exported symbol, function, endpoint, method, or flag | Breaking |
| Narrowed parameter/input type; new required parameter or field | Breaking |
| Widened return/output type; response field removed or retyped | Breaking |
| Changed default value on an existing input | Breaking |
| Stricter validation on an existing input | Breaking |
| Additive: new optional parameter, new endpoint, new export, widened input, narrowed output | Non-breaking |

### Steps

```
0. Re-validate existing findings
   Run `uv run --quiet skills/nitpicker/check-audit-consistency.py docs/audit/api-contract-auditor-findings.md`
   when both files exist (script absent → record the gap as Advisory). Then for each finding
   with Status: Open: drift gone after re-verifying (the two sides agree again, or the declared
   bump now matches the surface) → Fixed (record date); finding was wrong → Invalid (record
   reason); still drifted → leave Open.

1. Inventory the declared surface
   Enumerate every source in the Contract Surface table and every element it declares; record
   counts per source. The inventory is the coverage checklist: every element is verified before
   the run is COMPLETE. Never sample. `Open-Unexamined` is reserved for genuine time exhaustion
   and forces run verdict INCOMPLETE.

2. Axis 1 — verify every declared element against its implementation
   Locate the implementing handler/resolver/symbol/parser entry; confirm path, method, every
   parameter (name, type, required/optional), request/response shape, status codes, and auth
   requirement match the declaration. Check both directions: declared-but-not-implemented AND
   implemented-but-undeclared (a live route, export, or flag absent from the declaration).

3. Axis 2 — diff the surface against the release baseline
   Baseline = latest semver tag (`git describe --tags --abbrev=0`); with no tag, the first
   commit — record the baseline in the Summary either way. Diff every spec file, export
   declaration, type surface, route registration, and parser definition between baseline and
   HEAD; classify each change per the Change Classes table. Read the bump the commits since the
   baseline declare (feat!/BREAKING CHANGE → major, feat → minor, fix → patch); without
   conventional commits, read it from the version-manifest diff; neither → declared bump none.
   Check every breaking change against it. Also check the last shipped pair (previous tag →
   latest tag): a breaking change published under a minor or patch tag is Critical.

4. File findings and write docs/audit/api-contract-auditor-findings.md
   Assign the next AC-NNN id. Every finding carries the four-part evidence: declared element
   (file:line), implementation (file:line or "absent"), the mismatch, and the consumer-visible
   consequence. Axis 2 findings add the breaking/non-breaking classification vs the declared
   bump; cross-reference overlapping commit-auditor ids in the Mismatch line. Update
   "Last validated" to today; "Generated" is the first-run date — never change it.

5. Present summary and run the fix gate
   State the run verdict (COMPLETE only when every declared element is verified and every
   baseline change classified). Then ask per finding, Critical first:
   "Fix [AC-NNN]? (s)pec — edit the declaration to match the implementation
    (c)ode — edit the implementation to honor the declaration  (n)either — leave Open"
   Spec edits and code edits are separate approvals: fixing drift means deciding which side is
   right, and that is the user's call per finding. Never batch the side decision across
   findings and never default a side. After each applied fix, re-verify the element; only a
   re-verified element moves to Fixed.

6. Commit gate
   Fix edits to spec files and source stay in the working tree unstaged — never stage or commit
   them silently. Ask: "Commit findings to git? (y/n)"; on yes, stage only the findings file.
```

## Findings Format

Output path: `docs/audit/api-contract-auditor-findings.md`

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
- Open-Unexamined: N
- Unexamined: <element or change> — <why not examined>

## Open Findings

### Critical

#### [AC-NNN] Short title
Status: Open
Axis: <declaration-drift|semver-drift>
Class: <missing-implementation|undeclared-surface|shape-mismatch|status-code-mismatch|auth-mismatch|param-mismatch|removed-symbol|renamed-symbol|narrowed-input|widened-output|changed-default|stricter-validation|retyped-field>
Declared: <the spec/export/flag element — file:line>
Implementation: <file:line, or "absent">
Mismatch: <what differs; cross-reference commit-auditor ids here when they overlap>
Consumer impact: <what a consumer built against the declaration sees break>
Semver: <breaking|non-breaking> vs declared bump <major|minor|patch|none> (axis 2 findings only)
Fix: <the spec-side edit AND the code-side edit — the user picks the side>

### High
[same structure — likewise ### Medium, ### Low, ### Advisory]

## Fixed

### Pass N — YYYY-MM-DD

#### [AC-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <which side was edited, and the re-verification showing declaration and implementation agree>

## Invalid

### Pass N — YYYY-MM-DD

#### [AC-NNN] Short title
Notes: <why the drift or misclassification was not real>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes the
`Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the
other `## Summary` bullets after it — keep the Total line in exactly that shape and insert no field
between `Total:` and `Invalid:`. Unexamined elements live as `Unexamined:` Summary bullets, never in
a separate section; `Open-Unexamined` is not part of the finding totals. Only Open findings carry
the `Status:` line — drop it on moving to Fixed or Invalid; step 0 re-checks every `Status: Open`
finding. IDs are `AC-NNN`, zero-padded to 3 digits, assigned sequentially, never reused.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | A shipped release already broke consumers without a major bump — a breaking surface change sits between the previous tag and a published minor or patch tag |
| High | A pending breaking change is unlabeled — breaking surface change since the baseline with a declared bump below major — or the spec promises an endpoint, field, type, status code, or auth requirement the implementation does not honor |
| Medium | Implemented-but-undeclared surface (live route, export, or flag absent from the declaration); a non-breaking change declared as breaking (over-labeled bump); implementation more permissive than the declaration (accepts more than promised) |
| Low | Drift on an element the declaration itself marks deprecated; naming/metadata mismatch (operationId, tag names) with no consumer-visible behavior change |
| Advisory | A surface class with no declaration at all (routes with no spec, a CLI with no documented flags) — a contract gap, not drift; contract-test opportunity |

## Fix Strategy

**Per-finding, side-specific approval — the only apply path. There are no auto-applicable fixes: every fix rewrites one side of a contract, and every one waits for the per-finding answer.**
- `(s)pec`: edit the declaration to match the implementation — add the missing element, correct the shape, status code, parameter, or auth requirement
- `(c)ode`: edit the implementation to honor the declaration — restore the removed or renamed symbol (or add an alias), widen the narrowed input, revert the changed default, return the promised shape and status
- For an unlabeled breaking change the user keeps: the finding's fix is the label — record in the finding that the pending release requires a major bump. Version manifests, commit messages, and tags are release tooling's to change, never this skill's.

**Never:**
- Decide which side is right — no spec or code edit without the per-finding `(s)/(c)` answer
- Edit both sides of one finding
- Bump a version, rewrite a commit message, or create a tag
- Mark a finding Fixed without re-verifying the element against its declaration
- File internal or private API churn as a finding

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"The spec was generated from code, so it can't drift."** Generated-then-hand-edited is the common case, regeneration is skipped on hot fixes, and the generation config itself drifts — excluded routes, serializer overrides, stale annotations. Verify every generated element the same as a hand-written one.

**"There's no OpenAPI file, so there's nothing to audit."** Package exports, published type declarations, CLI flags, and GraphQL schemas are contracts. Inventory every source in the Contract Surface table; the run is INCOMPLETE until each present source is verified. A project with routes and no spec gets an Advisory contract-gap finding, not a pass.

**"I'll spot-check the big endpoints."** Drift concentrates in the element nobody looks at. Verify every declared element; a sampled run has verdict INCOMPLETE, stated prominently in the summary — never presented as done, and never as "done with caveats".

**"Renaming that export is fine — it's basically internal."** Declared public is public. If it is in `exports`, `__all__`, the `.d.ts`, or the spec, its removal or rename is a breaking change regardless of who the author believes uses it.

**"The type change is compatible in practice; real clients won't notice."** Compatibility is judged against the declaration, not against imagined clients. A consumer compiled or validated against the declared type breaks on the declared difference; classify by the Change Classes table, not by optimism.

**"I'll fix the spec to match the code without asking."** Fixing drift means deciding which side is right, and the code is as likely the bug as the spec. Every fix waits for the per-finding `(s)pec/(c)ode/(n)either` answer; a batch answer or a defaulted side is a violation.

**"Semver policing is commit-auditor's job."** commit-auditor checks the label against the diff text; this skill checks the surface against the label. A breaking surface change riding a `fix:` label is a High here even when the commit message honestly describes its diff — cross-reference, never defer.

**"There's no release tag, so axis 2 doesn't apply."** With no tag, the baseline is the first commit; record the baseline in the Summary and run the axis. An unversioned project accumulating unlabeled breaking changes is the case this axis exists for.
