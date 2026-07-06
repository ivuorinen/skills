---
name: config-auditor
description: 'Hostile single-shot application/runtime configuration audit — cross-references every env var and config key read by code against every source of truth (`.env.example`, config schema, docs, in-code defaults) to hunt undocumented config, missing validation, unsafe defaults, config drift, committed secrets, type-coercion traps, and hardcoded environment values, each finding naming the read site, the source-of-truth gap, and a concrete fix. Use when auditing a codebase for configuration defects, checking whether env vars are documented and validated, or verifying config sources agree. Triggers: "config audit", "audit configuration", "check env vars", "find undocumented config", "config drift", "run config-auditor".'
---

# Config Auditor

## Overview

Hostile single-shot application/runtime configuration audit. Assume every config value read by code is undocumented, unvalidated, and defaulted to a dev-safe-but-prod-dangerous value until the code and its declared config sources prove otherwise. Hunt seven defect classes — undocumented config, missing startup validation, unsafe defaults, config drift, secrets committed in config, type-coercion traps, and hardcoded environment values — and file each with the exact read site, the source-of-truth gap (or wrong input), and a concrete fix. Speculation is banned: a var declared in `.env.example` but read by nothing is dead config, not a required-but-undocumented finding; a value with a genuinely safe default and full documentation is not a finding at all. Cross-references every code read against every declared source of truth — `.env.example`, config schema, README/docs, in-code defaults. Static analysis only; never adds a dependency. All findings are graded Critical → Advisory and written to `docs/audit/config-auditor-findings.md`.

## When to Use

- Auditing a codebase for configuration defects before a release, a new deployment target, or an environment migration
- When asked to "audit the configuration", "check env vars", "find undocumented config", "is this config validated", or "run a config audit"
- After adding a config-reading code path — a new env var, a new setting, a new feature flag
- When config sources have diverged and you need to know which is authoritative

**When NOT to use:** whether an unsafe default or committed secret is *exploitable* → `security-auditor` (you own that it is mis-configured, undocumented, or drifted; security owns the exploit). CI/pipeline environment and workflow secrets → `ci-auditor` (you own application/runtime config). Whether config errors are logged or observable → `observability-auditor`. Whole-repo defect audit → `nitpicker`. A value with a genuinely safe default and full documentation is not a finding — do not route it, drop it.

## Defect Classes

File a finding only when the config value is actually read by code AND the specific source-of-truth gap or wrong input is named. A var that appears in `.env.example` but is read by nothing is dead config — at most Advisory, never a required-but-undocumented finding. A value with a genuinely safe default and complete documentation across every source is not a finding. No read site, no gap named — no finding.

| Class | What to hunt | Evidence to construct |
|-------|--------------|------------------------|
| **undocumented-config** | An env var or config key read by code but absent from the documented config surface (`.env.example`, config schema, README/docs) so an operator cannot know to set it | The read site, the source(s) of truth it is missing from, and the fix — add it with a safe placeholder |
| **missing-validation** | Config consumed with no startup validation, so the app boots and fails later on first use (required var read as empty, an int left unparsed, a URL unchecked) | The read site, the absent fail-fast check, the deferred failure it causes, and the startup-validation fix |
| **unsafe-default** | A default convenient in dev but dangerous in prod applied when the var is unset — `debug=true`, permissive CORS `*`, insecure cookie, `0.0.0.0` bind, verbose error pages, auth disabled | The default site, the prod posture it ships when unset, and the safe-default fix |
| **config-drift** | Divergence between sources for the same setting — `.env.example` vs in-code default vs docs vs schema disagree on name, default, or type | The two+ disagreeing sources quoted, which is authoritative, and the reconciliation fix |
| **secret-in-config** | A real (live-looking) secret committed in a tracked config file, default value, or sample | The file+key, why it is a real secret not a placeholder, and the fix — remove from tracking / move to a secret store |
| **type-coercion-trap** | An env var (always a string) used as bool/int/list without correct coercion — `if os.getenv("FLAG")` truthy on the string `"false"`, the string `"0"` truthy | The read+use site, the input that coerces wrong, and the correct-coercion fix |
| **hardcoded-environment-value** | An environment-specific value (URL, hostname, path, bucket, region, port) hardcoded in source instead of config, breaking portability across environments | The hardcoded value, the environment it breaks in, and the move-to-config fix |

## Process

```
0. Re-validate existing findings
   If docs/audit/config-auditor-findings.md exists, re-check each finding with Status: Open
   against the current code:
   - Read site changed and the value is now documented/validated/safe, or the fix landed → Fixed (record date)
   - Finding was wrong (var is dead config, default is safe, source already agrees) → Invalid (record why)
   - Still present → leave Open. Never carry a finding forward without re-checking it.

1. Enumerate the config surface
   Build two lists and cross-reference them.
   a. Every config value READ by code: env var reads (getenv, process.env, os.environ,
      framework config accessors), config-file key reads, feature-flag lookups. For each,
      name the read site (file:line) and how the value is used (bool, int, URL, secret).
   b. Every DECLARED source of truth: .env.example, config schema (settings class, JSON/YAML
      schema, typed config), README/docs config sections, and in-code defaults. Quote what
      each declares — name, default, type.
   A read site with no matching declaration, or a value whose declarations disagree, is a
   candidate. A source of truth left unread is recorded as an `Unexamined:` Summary bullet
   naming a concrete blocker (generated/unreadable config, missing source, no access) —
   effort savings is not a blocker, and a silently skipped source is a defect in the audit
   itself.

2. Identify the config loader and validation library — never install
   Probe the manifest and imports for what the project already uses: env loaders (dotenv,
   python-dotenv, viper), typed config/validation (pydantic-settings, zod, envalid, joi,
   convict), and framework config layers (Django settings, Rails credentials, Spring
   @ConfigurationProperties). Record what is available in the Summary. Absent tools stay
   absent — every fix uses the loader/validator the project already has.

3. Hunt every defect class on every config value
   Work the Defect Classes table against the cross-reference from step 1. For each candidate:
   a. Confirm the value is actually read by code — trace the read site. Dead config in a
      sample file is not an undocumented-config finding.
   b. Read the actual read+use site — verify no existing validation, coercion, safe default,
      or documentation already neutralizes it. Read the getenv call, the default argument,
      the coercion, the schema entry. "Probably validated" and "probably documented in the
      schema" are both banned; the read site and the sources decide.
   c. Name the specific gap or wrong input: which source of truth it is missing from, which
      sources disagree and how, the prod posture the default ships, or the string input that
      coerces wrong.
   d. Candidate fails a, b, or c → drop it. It is not a finding.

4. File findings
   Assign the next CFG-NNN id. Record class, read site (file:line), the source-of-truth gap
   or wrong input, the consequence (deferred failure, prod posture, portability break), and
   the concrete fix.

5. Write docs/audit/config-auditor-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.

6. Present summary — finding counts by severity, config loader/validator available,
   unexamined sources — then ask: "Apply fixes? (a)ll auto-applicable  (c)ritical-and-high only  (n)o"
   Apply in severity order, Critical first. Only the Fix Strategy auto-applicable list is
   eligible through this prompt; every other fix stays a proposal in its finding and is
   applied only when the user approves that specific change by name.

7. Commit gate
   Fix edits are left in the working tree unstaged. Ask: "Commit findings to git? (y/n)" —
   on yes, stage only docs/audit/config-auditor-findings.md. Never commit silently.
```

## Findings Format

Output path: `docs/audit/config-auditor-findings.md`

```
# Config Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Config values read: N | Sources of truth examined: N | Unexamined: N
- Config loader / validator available: <comma-separated list, or none>
- Unexamined: <source of truth> — <why not examined>

## Open Findings

### Critical

#### [CFG-NNN] Short title
Status: Open
Class: <undocumented-config|missing-validation|unsafe-default|config-drift|secret-in-config|type-coercion-trap|hardcoded-environment-value>
Read site: <file:line — the code that reads the value, and how it is used>
Gap: <the source-of-truth gap or wrong input — which source it is missing from, which sources disagree, the prod posture, or the string that coerces wrong>
Impact: <the consequence — deferred failure, insecure prod posture, portability break>
Fix: <the concrete change — add to .env.example with a safe placeholder, add startup validation, flip to a safe default, reconcile the drift, fix the coercion>

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

#### [CFG-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <what changed, and the re-check showing the value is now documented/validated/safe>

## Invalid

### Pass N — YYYY-MM-DD

#### [CFG-NNN] Short title
Notes: <why the finding was wrong — dead config, safe default, sources already agree>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the other `## Summary` bullets after it. Keep the Total line in exactly that shape and insert no field into it. All supplementary bullets (`Config values read`, `Config loader / validator available`, `Unexamined:`) follow the Total line; unexamined sources of truth live as `Unexamined:` Summary bullets, never in a separate section. All fixed findings go under one `## Fixed` h2 and all invalid findings under one `## Invalid` h2, sub-divided by `### Pass N — YYYY-MM-DD` h3 headers — never `## Fixed — pass N` variants, never h2 → h4 without an h3.

The per-finding `Status:` field is `Open` for a verified, still-present finding; on moving a finding to Fixed or Invalid, drop the `Status:` line. Step 0 re-validation re-checks every finding with `Status: Open`. Finding ID format: `CFG-NNN` (zero-padded to 3 digits). Assign sequentially from the highest existing ID; never reuse an ID, even after Fixed or Invalid.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | An unsafe default that ships an insecure production posture when a var is unset (auth disabled, `debug=true`, CORS `*`, bind `0.0.0.0` on a sensitive service); a live secret committed in a tracked config file |
| High | Required config with no startup validation that fails in production on first request; a type-coercion trap on a security or money flag (a `"false"` that reads truthy) |
| Medium | An undocumented config var an operator must set; config drift on a default or type between two sources of truth |
| Low | A hardcoded environment value on a service with a single deployment target today; an undocumented optional var with a genuinely safe default |
| Advisory | Cosmetic naming drift between doc and code with identical semantics; dead config declared but never read |

## Fix Strategy

**Auto-applicable (ask first via the step 6 prompt, apply only on approval):**
- Add a missing var to `.env.example` or the config schema with a SAFE placeholder — never a real value
- Add startup validation using the project's existing config/validation library
- Reconcile a drifted default to match the documented or authoritative source
- Fix a truthy-string coercion using the project's existing config loader

**Requires explicit approval per change:**
- Flipping an unsafe default to a safe one — changes runtime behavior; name the behavior change in the finding
- Moving a hardcoded environment value into config — touches deployment and wiring

**Never:**
- Write a real secret into an example or sample file — placeholders only; a real secret in a sample is itself the defect
- Remove a config var that code still reads
- Add a config or validation dependency — the project's existing loader/validator or nothing
- Apply any fix before the step 6 prompt
- Commit anything silently

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"This var has a default, so it's fine."** A dev-safe default that is prod-dangerous is exactly the unsafe-default finding. Check the prod posture the default ships when the var is unset — `debug=true`, CORS `*`, and `0.0.0.0` all have defaults, and every one is a Critical.

**"It's documented in a code comment."** An operator reads `.env.example`, the schema, and the docs — not the source. A comment next to the getenv call is not the documented config surface. If it is not in a source of truth an operator consults, it is undocumented.

**"I'll put the real value in `.env.example` so it just works."** Never. Sample and example files carry placeholders only. A real secret in a sample is itself the secret-in-config defect — filing a fix that commits one is committing the defect you are auditing for.

**"The app runs, so the config is validated."** Booting is not validating. A required var read as empty that fails on the first request is unvalidated — it passed startup and deferred the failure to production. Missing startup validation is the finding regardless of whether the process is currently up.

**"`if os.getenv('FLAG')` reads the boolean."** Env vars are strings. `"false"`, `"0"`, and `"no"` are all truthy strings — the flag reads on when the operator set it off. That is the type-coercion-trap, and on a security or money flag it is High.

**"This permissive CORS is a security issue, so I'll skip it."** You file it as a misconfiguration and route the exploitability to `security-auditor`. Silence is approval — a config defect you noticed and did not file is one you accepted. You own that it is mis-configured; security owns the exploit.

**"This secret belongs to CI, so it's not mine."** Decide by where it is read. CI pipeline and workflow env is `ci-auditor`'s. A secret read by application or runtime config is yours. The file it lives in does not decide — the code that consumes it does.

**"I'll flip the unsafe default to safe while I'm here."** Flipping a default is a runtime behavior change and is approval-gated per change. Name the behavior change in the finding and wait for the user to approve that specific flip — a quiet flip is a correctness change wearing a config hat.

**"Last pass's findings are surely still valid — skip step 0."** Every `Status: Open` finding is re-checked against current code every run. Config moves; a var gets documented, a default gets fixed, a source gets reconciled. A stale Open finding sends the user chasing a fixed defect, and a silently-fixed one never reaches the Fixed ledger.

**"I'll apply the doc additions as I go."** No fix is applied before the step 6 summary and prompt — not even adding a var to `.env.example`. Fixes applied mid-hunt bypass the approval gate and contaminate re-validation.
