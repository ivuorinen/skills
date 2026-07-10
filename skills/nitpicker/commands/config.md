# /nitpicker config — Config Auditor

Hostile single-shot application/runtime configuration audit: cross-reference every config value read by code against every declared source of truth and hunt undocumented config, missing validation, unsafe prod defaults, config drift, committed secrets, type-coercion traps, and hardcoded environment values.

## When to use

- "config audit", "audit configuration", "check env vars", "find undocumented config", "config drift", "is this config validated"
- Before a release, a new deployment target, or an environment migration
- After adding a config-reading code path — a new env var, setting, or feature flag
- When config sources have diverged and you need to know which is authoritative

Run standalone or by the `/nitpicker` default audit flow.

**Not this command:** whether an unsafe default or committed secret is _exploitable_ → `/nitpicker security` (this command owns that it is mis-configured, undocumented, or drifted; security owns the exploit). CI/pipeline environment and workflow secrets → `/nitpicker ci`. Whether config errors are logged or observable → `/nitpicker observability`. Whole-repo defect audit → `/nitpicker audit`. A value with a genuinely safe default and full documentation is not a finding — do not route it, drop it.

## Mindset

Assume every config value read by code is undocumented, unvalidated, and defaulted to a dev-safe-but-prod-dangerous value until the code and its declared config sources prove otherwise. Speculation is banned: a var declared in `.env.example` but read by nothing is dead config (at most Advisory), never a required-but-undocumented finding. Static analysis only; never add a dependency.

## Defect classes

File a finding only when the config value is actually read by code AND the specific source-of-truth gap or wrong input is named. No read site, no gap named — no finding.

| Class                           | What to hunt                                                                                                                                                                             | Evidence to construct                                                                                                |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **undocumented-config**         | An env var or config key read by code but absent from the documented config surface (`.env.example`, config schema, README/docs) so an operator cannot know to set it                    | The read site, the source(s) of truth it is missing from, and the fix — add it with a safe placeholder               |
| **missing-validation**          | Config consumed with no startup validation, so the app boots and fails later on first use (required var read as empty, an int left unparsed, a URL unchecked)                            | The read site, the absent fail-fast check, the deferred failure it causes, and the startup-validation fix            |
| **unsafe-default**              | A default convenient in dev but dangerous in prod applied when the var is unset — `debug=true`, permissive CORS `*`, insecure cookie, `0.0.0.0` bind, verbose error pages, auth disabled | The default site, the prod posture it ships when unset, and the safe-default fix                                     |
| **config-drift**                | Divergence between sources for the same setting — `.env.example` vs in-code default vs docs vs schema disagree on name, default, or type                                                 | The two+ disagreeing sources quoted, which is authoritative, and the reconciliation fix                              |
| **secret-in-config**            | A real (live-looking) secret committed in a tracked config file, default value, or sample                                                                                                | The file+key, why it is a real secret not a placeholder, and the fix — remove from tracking / move to a secret store |
| **type-coercion-trap**          | An env var (always a string) used as bool/int/list without correct coercion — `if os.getenv("FLAG")` truthy on the string `"false"`, the string `"0"` truthy                             | The read+use site, the input that coerces wrong, and the correct-coercion fix                                        |
| **hardcoded-environment-value** | An environment-specific value (URL, hostname, path, bucket, region, port) hardcoded in source instead of config, breaking portability across environments                                | The hardcoded value, the environment it breaks in, and the move-to-config fix                                        |

## Process

1. **Enumerate the config surface.** Build two lists and cross-reference them:
   - Every config value READ by code: env var reads (`getenv`, `process.env`, `os.environ`, framework accessors), config-file key reads, feature-flag lookups. For each, name the read site (file:line) and how the value is used (bool, int, URL, secret).
   - Every DECLARED source of truth: `.env.example`, config schema (settings class, JSON/YAML schema, typed config), README/docs config sections, in-code defaults. Quote what each declares — name, default, type.

   A read site with no matching declaration, or a value whose declarations disagree, is a candidate. A source of truth left unread is recorded in the response summary as unexamined, naming a concrete blocker (generated/unreadable config, missing source, no access) — effort savings is not a blocker, and a silently skipped source is a defect in the audit itself.

2. **Identify the config loader and validation library — never install.** Probe the manifest and imports for what the project already uses: env loaders (dotenv, python-dotenv, viper), typed config/validation (pydantic-settings, zod, envalid, joi, convict), framework config layers (Django settings, Rails credentials, Spring `@ConfigurationProperties`). Report what is available in the summary. Absent tools stay absent — every fix uses the loader/validator the project already has.
3. **Hunt every defect class on every config value.** For each candidate:
   - Confirm the value is actually read by code — trace the read site. Dead config in a sample file is not an undocumented-config finding.
   - Read the actual read+use site — verify no existing validation, coercion, safe default, or documentation already neutralizes it. "Probably validated" and "probably documented in the schema" are both banned; the read site and the sources decide.
   - Name the specific gap or wrong input: which source of truth it is missing from, which sources disagree and how, the prod posture the default ships, or the string input that coerces wrong.
   - A candidate failing any of these is dropped. It is not a finding.
4. **File findings** via the store protocol in `_conventions.md`, using `--auditor config`. `## Evidence` names the class, the read site (file:line), and the source-of-truth gap or wrong input; `## Impact` the consequence (deferred failure, insecure prod posture, portability break); `## Fix` the concrete change. Then follow the shared run protocol: summary (include loader/validator available and unexamined sources), apply-fixes prompt, commit gate.

## Severity guide

| Severity | Condition                                                                                                                                                                                                        |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Critical | An unsafe default that ships an insecure production posture when a var is unset (auth disabled, `debug=true`, CORS `*`, bind `0.0.0.0` on a sensitive service); a live secret committed in a tracked config file |
| High     | Required config with no startup validation that fails in production on first request; a type-coercion trap on a security or money flag (a `"false"` that reads truthy)                                           |
| Medium   | An undocumented config var an operator must set; config drift on a default or type between two sources of truth                                                                                                  |
| Low      | A hardcoded environment value on a service with a single deployment target today; an undocumented optional var with a genuinely safe default                                                                     |
| Advisory | Cosmetic naming drift between doc and code with identical semantics; dead config declared but never read                                                                                                         |

## Fix strategy

**Auto-applicable (through the apply-fixes prompt):**

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

## Common mistakes

These rationalizations are forbidden:

- **"This var has a default, so it's fine."** A dev-safe default that is prod-dangerous is exactly the unsafe-default finding. Check the prod posture the default ships when the var is unset — `debug=true`, CORS `*`, and `0.0.0.0` all have defaults, and every one is a Critical.
- **"It's documented in a code comment."** An operator reads `.env.example`, the schema, and the docs — not the source. If it is not in a source of truth an operator consults, it is undocumented.
- **"I'll put the real value in `.env.example` so it just works."** Never. Sample files carry placeholders only. A real secret in a sample is the secret-in-config defect — filing a fix that commits one is committing the defect you are auditing for.
- **"The app runs, so the config is validated."** Booting is not validating. A required var read as empty that fails on the first request is unvalidated — it passed startup and deferred the failure to production.
- **"`if os.getenv('FLAG')` reads the boolean."** Env vars are strings. `"false"`, `"0"`, and `"no"` are all truthy strings — the flag reads on when the operator set it off. On a security or money flag that is High.
- **"This permissive CORS is a security issue, so I'll skip it."** File it as a misconfiguration and route the exploitability to `/nitpicker security`. You own that it is mis-configured; security owns the exploit.
- **"This secret belongs to CI, so it's not mine."** Decide by where it is read. CI pipeline/workflow env is `/nitpicker ci`'s. A secret read by application or runtime config is yours. The file it lives in does not decide — the code that consumes it does.
- **"I'll flip the unsafe default to safe while I'm here."** Flipping a default is a runtime behavior change and is approval-gated per change. A quiet flip is a correctness change wearing a config hat.
