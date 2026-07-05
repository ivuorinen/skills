---
name: dep-auditor
description: 'Hostile single-shot audit of dependency health beyond CVEs — finds unused, phantom, duplicate, heavyweight, unmaintained, license-conflicting, drifted, and misclassified dependencies by cross-referencing manifest, lockfile, and a full import/usage scan. Use when auditing what a project already depends on, pruning the dependency tree, or gating a release on manifest hygiene. Triggers: "audit dependencies", "unused dependencies", "dependency health", "prune deps", "run dep-auditor".'
---

# Dependency Auditor

## Overview

Hostile audit of every dependency the project already declares or silently relies on. It treats every manifest entry as dead weight until an actual usage is proven, and every import as undeclared until a manifest names it. Single-shot: re-validate existing findings, inventory manifests and lockfiles, build the declared/locked/referenced sets, cross-reference, file findings, optionally fix on approval, ask before committing. CVEs and supply-chain advisories are out of scope — route them to `security-auditor`. Whether a NEW dependency should be added is out of scope — `complexity-hunter`'s ladder governs that decision before the add; this skill audits what is already installed. Findings are graded Critical → Advisory and written to `docs/audit/dep-auditor-findings.md`.

## When to Use

- Auditing what a project already depends on: dead, duplicated, misdeclared, drifted, or abandoned dependencies
- Before a release, or after a refactor or feature removal, to prove the manifest matches what the code actually imports
- When asked to "audit dependencies", "find unused dependencies", "prune deps", or "check dependency health"

**When NOT to use:** For CVEs and vulnerable versions, use `security-auditor`. For deciding whether a proposed new dependency is justified, use `complexity-hunter`. For general code defects, use `nitpicker`.

## Process

### Defect Classes

| Class | Definition |
|-------|------------|
| unused-dependency | Declared in a manifest, referenced by no import form, config plugin reference, script, or binary invocation |
| phantom-dependency | Imported by source or config but declared in no manifest — resolves only through a transitive |
| duplicate-dependency | Two or more declared packages covering the same capability (two HTTP clients, two date libraries, lodash + underscore) |
| heavyweight-dependency | A declared package whose only usage is one function replaceable by ten or fewer lines of stdlib/local code |
| unmaintained-upstream | Upstream archived or formally deprecated, proven by fetched metadata (registry deprecation field, archived flag) — never inferred from release age |
| license-conflict | Dependency license incompatible with the project's declared license |
| manifest-lockfile-drift | Lockfile missing, stale, or disagreeing with the manifest (entry or version-range mismatch) |
| misclassified-dependency | Runtime dependency declared dev-only, or dev/build tool declared as production |

**Evidence rule:** every finding cites all three sources — the manifest line, the lockfile entry, and the usage-scan result. Any leg is satisfiable by an exhaustive negative ("declared in no manifest" for a phantom, "no reference after the full scan" for unused, "lockfile missing" for drift) — but only after the exhaustive check actually ran. A finding missing any leg is not filed; a leg is never skipped on the grounds that its class "obviously" lacks it.

### Import-Form Coverage

A dependency is "unused" only after every reference form its ecosystem supports comes back empty:

| Ecosystem | Reference forms to scan |
|-----------|-------------------------|
| JS/TS | `require()`, static `import`/`export from`, dynamic `import()`, type-only imports and `@types/*` pairing, `package.json` scripts binaries, config plugin/preset/extends strings (eslint, prettier, babel, jest, postcss, tailwind, vite/webpack plugin arrays) |
| Python | `import` / `from ... import`, `importlib`, `__import__`, entry points, plugins auto-loaded from config (pytest, flake8), tool sections in `pyproject.toml`/`setup.cfg`, Makefile/CI script invocations |
| Other (Rust, Go, PHP, Ruby, ...) | That ecosystem's full import/use/require forms plus build-config and task-runner references |

Map package names to import names before scanning (`beautifulsoup4` → `bs4`, `Pillow` → `PIL`, `@scope/pkg` subpaths) — a grep for the package name alone proves nothing in either direction.

### Tooling

Probe every tool with `which` before use; run only what is installed; never install anything, not even a scanner.

| Tool | Use |
|------|-----|
| depcheck | JS unused/phantom candidates |
| deptry | Python unused/phantom/misclassified candidates |
| npm/pnpm/yarn ls, pip list / uv pip list, cargo tree, go mod why, composer show, bundle list | Installed-vs-locked comparison; parse the full output, never sample it |
| npm view / pip index / registry metadata (read-only) | Deprecation/archived status and license fields |

A tool's candidate list is input, not a finding — verify every candidate against the Import-Form Coverage table before filing; the tools miss config-plugin references and name mappings. Where maintenance or license metadata is unreachable (tool absent, no network), record the dependency under Unexamined — never guess either way.

### Steps

```
0. Re-validate: if docs/audit/dep-auditor-findings.md exists, re-check every Status: Open
   finding against the current manifest/lockfile/scan — resolved → Fixed, wrong → Invalid
   (record date, pass, and why), still true → leave Open.
1. Inventory: find every manifest + lockfile pair (package.json, pyproject.toml,
   requirements*.txt, Cargo.toml, go.mod, composer.json, Gemfile + their lockfiles) and the
   project's declared license. A generated-but-uncommitted lockfile is manifest-lockfile-drift
   (severity per the Severity Guide: application vs. published library).
2. Probe tools per the Tooling table; record available/not-available.
3. Build three sets per ecosystem: Declared (manifest, per section), Locked (lockfile),
   Referenced (full usage scan per Import-Form Coverage).
4. Cross-reference the sets; file findings per Defect Class. Examine every declared dependency
   against every class; anything not fully examined becomes an Unexamined Summary bullet and
   forces verdict INCOMPLETE.
5. Check maintenance status and license for every declared dependency via available metadata.
6. Write docs/audit/dep-auditor-findings.md. Update "Last validated" to today; "Generated" is
   the first-run date — never change it.
7. Present summary (verdict, counts by severity, Unexamined list), then ask:
   "Apply fixes? (a)uto-applicable  (s)afe only  (n)o" — (a) applies every Auto-applicable
   fix from Fix Strategy; (s) regenerates drifted lockfiles only, no manifest edits.
   Removals, replacements, and consolidations are NEVER covered by (a) or (s): each is
   presented with its evidence and approved per dependency. Never batch-remove.
8. Ask: "Commit findings to git? (y/n)" — never commit silently. Manifest/lockfile edits stay
   unstaged in the working tree.
```

## Findings Format

Output path: `docs/audit/dep-auditor-findings.md`

```
# Dependency Audit Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N dependencies/checks unexamined)
- Ecosystems: <npm|pip|cargo|...> | Project license: <SPDX id or "undeclared">
- Sets: declared N | locked N | referenced N
- Tools: available <list> | not available <list>
- Unexamined: <dependency or check> — <why not examined>

## Open Findings

### Critical

#### [DEP-NNN] Short title
Status: Open
Class: <unused-dependency|phantom-dependency|duplicate-dependency|heavyweight-dependency|unmaintained-upstream|license-conflict|manifest-lockfile-drift|misclassified-dependency>
Ecosystem: <npm|pip|cargo|...>
Package: <name@version>
Manifest: <file:line and section, or "declared in no manifest">
Lockfile: <file and entry, or "missing">
Usage: <referencing file:line, or "no reference after full Import-Form Coverage scan">
Problem: <what is wrong>
Impact: <why this matters>
Fix: <exact command or manifest edit>

### High
[same structure]

### Medium
[same structure]

### Low
[same structure]

### Advisory
[same structure]

## Fixed

### Pass N — YYYY-MM-DD

#### [DEP-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <what changed and the re-run scan/tool result that confirms it>

## Invalid

### Pass N — YYYY-MM-DD

#### [DEP-NNN] Short title
Notes: <why the finding was wrong — e.g. the reference form the original scan missed>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the other `## Summary` bullets after it. Keep the Total line in exactly that shape and insert no field between `Total:` and `Invalid:`. All fixed findings live under one `## Fixed` h2 and all invalid findings under one `## Invalid` h2, each sub-divided by `### Pass N — YYYY-MM-DD` h3 headers. Unexamined items live as `Unexamined:` Summary bullets, never in a separate section, and are not part of the Open/Fixed/Invalid totals.

The per-finding `Status:` field is `Open` for an examined, still-true finding; drop it on moving a finding to Fixed or Invalid. Step 0 re-validation re-checks every finding with `Status: Open`. Finding ID format: `DEP-NNN` (zero-padded to 3 digits). Assign sequentially from the highest existing ID; never reuse or renumber IDs. Pass number = highest existing `### Pass N` in the file + 1, or 1 on the first run; a pass with nothing fixed or invalidated adds no pass group.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | license-conflict with the project's declared license; phantom-dependency on a production code path — one transitive-graph change breaks the build |
| High | manifest-lockfile-drift (manifest/lockfile disagreement, or missing lockfile in an application); runtime dependency declared dev-only (absent from production installs); unused production dependency |
| Medium | duplicate-dependency; unmaintained-upstream proven by metadata; dev/build tool declared as production; phantom-dependency on a dev/test-only path |
| Low | unused dev dependency; heavyweight-dependency |
| Advisory | Deprecated upstream whose own metadata names a drop-in replacement; capability overlap that exists only in transitive graphs; missing lockfile in a published library that ships version ranges |

## Fix Strategy

**Auto-applicable (ask first, apply on approval):**
- Regenerate a drifted lockfile with the ecosystem's lockfile-only command (`npm install --package-lock-only`, `uv lock`, `cargo generate-lockfile`)
- Move a misclassified dependency between sections at its current version
- Declare a phantom dependency in the manifest at its currently locked version

**Requires explicit approval per dependency (removals are behavior-affecting):**
- Removing any dependency — present the package, the negative-scan evidence, and the exact removal command, then wait for approval before touching the manifest
- Replacing a heavyweight dependency with local code — include the exact replacement code in the finding
- Consolidating duplicates onto one package — touches every usage site

**Never:**
- Install, add, or upgrade any package (version upgrades belong to `security-auditor`; new-dependency decisions to `complexity-hunter`)
- Remove a dependency whose scan covered anything less than the full Import-Form Coverage table
- Mark a finding Fixed without re-running the exact scan or tool check that filed it

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"No import hits in a grep of src/, so it's unused."** Source imports are one reference form of many. Eslint plugins named in config, pytest plugins auto-loaded, binaries called from `package.json` scripts or Makefiles, and import names that differ from package names all count as usage. Run the full Import-Form Coverage table or file nothing.

**"The lockfile is machine-generated, skip it."** The lockfile is one of the three evidence legs and the sole witness for manifest-lockfile-drift and phantom resolution. Read it every run.

**"Checking every dep's maintenance status is too slow, I'll spot-check."** Every declared dependency gets the maintenance and license check. A dependency skipped for time is an Unexamined bullet and forces verdict INCOMPLETE — never a silent pass.

**"License fields are boilerplate, skip them."** A copyleft dependency inside a permissively-licensed project is a Critical finding. Read the license field of every declared dependency and the project's own declared license.

**"It's a devDependency so it doesn't matter."** Dev dependencies run in CI and on every contributor machine, and misclassification in either direction is its own defect class. Dev status lowers severity; it never grants exemption from examination.

**"npm ls output is huge, I'll sample it."** Parse the full tree output. A sampled tree is an unexamined set and forces verdict INCOMPLETE.

**"Last publish was three years ago, so it's abandoned."** Release age proves nothing — stable software goes quiet. File unmaintained-upstream only on fetched metadata: an archived flag or a formal deprecation notice. Metadata unreachable → Unexamined, never a guess.

**"depcheck says it's unused, file it."** Tool output is a candidate list, not evidence. depcheck and deptry miss config-plugin references and name mappings; verify every candidate against the full scan before filing.

**"It's unused, so removing it is safe — just delete it."** Removal is behavior-affecting: a "false unused" breaks the build or a runtime path. Every removal is presented with its evidence and approved per dependency before any manifest edit.

**"While I'm here, this version has a CVE — I'll file that too."** CVEs are `security-auditor`'s surface. Tell the user to run it; file no DEP finding for a vulnerability.
