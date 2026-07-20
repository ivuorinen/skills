# /nitpicker deps — Dependency Health Audit

Hostile audit of every dependency the project already declares or silently relies on: every manifest entry is dead weight until an actual usage is proven, and every import is undeclared until a manifest names it.

## When to use

- Auditing what a project already depends on: dead, duplicated, misdeclared, drifted, or abandoned dependencies
- Before a release, or after a refactor or feature removal, to prove the manifest matches what the code actually imports
- A dependency tree that has grown for years without an audit
- When asked to "audit dependencies", "find unused dependencies", "prune deps", or "check dependency health"

Out of scope: CVEs, vulnerable versions, and supply-chain advisories route to `/nitpicker security`. Whether a proposed NEW dependency is justified routes to `/nitpicker complexity` — its ladder governs the decision before the add; this command audits what is already installed. General code defects are `/nitpicker audit`.

## Defect classes

| Class | Definition |
| --- | --- |
| unused-dependency | Declared in a manifest, referenced by no import form, config plugin reference, script, or binary invocation |
| phantom-dependency | Imported by source or config but declared in no manifest — resolves only through a transitive |
| duplicate-dependency | Two or more declared packages covering the same capability (two HTTP clients, two date libraries, lodash + underscore) |
| heavyweight-dependency | A declared package whose only usage is one function replaceable by ten or fewer lines of stdlib/local code |
| unmaintained-upstream | Upstream archived or formally deprecated, proven by fetched metadata (registry deprecation field, archived flag) — never inferred from release age |
| license-conflict | Dependency license incompatible with the project's declared license |
| manifest-lockfile-drift | Lockfile missing, stale, or disagreeing with the manifest (entry or version-range mismatch) |
| misclassified-dependency | Runtime dependency declared dev-only, or dev/build tool declared as production |

**Evidence rule:** every finding cites all three sources — the manifest line, the lockfile entry, and the usage-scan result. Any leg is satisfiable by an exhaustive negative ("declared in no manifest" for a phantom, "no reference after the full scan" for unused, "lockfile missing" for drift) — but only after the exhaustive check actually ran. A finding missing any leg is not filed; a leg is never skipped on the grounds that its class "obviously" lacks it.

## Import-form coverage

A dependency is "unused" only after every reference form its ecosystem supports comes back empty:

| Ecosystem | Reference forms to scan |
| --- | --- |
| JS/TS | `require()`, static `import`/`export from`, dynamic `import()`, type-only imports and `@types/*` pairing, `package.json` scripts binaries, config plugin/preset/extends strings (eslint, prettier, babel, jest, postcss, tailwind, vite/webpack plugin arrays) |
| Python | `import` / `from ... import`, `importlib`, `__import__`, entry points, plugins auto-loaded from config (pytest, flake8), tool sections in `pyproject.toml`/`setup.cfg`, Makefile/CI script invocations |
| Other (Rust, Go, PHP, Ruby, ...) | That ecosystem's full import/use/require forms plus build-config and task-runner references |

Map package names to import names before scanning (`beautifulsoup4` → `bs4`, `Pillow` → `PIL`, `@scope/pkg` subpaths) — a grep for the package name alone proves nothing in either direction.

## Tooling

Probe every tool with `which` before use; run only what is installed; never install anything, not even a scanner.

| Tool | Use |
| --- | --- |
| depcheck | JS unused/phantom candidates |
| deptry | Python unused/phantom/misclassified candidates |
| npm/pnpm/yarn ls, pip list / uv pip list, cargo tree, go mod why, composer show, bundle list | Installed-vs-locked comparison; parse the full output, never sample it |
| npm view / pip index / registry metadata (read-only) | Deprecation/archived status and license fields |

A tool's candidate list is input, not a finding — verify every candidate against the import-form coverage table before filing; the tools miss config-plugin references and name mappings. Where maintenance or license metadata is unreachable (tool absent, no network), record the dependency as unexamined in the run summary — never guess either way.

## Process

1. **Inventory:** find every manifest + lockfile pair (package.json, pyproject.toml, requirements*.txt, Cargo.toml, go.mod, composer.json, Gemfile + their lockfiles) and the project's declared license. A generated-but-uncommitted lockfile is manifest-lockfile-drift (severity per the guide: application vs. published library).
2. **Probe tools** per the tooling table; record available/not-available in the run summary.
3. **Build three sets per ecosystem:** Declared (manifest, per section), Locked (lockfile), Referenced (full usage scan per import-form coverage).
4. **Cross-reference the sets;** file findings per defect class via the store protocol in `_conventions.md`, using `--auditor deps`. Each finding's Evidence carries the three legs (manifest file:line and section, lockfile entry or "missing", referencing file:line or the exhaustive negative) plus ecosystem and `name@version`. Examine every declared dependency against every class; anything not fully examined is recorded as unexamined and forces run verdict INCOMPLETE.
5. **Check maintenance status and license** for every declared dependency via available metadata.
6. **Summarize and fix.** The summary states the run verdict (COMPLETE | INCOMPLETE with the unexamined list), ecosystems, project license, and set sizes. Fix application and the commit gate follow `_conventions.md`, with these overrides: the (s)afe option regenerates drifted lockfiles only, no manifest edits; removals, replacements, and consolidations are NEVER batch-applied — each is presented with its evidence and approved per dependency. Never batch-remove.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | license-conflict with the project's declared license; phantom-dependency on a production code path — one transitive-graph change breaks the build |
| High | manifest-lockfile-drift (manifest/lockfile disagreement, or missing lockfile in an application); runtime dependency declared dev-only (absent from production installs); unused production dependency |
| Medium | duplicate-dependency; unmaintained-upstream proven by metadata; dev/build tool declared as production; phantom-dependency on a dev/test-only path |
| Low | unused dev dependency; heavyweight-dependency |
| Advisory | Deprecated upstream whose own metadata names a drop-in replacement; capability overlap that exists only in transitive graphs; missing lockfile in a published library that ships version ranges |

## Fix strategy

**Auto-applicable:**

- Regenerate a drifted lockfile with the ecosystem's lockfile-only command (`npm install --package-lock-only`, `uv lock`, `cargo generate-lockfile`)
- Move a misclassified dependency between sections at its current version
- Declare a phantom dependency in the manifest at its currently locked version

**Requires explicit approval per dependency (removals are behavior-affecting):**

- Removing any dependency — present the package, the negative-scan evidence, and the exact removal command, then wait for approval before touching the manifest
- Replacing a heavyweight dependency with local code — include the exact replacement code in the finding
- Consolidating duplicates onto one package — touches every usage site

**Never:**

- Install, add, or upgrade any package (version upgrades belong to `/nitpicker security`; new-dependency decisions to `/nitpicker complexity`)
- Remove a dependency whose scan covered anything less than the full import-form coverage table
- Mark a finding fixed without re-running the exact scan or tool check that filed it

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

**"No import hits in a grep of src/, so it's unused."** Source imports are one reference form of many. Eslint plugins named in config, pytest plugins auto-loaded, binaries called from `package.json` scripts or Makefiles, and import names that differ from package names all count as usage. Run the full import-form coverage table or file nothing.

**"The lockfile is machine-generated, skip it."** The lockfile is one of the three evidence legs and the sole witness for manifest-lockfile-drift and phantom resolution. Read it every run.

**"Checking every dep's maintenance status is too slow, I'll spot-check."** Every declared dependency gets the maintenance and license check. A dependency skipped for time is an unexamined item and forces verdict INCOMPLETE — never a silent pass.

**"License fields are boilerplate, skip them."** A copyleft dependency inside a permissively-licensed project is a Critical finding. Read the license field of every declared dependency and the project's own declared license.

**"It's a devDependency so it doesn't matter."** Dev dependencies run in CI and on every contributor machine, and misclassification in either direction is its own defect class. Dev status lowers severity; it never grants exemption from examination.

**"npm ls output is huge, I'll sample it."** Parse the full tree output. A sampled tree is an unexamined set and forces verdict INCOMPLETE.

**"Last publish was three years ago, so it's abandoned."** Release age proves nothing — stable software goes quiet. File unmaintained-upstream only on fetched metadata: an archived flag or a formal deprecation notice. Metadata unreachable → unexamined, never a guess.

**"depcheck says it's unused, file it."** Tool output is a candidate list, not evidence. depcheck and deptry miss config-plugin references and name mappings; verify every candidate against the full scan before filing.

**"It's unused, so removing it is safe — just delete it."** Removal is behavior-affecting: a "false unused" breaks the build or a runtime path. Every removal is presented with its evidence and approved per dependency before any manifest edit.

**"While I'm here, this version has a CVE — I'll file that too."** CVEs are `/nitpicker security`'s surface. Route it there in one line; file no deps finding for a vulnerability.
