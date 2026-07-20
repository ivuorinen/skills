# /nitpicker contract — API Contract Auditor

Hostile audit of the project's public contract surface: assume the contract has drifted until every declared element is verified against the implementation, and every surface change since the last release tag is verified against the semver bump the commits declare.

## When to use

- Verifying an OpenAPI/Swagger/GraphQL spec, package export list, published type declarations, or documented CLI flags against the implementation
- Before a release, to prove no unlabeled breaking change is pending and the last shipped release did not break consumers under a minor/patch bump
- After a refactor that touched route handlers, resolvers, exports, or the CLI parser
- Triggers: "audit the api contract", "does the spec match the code", "is this change breaking"

Two axes. **Axis 1 — declaration vs implementation:** OpenAPI/Swagger paths, methods, parameters, request/response shapes, status codes, and auth requirements vs the actual route handlers; GraphQL schema vs resolvers; published TypeScript types and library exports vs runtime behavior; documented CLI flags vs the argument parser. **Axis 2 — surface change vs semver:** every removed or renamed exported symbol, function, or endpoint, narrowed parameter type, widened return type, changed default, removed or retyped response field, and stricter validation on an existing input since the last release tag, each classified breaking or non-breaking and checked against the version bump the commit messages declare.

Out of scope: prose documentation accuracy routes to `/nitpicker docs`; whether a commit message's label matches its diff routes to `/nitpicker commits` — the two semver commands pair: `/nitpicker commits` checks the label against the diff, this command checks the surface against the label; cross-reference overlapping findings by name when both fire. Architectural boundary violations route to `/nitpicker arch`. Internal or private API churn is not a contract and is never filed.

## Contract surface

The definition of "public" comes from the project's own declarations, never from guesswork. Inventory every declaration source present and record the element count per source. An element in any of these is public, whatever a comment or a teammate calls it.

| Source | Declared elements |
| --- | --- |
| OpenAPI / Swagger / AsyncAPI files | Paths, methods, parameters, request/response schemas, status codes, security requirements |
| GraphQL SDL or code-first schema | Types, fields, arguments, nullability, and the resolvers bound to them |
| Package manifest + type surface | `package.json` `exports`/`main`/`types`/`bin`, published `.d.ts`, `__all__`, public headers, re-export barrels |
| CLI | Flags and subcommands in `--help` text and man pages vs the argument parser definition |
| Route tables | Framework route registrations — inventoried with or without a spec; a spec-less route surface is the Advisory contract-gap |

## Change classes (axis 2)

| Change since the baseline | Compatibility |
| --- | --- |
| Removed or renamed exported symbol, function, endpoint, method, or flag | Breaking |
| Narrowed parameter/input type; new required parameter or field | Breaking |
| Widened return/output type; response field removed or retyped | Breaking |
| Changed default value on an existing input | Breaking |
| Stricter validation on an existing input | Breaking |
| Additive: new optional parameter, new endpoint, new export, widened input, narrowed output | Non-breaking |

## Process

1. **Inventory the declared surface.** Enumerate every source in the Contract Surface table and every element it declares; record counts per source. The inventory is the coverage checklist: every element is verified before the run is COMPLETE. Never sample; unexamined elements are reported by name in the summary and force verdict INCOMPLETE.
2. **Axis 1 — verify every declared element against its implementation.** Locate the implementing handler/resolver/symbol/parser entry; confirm path, method, every parameter (name, type, required/optional), request/response shape, status codes, and auth requirement match the declaration. Check both directions: declared-but-not-implemented AND implemented-but-undeclared (a live route, export, or flag absent from the declaration).
3. **Axis 2 — diff the surface against the release baseline.** Baseline = latest semver tag (`git describe --tags --abbrev=0`); with no tag, the first commit — record the baseline in the summary either way. Diff every spec file, export declaration, type surface, route registration, and parser definition between baseline and HEAD; classify each change per the Change Classes table. Read the bump the commits since the baseline declare (`feat!`/`BREAKING CHANGE` → major, `feat` → minor, `fix` → patch); without conventional commits, read it from the version-manifest diff; neither → declared bump none. Check every breaking change against it. Also check the last shipped pair (previous tag → latest tag): a breaking change published under a minor or patch tag is Critical.
4. **File findings** via the store protocol in `_conventions.md`, using `--auditor contract`. Every finding carries the four-part evidence: the declared element (file:line), the implementation (file:line or "absent"), the mismatch, and the consumer-visible consequence. Axis 2 findings add the breaking/non-breaking classification vs the declared bump; cross-reference overlapping `/nitpicker commits` finding ids in the mismatch.
5. **Summary and fix gate.** State the run verdict (COMPLETE only when every declared element is verified and every baseline change classified). This command overrides the shared apply-fixes prompt — ask per finding, Critical first:
   `Fix [<id>]? (s)pec — edit the declaration to match the implementation  (c)ode — edit the implementation to honor the declaration  (n)either — leave open`
   Spec edits and code edits are separate approvals: fixing drift means deciding which side is right, and that is the user's call per finding. Never batch the side decision across findings and never default a side. After each applied fix, re-verify the element; only a re-verified element is resolved as fixed. Fix edits to spec files and source stay in the working tree unstaged.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | A shipped release already broke consumers without a major bump — a breaking surface change sits between the previous tag and a published minor or patch tag |
| High | A pending breaking change is unlabeled — breaking surface change since the baseline with a declared bump below major — or the spec promises an endpoint, field, type, status code, or auth requirement the implementation does not honor |
| Medium | Implemented-but-undeclared surface (live route, export, or flag absent from the declaration); a non-breaking change declared as breaking (over-labeled bump); implementation more permissive than the declaration (accepts more than promised) |
| Low | Drift on an element the declaration itself marks deprecated; naming/metadata mismatch (operationId, tag names) with no consumer-visible behavior change |
| Advisory | A surface class with no declaration at all (routes with no spec, a CLI with no documented flags) — a contract gap, not drift; contract-test opportunity |

## Fix strategy

**Per-finding, side-specific approval — the only apply path. There are no auto-applicable fixes: every fix rewrites one side of a contract, and every one waits for the per-finding answer.**

- `(s)pec`: edit the declaration to match the implementation — add the missing element, correct the shape, status code, parameter, or auth requirement
- `(c)ode`: edit the implementation to honor the declaration — restore the removed or renamed symbol (or add an alias), widen the narrowed input, revert the changed default, return the promised shape and status
- For an unlabeled breaking change the user keeps: the finding's fix is the label — record in the finding that the pending release requires a major bump. Version manifests, commit messages, and tags are release tooling's to change, never this command's.

**Never:**

- Decide which side is right — no spec or code edit without the per-finding `(s)/(c)` answer
- Edit both sides of one finding
- Bump a version, rewrite a commit message, or create a tag
- Mark a finding fixed without re-verifying the element against its declaration
- File internal or private API churn as a finding

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

- **"The spec was generated from code, so it can't drift."** Generated-then-hand-edited is the common case, regeneration is skipped on hot fixes, and the generation config itself drifts — excluded routes, serializer overrides, stale annotations. Verify every generated element the same as a hand-written one.
- **"There's no OpenAPI file, so there's nothing to audit."** Package exports, published type declarations, CLI flags, and GraphQL schemas are contracts. Inventory every source in the Contract Surface table; the run is INCOMPLETE until each present source is verified. A project with routes and no spec gets an Advisory contract-gap finding, not a pass.
- **"I'll spot-check the big endpoints."** Drift concentrates in the element nobody looks at. Verify every declared element; a sampled run has verdict INCOMPLETE, stated prominently in the summary — never presented as done, and never as "done with caveats".
- **"Renaming that export is fine — it's basically internal."** Declared public is public. If it is in `exports`, `__all__`, the `.d.ts`, or the spec, its removal or rename is a breaking change regardless of who the author believes uses it.
- **"The type change is compatible in practice; real clients won't notice."** Compatibility is judged against the declaration, not against imagined clients. A consumer compiled or validated against the declared type breaks on the declared difference; classify by the Change Classes table, not by optimism.
- **"I'll fix the spec to match the code without asking."** Fixing drift means deciding which side is right, and the code is as likely the bug as the spec. Every fix waits for the per-finding `(s)pec/(c)ode/(n)either` answer; a batch answer or a defaulted side is a violation.
- **"Semver policing is the commits command's job."** `/nitpicker commits` checks the label against the diff text; this command checks the surface against the label. A breaking surface change riding a `fix:` label is a High here even when the commit message honestly describes its diff — cross-reference, never defer.
- **"There's no release tag, so axis 2 doesn't apply."** With no tag, the baseline is the first commit; record the baseline in the summary and run the axis. An unversioned project accumulating unlabeled breaking changes is the case this axis exists for.
