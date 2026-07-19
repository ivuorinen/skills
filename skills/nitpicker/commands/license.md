# /nitpicker license — License & Legal-Compliance Audit

Hostile audit of the project's licensing surface: assume the project has no license, its dependencies are copyleft or unlicensed, and its bundled assets are unattributed until each is proven otherwise. A shipped product with a license defect is a legal liability, not a lint warning.

## When to use

- Auditing a repo's own license, its dependency licenses, SPDX headers, and attribution/NOTICE obligations before shipping or open-sourcing
- A dependency was added and you need to confirm its license is compatible with the project's and does not impose obligations the project cannot meet
- Before a release, relicense, or acquisition, to prove the license chain is clean
- When asked to "audit the licenses", "check license compatibility", "is this dependency's license OK", "are we GPL-contaminated", or "check attribution"

Out of scope: dependency health beyond licensing (unused, outdated, CVEs) routes to `/nitpicker deps`; committed secrets and credentials to `/nitpicker security` or `/nitpicker config`. This lens is almost never fully N/A — even a private, non-distributed repo needs its own license declared and its dependency obligations understood — but a repo with no declared license, no dependencies, and no bundled third-party assets gets the verdict "no third-party license surface; project itself is unlicensed" (which is itself a finding).

## Process

1. **Establish the project's own license.** Read the `LICENSE`/`LICENSE.md`/`COPYING` file and the `license`/`licenses` field in every manifest (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod` + `LICENSE`, `composer.json`, `*.csproj`, `pom.xml`, `Gemfile`/`.gemspec`). Record the declared license as an SPDX identifier. A repo with source but no license is "all rights reserved" by default — legally unusable by anyone, an immediate finding.
2. **Run installed license scanners.** Probe with `command -v` for `licensee`, `reuse`, `scancode`, `askalono`, `license-checker`, `pip-licenses`, `go-licenses`, `cargo-deny`/`cargo-license`. Run each tool found (`reuse lint`; `pip-licenses --format=json`; `license-checker --json`; `cargo deny check licenses`); record a missing tool as "not available" and a crashed one as "errored: <message>" — a failure never aborts the run. Never install a tool. Parse output into the dependency-license inventory; a dependency the tool reports as `UNKNOWN`/`UNLICENSED`/empty is not "probably fine" — it is an unlicensed-dependency finding until a license is confirmed from its source.
3. **Build the dependency-license inventory.** For every declared dependency (production and, where they ship or are distributed, dev/build), resolve its full SPDX license expression from the tool output cross-checked against the dependency's own `LICENSE`/manifest — the manifest field and the actual file disagree often enough that the file wins, and a disjunction (`A OR B`) or `WITH <exception>` clause is preserved verbatim, never collapsed to one arm. Resolve the license of the exact pinned/locked version from that version's own `LICENSE`, never the latest — a dependency that relicensed between versions (Redis/Terraform/Elastic/MongoDB → SSPL/BSL/RSAL, or the reverse) carries the license of the version actually vendored, and an upgrade can silently cross into a more restrictive license. Transitive dependencies count: a permissive direct dependency pulling a copyleft transitive one contaminates the same. Record every dependency whose license could not be resolved.
4. **Check compatibility and obligations against the project's license and distribution model.** For each dependency license, decide whether it is compatible with the project's declared license and whether the project meets its obligations. Direction matters: a copyleft (GPL/AGPL/LGPL) or source-available (SSPL/BSL/Commons Clause) license flowing _into_ a permissively-licensed or proprietary distributed product is contamination; the same license in an internal, non-distributed tool may impose no obligation. AGPL is the exception: its network-interaction clause makes offering the software over a network a distribution trigger, so an internal service reachable over a network is not a no-distribution basis for an AGPL dependency — file it at distribution severity, not the internal-tool Medium. LGPL obligations turn on linkage: dynamic linking against a replaceable LGPL library is permitted for a proprietary product; static linking or inlining triggers the relinking/source-availability obligation — record which linkage the project uses before assigning severity. Attribution licenses (MIT/BSD/Apache-2.0) require preserving copyright notices and, for Apache-2.0, a `NOTICE` file.
5. **File findings** via the store protocol in `_conventions.md`, using `--auditor license`. Each finding records the class, the SPDX identifiers involved, Evidence (the dependency + its resolved license + the manifest/file it came from, and the project license it conflicts with), Impact (the concrete legal exposure: a copyleft source-disclosure obligation, an unusable UNKNOWN license, a missing required attribution), and Fix (the exact action: replace the dependency, add the NOTICE entry, add the SPDX header, declare the project license). State the reasoning; never assert a compatibility verdict as settled legal advice — flag it and name the obligation.
6. **Summarize and fix.** The summary states the run verdict (COMPLETE only if every dependency's license was resolved or filed as UNKNOWN, and the project's own license established), tool coverage, and counts by class. Fix application and the commit gate follow `_conventions.md`, with this override: replacing or removing a dependency to resolve a contamination finding requires explicit approval per change; adding a missing `LICENSE`/`NOTICE`/SPDX header is additive and batch-applicable. After each fix, re-check the cited location and re-run the scanner.

### Defect classes

| Class | What to flag | Fix shape |
| --- | --- | --- |
| **missing-project-license** | Source in a repo with no `LICENSE`/`COPYING` file and no manifest `license` field — legally "all rights reserved", unusable by others; or a public repo whose intended license is undeclared | Add a `LICENSE` file and set the manifest `license` SPDX field to match; for a private repo, declare the intended terms |
| **license-mismatch** | The `LICENSE` file and the manifest `license` field name different licenses; the README/site claims a license the repo does not carry | Reconcile to one SPDX identifier across the file, every manifest, and the docs; the `LICENSE` file text is authoritative |
| **copyleft-contamination** | A GPL/AGPL/LGPL (or SSPL/BSL/Commons Clause source-available) dependency — direct or transitive — linked into a permissively-licensed or proprietary distributed product | Replace with a permissively-licensed equivalent; or comply (open-source the derivative under the copyleft terms); isolate via a process boundary where the license permits |
| **incompatible-license** | A dependency license that cannot legally combine with the project's declared license (e.g. Apache-2.0 code into a GPLv2-only project; a proprietary dependency in an MIT release) | Replace the dependency, or change the project license to one compatible with every dependency in the chain |
| **version-license-drift** | A pinned dependency whose license differs from the version the inventory was resolved against, or a pending upgrade that crosses a permissive→source-available/copyleft relicense boundary (Redis/Terraform/Elastic/MongoDB → SSPL/BSL/RSAL) | Resolve the license from the pinned version's `LICENSE`; pin below the relicense boundary or accept the new terms explicitly; flag any upgrade that crosses it |
| **dual-license-or-exception** | A dependency offered under a disjunctive license (`A OR B`) resolved to a single arm with no record of the chosen arm, or a copyleft license carrying a linking/usage exception (Classpath, GCC runtime, LGPL) flagged as plain copyleft-contamination | Record the full SPDX expression; for a disjunction, record and comply with the chosen arm; evaluate obligations under the exception, not the base license |
| **unlicensed-dependency** | A dependency whose license the scanner and its source resolve to `UNKNOWN`/`UNLICENSED`/empty — no grant of rights, so no legal permission to use it | Confirm the license from the upstream repo; if none exists, remove the dependency or obtain a written grant |
| **missing-attribution** | An MIT/BSD/Apache-2.0 (or similar attribution) dependency whose copyright notice is not preserved in the distribution; a bundled/vendored source file with its license header stripped; Apache-2.0 deps with no `NOTICE` file | Preserve each dependency's license text and copyright in a bundled `THIRD_PARTY_LICENSES`/`NOTICE`; restore stripped headers |
| **restrictive-use-clause** | A dependency under a non-commercial (CC-BY-NC), field-of-use-restricted, or "no competing service" license (SSPL, BSL, Commons Clause, Elastic License) that the project's actual use violates | Replace with a dependency whose license permits the project's use; or confirm the specific use falls within the license grant |
| **patent-grant-conflict** | A distributed product whose terms or patent posture forfeit a dependency's patent grant (Apache-2.0 §3, GPLv3, MPL-2.0 retaliation clauses), or a patent-sensitive product relying on a permissive dep that conveys no patent grant, with the exposure unrecorded | Record each dependency's patent-grant and retaliation terms; flag combinations where the project forfeits or lacks a required grant |
| **unverified-code-provenance** | Vendored or inlined third-party source (Stack Overflow snippet under CC-BY-SA, LLM-generated block, copied file) with no recorded license or origin; inbound contributions with no DCO/CLA establishing the inbound license | Record the origin and license of every copied snippet; require DCO/CLA so the project's own grant rests on a licensed inbound chain |
| **missing-spdx-header** | Source files lacking an `SPDX-License-Identifier:` header where the project declares REUSE/SPDX compliance or a policy requires per-file headers (`reuse lint` fails) | Add `SPDX-License-Identifier: <id>` (and `SPDX-FileCopyrightText:`) to each file, or drop the compliance claim if unintended |
| **bundled-asset-license** | A vendored font, image, icon set, dataset, or code snippet with a restrictive or unstated license, treated as freely usable | Confirm and record each asset's license and attribution; replace assets whose license the project cannot meet |

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | A distributed product with copyleft-contamination forcing source disclosure it does not make; an unlicensed-dependency or restrictive-use-clause violation shipping in a release — active legal exposure |
| High | Incompatible-license in a shipped dependency chain; a proprietary/source-available dependency in a repo released as open source; missing-project-license on a public repo intended to be used |
| Medium | Missing required attribution / `NOTICE` for attribution-licensed dependencies; license-mismatch between file and manifest; a copyleft dependency in an internal tool where a no-distribution basis is stated but not yet verified (an unstated basis is a High copyleft-contamination finding, not Medium) |
| Low | Missing SPDX headers where REUSE compliance is claimed; an UNKNOWN license on a dev-only, non-distributed dependency; a bundled asset whose permissive license is unrecorded |
| Advisory | A license-policy hardening with no current violation (adding SPDX headers where none are required); a permissive dependency whose attribution is present but not centralized |

## Fix strategy

**Auto-applicable:**

- Add a `LICENSE` file and set the manifest `license` SPDX field to match the intended license
- Reconcile a file/manifest license-mismatch to one identifier
- Add or complete a `NOTICE`/`THIRD_PARTY_LICENSES` file from the resolved dependency inventory
- Add `SPDX-License-Identifier` headers where REUSE compliance is declared

**Requires explicit approval per change:**

- Replacing or removing a dependency to resolve contamination, incompatibility, or a restrictive-use clause
- Changing the project's own declared license (a decision with contributor and downstream implications)
- Restoring or rewriting a stripped license header in vendored code

**Never auto-apply:**

- Choosing a license for a repo that has none — surface the options and their implications; the owner decides
- Asserting a compatibility verdict as settled legal advice — flag the obligation and recommend counsel for a genuinely contested combination
- Deleting a `LICENSE`/`NOTICE` file or a license header to make a scanner pass

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

**"It's MIT/permissive, so there are no obligations."** Every permissive license carries an attribution obligation: the copyright notice and license text must travel with the distribution. A shipped product that drops them is in violation of the most permissive licenses too. Confirm attribution is preserved, not just that the license is permissive.

**"The `package.json` says MIT, so it's MIT."** The manifest field is a claim; the `LICENSE` file is the grant. They disagree often — a fork keeps the original file, a template leaves a stale field. Resolve from the actual license file; the field that contradicts it is a license-mismatch finding.

**"It's a dev/build dependency, so its license doesn't matter."** A dev dependency whose output or code ships (a bundler that inlines a runtime, a codegen tool that emits licensed templates, a vendored build script) carries its license into the product. Only a tool that touches neither the distributed artifact nor its source is out of scope, and that is proven, not assumed.

**"The GPL dependency is only transitive, we didn't choose it."** Copyleft flows through the whole dependency graph regardless of who added it; a permissive direct dependency pulling a GPL transitive one contaminates the derivative exactly the same. Trace the transitive chain; file it at the distribution model's severity.

**"The scanner reported UNKNOWN, so I'll assume it's permissive."** UNKNOWN is the absence of a grant of rights — the opposite of permission. An unlicensed dependency conveys no right to use, copy, or distribute it. Confirm the license from upstream or file it; never default UNKNOWN to safe.

**"It's an internal tool, licenses don't apply."** Copyleft obligations attach on _distribution_, but "internal" is a claim about the distribution model that must hold — an internal tool that is later shipped, offered as a network service (triggering AGPL), or open-sourced carries every obligation forward. State the no-distribution basis; do not assume it.

**"The license combination is probably fine."** "Probably" is not a compatibility verdict. Name the two licenses, name the obligation each imposes, and state whether the combination meets it — or flag it as contested and recommend counsel. A hand-waved "fine" is silence, and silence on a license conflict is approval of the exposure.

**"I noted the license issue, so it's handled."** A described issue is an open finding. A finding is resolved only after the dependency is replaced, the `NOTICE`/header added, or the license declared — and the scanner re-run to confirm.
