# config-auditor

Hostile single-shot application/runtime configuration audit. Assumes every config value read by code is undocumented, unvalidated, and defaulted to a dev-safe-but-prod-dangerous value until the code and its declared config sources prove otherwise. Hunts seven defect classes — undocumented config, missing startup validation, unsafe defaults, config drift, secrets committed in config, type-coercion traps, and hardcoded environment values. Cross-references every code read against every declared source of truth — `.env.example`, config schema, README/docs, in-code defaults. Speculation is banned: a var declared in `.env.example` but read by nothing is dead config, not a required-but-undocumented finding; a value with a genuinely safe default and full documentation is not a finding at all. Static analysis only; never adds a dependency.

## When to Use

- "audit the configuration" / "check env vars" / "find undocumented config" / "is this config validated" / "config drift"
- Before a release, a new deployment target, or an environment migration
- After adding a config-reading code path — a new env var, a new setting, a new feature flag
- When config sources have diverged and you need to know which is authoritative

**When NOT to use:**
- Whether an unsafe default or committed secret is exploitable → use [security-auditor]
- CI/pipeline environment and workflow secrets → use [ci-auditor]
- Whether config errors are logged or observable → use [observability-auditor]
- Whole-repo defect audit → use [nitpicker]

A value with a genuinely safe default and full documentation is not a finding — do not route it, drop it.

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Every config value read by code (env var reads via `getenv`/`process.env`/`os.environ`/framework accessors, config-file key reads, feature-flag lookups); every declared source of truth (`.env.example`, config schema, README/docs, in-code defaults); the project's config loader/validator (dotenv, pydantic-settings, zod, envalid, joi, convict, framework config layers) |
| **Writes** | `docs/audit/config-auditor-findings.md` |

## How to Invoke

```
/config-auditor
```

## Defect Classes

| Class | Definition |
|-------|------------|
| **undocumented-config** | An env var or config key read by code but absent from the documented config surface (`.env.example`, schema, README/docs) so an operator cannot know to set it |
| **missing-validation** | Config consumed with no startup validation, so the app boots and fails later on first use (required var read as empty, an int left unparsed, a URL unchecked) |
| **unsafe-default** | A default convenient in dev but dangerous in prod applied when the var is unset — `debug=true`, CORS `*`, insecure cookie, `0.0.0.0` bind, verbose error pages, auth disabled |
| **config-drift** | Divergence between sources for the same setting — `.env.example` vs in-code default vs docs vs schema disagree on name, default, or type |
| **secret-in-config** | A real (live-looking) secret committed in a tracked config file, default value, or sample |
| **type-coercion-trap** | An env var (always a string) used as bool/int/list without correct coercion — `if os.getenv("FLAG")` truthy on the string `"false"`, the string `"0"` truthy |
| **hardcoded-environment-value** | An environment-specific value (URL, hostname, path, bucket, region, port) hardcoded in source instead of config, breaking portability across environments |

## Process

```
0. Re-validate existing findings against current code
1. Enumerate the config surface — every value READ by code cross-referenced against every DECLARED source of truth
2. Identify the config loader and validation library (probe first, never install)
3. Hunt every defect class on every config value — confirm actually read, no existing validation/coercion/safe-default/docs neutralizes it, name the gap or wrong input
4. File findings: CFG-NNN, class, read site, source-of-truth gap or wrong input, consequence, concrete fix
5. Write docs/audit/config-auditor-findings.md
6. Ask: "Apply fixes? (a)ll auto-applicable (c)ritical-and-high only (n)o"
7. Ask: "Commit findings to git? (y/n)" — never commit silently
```

A source of truth left unread is recorded as an `Unexamined:` Summary bullet naming a concrete blocker.

## Findings Format

```
#### [CFG-NNN] Short title
Status: Open
Class: <undocumented-config|missing-validation|unsafe-default|config-drift|secret-in-config|type-coercion-trap|hardcoded-environment-value>
Read site: <file:line — the code that reads the value, and how it is used>
Gap: <the source-of-truth gap or wrong input — which source it is missing from, which sources disagree, the prod posture, or the string that coerces wrong>
Impact: <the consequence — deferred failure, insecure prod posture, portability break>
Fix: <the concrete change — add to .env.example with a safe placeholder, add startup validation, flip to a safe default, reconcile the drift, fix the coercion>
```

Finding ID format: `CFG-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | An unsafe default that ships an insecure production posture when a var is unset (auth disabled, `debug=true`, CORS `*`, bind `0.0.0.0` on a sensitive service); a live secret committed in a tracked config file |
| High | Required config with no startup validation that fails in production on first request; a type-coercion trap on a security or money flag (a `"false"` that reads truthy) |
| Medium | An undocumented config var an operator must set; config drift on a default or type between two sources of truth |
| Low | A hardcoded environment value on a service with a single deployment target today; an undocumented optional var with a genuinely safe default |
| Advisory | Cosmetic naming drift between doc and code with identical semantics; dead config declared but never read |

## Fix Strategy

Auto-applicable fixes (approval-gated via the step 6 prompt) add a missing var to `.env.example` or the schema with a SAFE placeholder, add startup validation using the project's existing validation library, reconcile a drifted default to the authoritative source, or fix a truthy-string coercion using the existing loader. Flipping an unsafe default to a safe one, or moving a hardcoded environment value into config, each require explicit per-change approval — both change runtime or deployment behavior. Never write a real secret into a sample (a real secret in a sample is itself the defect), never remove a config var that code still reads, and never add a config/validation dependency.

## Related Skills

- [security-auditor] — exploitability of an unsafe default or committed secret routed there
- [ci-auditor] — CI/pipeline environment and workflow secrets routed there
- [observability-auditor] — whether config errors are logged/observable routed there
- [nitpicker] — invokes this skill in `config` mode

---

[security-auditor]: ../security-auditor/README.md
[ci-auditor]: ../ci-auditor/README.md
[observability-auditor]: ../observability-auditor/README.md
[nitpicker]: ../nitpicker/README.md
