# dep-auditor

Hostile single-shot audit of dependency *health* beyond CVEs. Treats every manifest entry as dead weight until an actual usage is proven and every import as undeclared until a manifest names it. Cross-references three evidence legs — the manifest, the lockfile, and a full import/usage scan covering every reference form the ecosystem supports — and files findings for unused, phantom, duplicate, heavyweight, unmaintained, license-conflicting, drifted, and misclassified dependencies. Uses installed tools when present (`depcheck`, `deptry`, `npm ls`, `pip list`, `cargo tree`); never installs anything.

## When to Use

- "Audit dependencies" / "find unused dependencies" / "prune deps" / "check dependency health"
- Before a release, to prove the manifest matches what the code actually imports
- After a refactor or feature removal that changed what the code imports
- A dependency tree that has grown for years without an audit

**When NOT to use:**
- CVEs, vulnerable versions, secrets, supply-chain advisories → use [security-auditor]
- Whether a proposed NEW dependency is justified → use [complexity-hunter] (its ladder governs the decision before the add; dep-auditor audits what is already installed)
- General code defects → use [nitpicker]

## dep-auditor vs. security-auditor

| | dep-auditor | security-auditor |
|---|---|---|
| Question | "Is this dependency earning its place?" | "Is this dependency (or code) vulnerable?" |
| Input | Manifest + lockfile + full import/usage scan | Installed security scanners' output |
| Finds | Unused, phantom, duplicate, heavyweight, unmaintained, license-conflicting, drifted, misclassified deps | CVEs, secrets, SAST hits, IaC misconfigurations |
| Fix shape | Remove, declare, reclassify, consolidate (removals gated per dependency) | Upgrade, patch, redact, reconfigure |

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Every manifest (`package.json`, `pyproject.toml`, `requirements*.txt`, `Cargo.toml`, `go.mod`, `composer.json`, `Gemfile`) and its lockfile; the full source tree (every import form); config files that reference plugins/presets by name; `package.json` scripts, Makefiles, CI files; read-only registry metadata for maintenance/license status |
| **Writes** | `docs/audit/dep-auditor-findings.md` |

## How to Invoke

```
/dep-auditor
```

Inventories every manifest/lockfile pair, probes for installed dependency tools, builds the declared/locked/referenced sets, and cross-references them. Tool candidates (depcheck/deptry output) are verified against the full import-form scan before anything is filed.

## Defect Classes

| Class | Definition |
|-------|------------|
| **unused-dependency** | Declared, referenced by no import form, config plugin reference, script, or binary invocation |
| **phantom-dependency** | Imported but declared in no manifest — rides on a transitive |
| **duplicate-dependency** | Two or more declared packages covering the same capability |
| **heavyweight-dependency** | Only usage is one function replaceable by ten or fewer lines of stdlib/local code |
| **unmaintained-upstream** | Archived or formally deprecated — proven by fetched metadata, never inferred from release age |
| **license-conflict** | Dependency license incompatible with the project's declared license |
| **manifest-lockfile-drift** | Lockfile missing, stale, or disagreeing with the manifest |
| **misclassified-dependency** | Runtime dep declared dev-only, or dev/build tool declared as production |

## Process

```
0. Re-validate existing Status: Open findings against the current manifest/lockfile/scan
1. Inventory every manifest + lockfile pair and the project's declared license
2. Probe tools (which depcheck, deptry, npm, pip, cargo, ...) — run only what is installed
3. Build three sets per ecosystem: Declared, Locked, Referenced (full import-form scan)
4. Cross-reference; file findings per defect class — three evidence legs per finding
5. Check maintenance + license for every declared dependency via available metadata
6. Write docs/audit/dep-auditor-findings.md
7. Ask: "Apply fixes? (a)uto-applicable (s)afe only (n)o" — removals approved per dependency
8. Ask: "Commit findings to git? (y/n)" — never commit silently
```

A run is COMPLETE only when every declared dependency is examined against every class. Anything skipped (unreachable metadata, unparsed tree) becomes an `- Unexamined:` Summary bullet and forces verdict INCOMPLETE.

## Findings Format

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
```

Finding ID format: `DEP-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | License conflict with the project's declared license; phantom dependency on a production code path |
| High | Manifest/lockfile drift (missing lockfile in an application); runtime dep declared dev-only; unused production dependency |
| Medium | Duplicate dependency; metadata-proven unmaintained upstream; dev tool declared production; phantom on a dev/test path |
| Low | Unused dev dependency; heavyweight dependency |
| Advisory | Deprecated upstream with a named drop-in replacement; transitive-only overlap; missing lockfile in a published library |

## Related Skills

- [security-auditor] — CVEs, secrets, and vulnerable versions; dep-auditor files no CVE findings
- [complexity-hunter] — gates whether a NEW dependency should be added; dep-auditor audits what already is
- [nitpicker] — whole-repo defect audit across code, tests, docs, and config

---

[security-auditor]: ../security-auditor/README.md
[complexity-hunter]: ../complexity-hunter/README.md
[nitpicker]: ../nitpicker/README.md
