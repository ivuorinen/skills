# Audit Coverage Checklist

The default `audit` command (`commands/audit.md`) copies every task below
into the agent's task list at run start — in Claude Code one
`TaskCreate`/`TodoWrite` entry per task, the equivalent task tracker in
other agents. This list is the audit's coverage contract: `audit` is
"exhaustive" only when every task has been addressed.

Each task names the quality lens and the specialist command
(`commands/<command>.md`) that owns it. Together the tasks cover the full
review surface the skill offers.

## How audit uses this file

- Copy each task into your task list before reviewing anything, in the order
  listed.
- Apply each lens using its specialist command as the authority. Deep-run
  that command file when the lens is high-risk or the user named it as the
  focus; otherwise apply the lens inline.
- File findings via `findings.py` as they are confirmed. Findings from a
  deep-run specialist land under that command's auditor key; lenses applied
  inline land under `audit`.
- Close each task in exactly one state:
  1. **findings filed** — one or more findings recorded for the lens;
  2. **clean** — lens applied, nothing found (record it in the run summary);
  3. **N/A** — the surface the lens needs is absent, with a one-line reason.
- A task in none of those states is a silently skipped lens. Silence =
  approval: an unaddressed task is an accepted blind spot. Do not close the
  audit while any task is open, and list every task's outcome in the run
  summary.

## Base lenses (always applicable)

- **Correctness & logic** — wrong results, broken invariants, bad edge
  cases, off-by-one, unsafe assumptions.
- **Reliability & operational safety** — failure modes, retries, timeouts,
  idempotence, data-loss paths.
- **Maintainability & internal architecture** — dead code, duplication,
  tangled coupling, unclear ownership.
- **Conventions** — repo, language, and framework idioms; naming; layout.

## Specialist lenses (apply each; mark N/A only when the surface is absent)

- **Security** (`security`) — trust boundaries, injection, authn/z, secrets,
  unsafe deserialization. Run scanners where available.
- **Privacy** (`privacy`) — personal data stored or transmitted without the
  control its class requires. N/A when no identifiable personal-data surface
  exists.
- **Config** (`config`) — undocumented env vars, unsafe prod defaults,
  config drift, committed secrets, type-coercion traps.
- **Infrastructure-as-code** (`iac`) — container images, orchestration
  (Kubernetes, Compose, Helm), and cloud provisioning (Terraform,
  CloudFormation, Pulumi): root/privileged containers, open ingress, public
  data stores, unencrypted resources, overbroad IAM, unpinned base images,
  committed state/secrets. N/A when the repo has no IaC files.
- **Performance** (`perf`) — N+1 queries, O(n²)+ hotspots,
  sync-blocking-in-async, unbounded growth, missing pagination.
- **Concurrency** (`concurrency`) — races, TOCTOU, deadlock ordering, lost
  updates, unsafe publication, state corrupted across await. N/A for
  strictly single-threaded code with no async.
- **Error handling** (`errors`) — swallowed exceptions, fail-open defaults,
  overbroad catches, masking fallbacks, silent retries.
- **Resource leaks** (`leaks`) — acquire-without-guaranteed-release:
  handles, pools, listeners, tasks, temp artifacts.
- **Architecture** (`arch`) — violations against detected or declared
  patterns and layer boundaries. If `docs/audit/arch-profile.md` is absent,
  run `arch-profile` first to detect the pattern.
- **API contract** (`contract`) — declared public surface (specs, exports,
  published types, CLI flags) vs implementation vs the declared semver bump.
  N/A when no public contract surface exists.
- **Dependencies** (`deps`) — unused, phantom, duplicate, heavyweight,
  unmaintained, license-conflicting, drifted, misclassified dependencies.
- **Migrations** (`migrations`) — destructive ops, irreversible downs,
  long-lock operations, missing FK indexes, schema-model drift, unbatched
  data migrations, deploy-order breaks. N/A when the repo has no schema or
  data migrations.
- **Tests** (`tests`) — tautological tests, mocked-out subjects, flaky
  patterns, untracked skips, coverage holes on critical paths, and tests
  coupled to an external binary or environment the CI test step does not
  provision.
- **Docs** (`docs`) — documentation accuracy against the code: stale,
  missing, or wrong behavior descriptions.
- **CI/CD** (`ci`) — unpinned actions, over-broad token scope, script
  injection, privileged-trigger misuse, non-gating checks, masked failures.
  N/A when the repo has no CI/CD pipeline definitions.
- **Commits** (`commits`) — commit-message discipline against the actual
  diffs: type under/overstatement, unmarked breaking changes, malformed
  convention that mis-versions a release.
- **Observability** (`observability`) — dark paths, missing correlation IDs,
  level misuse, unfireable alerts, cardinality bombs, PII in logs. N/A for a
  library with no runtime signal surface.
- **Accessibility** (`a11y`) — WCAG 2.2 AA on the UI layer: keyboard
  reachability, roles and names, contrast, focus order. N/A when there is no
  UI layer.
- **Localization** (`i18n`) — hardcoded strings, locale-unsafe number, date,
  and sort handling against the declared locale scope. N/A when there is no
  localization surface and single-locale is the declared scope.
- **Complexity** (`complexity`) — over-engineering: speculative
  abstractions, reinvented standard library, dead flexibility, needless
  dependencies.
- **Unwired code** (`unwired`) — unwired and incomplete implementations that
  are defined but never reached.

## Agent-enforcement lenses (only when an agent project — `.claude/` exists)

- **Agent loopholes** (`agent-loopholes`) — bypassable or unenforced
  constraints in `.claude/rules`, hooks, settings, permissions, skills.
- **Agent hooks** (`agent-hooks`) — hook coverage against the project's
  evidence base; recurring failures no hook guards.
- **Agent rules** (`agent-rules`) — `.claude/rules/` quality; conventions
  that should be codified as rules.

## Not coverage lenses

`review` (the diff-scoped form of this same read), `pr`, `cr`, `plan`,
`baseline`, `release-gate`, `help`, and `x-findings-migrator` are workflow or
meta commands, not quality lenses — they are not tasks in this checklist.
