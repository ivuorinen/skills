# /nitpicker deps — Dependency Health Audit

Hostile audit of every dependency the project already declares or silently relies on: every manifest entry is dead weight until an actual usage is proven, and every import is undeclared until a manifest names it.

## When to use

- Auditing what a project already depends on: dead, duplicated, misdeclared, drifted, or abandoned dependencies
- Before a release, or after a refactor or feature removal, to prove the manifest matches what the code actually imports
- A dependency tree that has grown for years without an audit
- When asked to "audit dependencies", "find unused dependencies", "prune deps", or "check dependency health"

Out of scope: known CVEs and vulnerable versions route to `/nitpicker security`. The **supply-chain execution surface** — install-time code execution, namespace confusion, typosquats, and lockfile integrity — is audited *here* (the supply-chain classes below), not routed away: it is a structural property of the dependency set, not a per-version advisory. Whether a proposed NEW dependency is justified routes to `/nitpicker complexity` — its ladder governs the decision before the add; this command audits what is already installed. General code defects are `/nitpicker audit`.

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
| install-script | A dependency whose install runs a lifecycle script (`preinstall`/`install`/`postinstall`, `build.rs`, gem `extconf`, composer `scripts`) — arbitrary code executes on every install, CI run, and contributor machine |
| dependency-confusion | A **first-party or internal-intended** name — one the project builds or owns (an org/name-prefix match, a workspace-local package published unscoped, a name the team maintains privately) — resolving from a **public** registry with no scope/registry pin (`.npmrc`, index-url, lockfile registry), so a same-named public package gets installed in place of the intended private one. Ordinary third-party public dependencies (express, lodash) are never candidates |
| typosquat-risk | A declared name within a small edit distance of a materially more popular package in the same ecosystem, where the declared one is the less-known — a likely typo'd or malicious substitute |
| integrity-gap | A lockfile entry with no integrity hash, or resolved from a non-registry source (git URL, arbitrary tarball, a personal fork) that bypasses registry integrity verification |

**Evidence rule:** every health finding (the eight classes above `install-script`) cites all three sources — the manifest line, the lockfile entry, and the usage-scan result. Any leg is satisfiable by an exhaustive negative ("declared in no manifest" for a phantom, "no reference after the full scan" for unused, "lockfile missing" for drift) — but only after the exhaustive check actually ran. A finding missing any leg is not filed; a leg is never skipped on the grounds that its class "obviously" lacks it.

**Supply-chain evidence rule:** the four supply-chain classes turn on the install/resolution surface, not on usage, so they carry class-specific evidence instead of the three legs:

- `install-script` — the dependency `name@version` and the lifecycle-script witness: the lockfile `hasInstallScript` flag, or the script line in the package's own manifest (`scripts.postinstall`, `build`, `extconf.rb`, composer `scripts`).
- `dependency-confusion` — first, the evidence that the name is **first-party/internal-intended** (it matches the project's own name or org prefix, is a workspace-local package, or is stated to be team-maintained), never a recognized third-party package; then its resolution source proving public-registry origin (the lockfile `resolved` URL), **and** the exhaustive negative that no scope/registry pin protects it (no `.npmrc` scope binding, no lockfile registry restriction). A finding needs all three; an ordinary third-party dependency, or a private name that IS scope-pinned, is not confusion.
- `typosquat-risk` — the declared name **and** the materially-more-popular near-name it shadows, with the edit distance and the relative-familiarity gap stated. A name that is merely unfamiliar, with no popular twin, is not a typosquat — the near-miss to a popular package is the evidence, never a hunch.
- `integrity-gap` — the lockfile entry showing the missing `integrity` field or the non-registry `resolved` source.

Confirming that a name is claimed on the public registry (for `dependency-confusion`) or comparing download popularity (for `typosquat-risk`) needs registry access; where it is unreachable, record the dependency as unexamined for that class and force verdict INCOMPLETE — never guess the name is safe.

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
| npm view / pip index / registry metadata (read-only) | Deprecation/archived status and license fields; whether an internal name is publicly claimed (dependency-confusion) |
| npm downloads API (`GET https://api.npmjs.org/downloads/point/last-month/<pkg>`), PyPI stats (`pypistats` / `pypistats.org` API) | Download-count popularity for the typosquat-risk twin comparison — the concrete source `npm view`/`pip index` metadata lack; compare the declared name's count against the popular near-name's |
| lockfile fields, read directly (`hasInstallScript`, `integrity`, `resolved`) | install-script, integrity-gap, and dependency-confusion witnesses — parse the lockfile, no scanner needed |
| `.npmrc` / registry & scope config, `npm config get` | Whether a scope/registry pin protects an internal name (dependency-confusion negative leg) |

A tool's candidate list is input, not a finding — verify every candidate against the import-form coverage table before filing; the tools miss config-plugin references and name mappings. Where maintenance or license metadata is unreachable (tool absent, no network), record the dependency as unexamined in the run summary — never guess either way.

## Process

1. **Inventory:** find every manifest + lockfile pair (package.json, pyproject.toml, requirements*.txt, Cargo.toml, go.mod, composer.json, Gemfile + their lockfiles) and the project's declared license. A generated-but-uncommitted lockfile is manifest-lockfile-drift (severity per the guide: application vs. published library).
2. **Probe tools** per the tooling table; record available/not-available in the run summary.
3. **Build three sets per ecosystem:** Declared (manifest, per section), Locked (lockfile), Referenced (full usage scan per import-form coverage).
4. **Cross-reference the sets;** file findings per defect class via the store protocol in `_conventions.md`, using `--auditor deps`. Each finding's Evidence carries the three legs (manifest file:line and section, lockfile entry or "missing", referencing file:line or the exhaustive negative) plus ecosystem and `name@version`. Examine every declared dependency against every class; anything not fully examined is recorded as unexamined and forces run verdict INCOMPLETE.
5. **Check maintenance status and license** for every declared dependency via available metadata. In the same pass, **scan the supply-chain surface**: read each lockfile entry's `hasInstallScript` / `install`-script field (install-script), missing `integrity` or non-registry `resolved` source (integrity-gap), and public-registry resolution of any **first-party or internal-intended** name — one the project owns, builds, or privately maintains, never an ordinary third-party package — against the scope/registry config (dependency-confusion); and screen every declared name for a small-edit-distance near-miss to a materially more popular package (typosquat-risk). File each via `--auditor deps` with its class-specific evidence; a name whose public-registry or popularity check is unreachable is unexamined for that class and forces INCOMPLETE.
6. **Summarize and fix.** The summary states the run verdict (COMPLETE | INCOMPLETE with the unexamined list), ecosystems, project license, and set sizes. Fix application and the commit gate follow `_conventions.md`, with these overrides: the (s)afe option regenerates drifted lockfiles only, no manifest edits; removals, replacements, and consolidations are NEVER batch-applied — each is presented with its evidence and approved per dependency. Never batch-remove.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | license-conflict with the project's declared license; phantom-dependency on a production code path — one transitive-graph change breaks the build; dependency-confusion (a first-party/internal-intended name — one the project owns or builds — resolving from a public registry with no scope pin, a silent malicious substitution); a typosquat-risk confirmed to be the known-malicious twin |
| High | manifest-lockfile-drift (manifest/lockfile disagreement, or missing lockfile in an application); runtime dependency declared dev-only (absent from production installs); unused production dependency; install-script on a floating/unpinned dependency (the script can change under you); integrity-gap on a production dependency; typosquat-risk near-miss to a popular package (unconfirmed) |
| Medium | duplicate-dependency; unmaintained-upstream proven by metadata; dev/build tool declared as production; phantom-dependency on a dev/test-only path; install-script on a fully pinned, integrity-verified, reputable dependency (a native build) |
| Low | unused dev dependency; heavyweight-dependency |
| Advisory | Deprecated upstream whose own metadata names a drop-in replacement; capability overlap that exists only in transitive graphs; missing lockfile in a published library that ships version ranges; install-script on a first-party or workspace-local package |

## Fix strategy

**Auto-applicable:**

- Regenerate a drifted lockfile with the ecosystem's lockfile-only command (`npm install --package-lock-only`, `uv lock`, `cargo generate-lockfile`)
- Move a misclassified dependency between sections at its current version
- Declare a phantom dependency in the manifest at its currently locked version

**Requires explicit approval per dependency (removals are behavior-affecting):**

- Removing any dependency — present the package, the negative-scan evidence, and the exact removal command, then wait for approval before touching the manifest
- Replacing a heavyweight dependency with local code — include the exact replacement code in the finding
- Consolidating duplicates onto one package — touches every usage site
- Remediating a supply-chain finding — scoping and registry-pinning a confusion-prone name, replacing a typosquat with its intended package, or disabling a lifecycle script (`ignore-scripts`, an allowlist) — each is behavior-affecting and presented per dependency with its evidence before any manifest, lockfile, or `.npmrc` edit. A confirmed dependency-confusion or malicious typosquat also warrants a note that the installing host may be compromised — flag it; do not silently "fix and move on"

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

**"While I'm here, this version has a CVE — I'll file that too."** A *version's* known vulnerability is `/nitpicker security`'s surface — route it there in one line. But the install/namespace/integrity **surface** (install-script, dependency-confusion, typosquat-risk, integrity-gap) is a structural property of the declared set and is filed *here*, not routed away. The split is per-version-advisory (security) vs. structural-attack-surface (deps).

**"Install scripts are normal — every native module has one, skip it."** A lifecycle script runs arbitrary code on every install, CI job, and contributor machine. Normal is not safe: file install-script for every dependency that carries one, and let severity (pinned-and-reputable vs. floating) reflect the risk. Never omit it because install scripts are common.

**"It's our internal package, npm won't pull a public one."** An unscoped internal name with no `.npmrc` scope binding resolves from whatever public registry has published that name — the lockfile `resolved` URL pointing at the public registry is the proof of an active confusion vector, not a reassurance. File dependency-confusion on the name + public-resolution + absent-pin evidence. The mirror error is filing it on every public dependency: `express` and `lodash` are legitimately third-party, not confusion — the class is only for a name the project itself owns or builds.

**"The lockfile has integrity hashes, so the tree is verified."** An entry `resolved` from a git URL, a personal fork, or an arbitrary tarball carries **no** registry integrity and can be force-pushed or swapped without detection. Read every entry's `resolved` source, not just whether some entries have an `integrity` field.

**"That package name is just unfamiliar, it's probably fine."** Unfamiliar alone is never a finding — and never a dismissal. File typosquat-risk only on a concrete near-miss to a materially more popular twin (cite both names and the edit distance); but a near-miss is never waved off as "probably fine" because the name looked plausible.
