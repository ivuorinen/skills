# /nitpicker contributing — Contributor-Guide Audit

Hostile audit of `CONTRIBUTING.md`: every instruction in it is a claim to verify against the repo's actual tooling, and when the file is absent, offer to scaffold one from the conventions the repo already enforces — never invented, never silent.

## When to use

- As a companion check alongside any command that touches or changes the codebase — a change that alters setup, build, test, commit, or PR mechanics silently invalidates the contributor guide.
- Before a release, or when onboarding reveals the documented contributor process no longer works.
- When `CONTRIBUTING.md` is missing and the repo enforces any contributor-facing convention — a build system, a test runner, a commit convention, or a CI gate — so a contributor needs one.
- When asked to "audit CONTRIBUTING", "check the contributing guide", "is our contributor doc accurate", or "we have no CONTRIBUTING.md".

Boundary: broad documentation accuracy (READMEs, ADRs, docstrings) is `/nitpicker docs`; commit-message discipline against diffs is `/nitpicker commits`; CI-gate correctness is `/nitpicker ci`. This command owns exactly one file's existence and its accuracy against the contributor-facing tooling — and its creation when absent, which no other command does.

## Sources of truth

Every CONTRIBUTING section maps to a source the repo already contains. A claim is verified against its source; a section is generated only from its source. No source → the section is omitted, never guessed.

| Section | Source of truth |
| --- | --- |
| Development setup | `README`, `Makefile`, `package.json` scripts, language manifests (`pyproject.toml`, `go.mod`, `Cargo.toml`, `package.json`), `.tool-versions`/`.nvmrc`, `devcontainer.json`, `docker-compose.yml` |
| Build / run | `Makefile` targets, `package.json` scripts, CI build steps |
| Testing | test-runner config, the `test` target/script, CI test steps |
| Code style | linter/formatter configs (`.editorconfig`, `ruff`, `eslint`, `prettier`, `.pre-commit-config.yaml`) and any style rules in `CLAUDE.md`/`AGENTS.md` |
| Commit convention | `commitlint` config, release-please/semantic-release config, commit rules in `CLAUDE.md`, and the actual `git log` |
| Pull-request process | `.github/PULL_REQUEST_TEMPLATE*`, `CODEOWNERS`, branch-protection required checks, the CI gate job |
| Reporting issues | `.github/ISSUE_TEMPLATE/`, `SECURITY.md` |
| Adding a new `<unit>` | the repo's own documented extension pattern (a scaffolder skill, a plugin/command registry, a "how to add X" doc) |
| License | the `LICENSE` file and the manifest `license` field |

## Process

1. Re-validate open findings per `_conventions.md`.
2. **Locate the file.** Search `CONTRIBUTING.md`, `.github/CONTRIBUTING.md`, `docs/CONTRIBUTING.md`. Absent → skip claim extraction and go straight to steps 6–7 (file the absence, offer the scaffold), then close at step 8. Present → work steps 3–6, then step 8. Both branches end at step 8, where the summary and the apply-fixes prompt fire.
3. **Extract every claim.** Parse the file into discrete claims: each shell command, each named target/script, each stated convention, each required step, each internal link. Every claim is a suspect.
4. **Verify each claim against its source.** A documented command is verified by locating the target/script/binary it names in its source of truth (a `Makefile` target, a `package.json` script, a config key) — never by trusting the prose. Never execute a documented command to test it; a destructive or long-running instruction is verified by inspection only. A convention claim (commit format, code style) is verified against the config that enforces it. A link is verified against its resolving target. File a finding for every claim whose source contradicts it, is absent, or has drifted.
5. **Detect missing sections.** For each row in Sources of truth whose source exists in the repo, the file must carry the matching section. A repo with a `test` target and no Testing section, or with release-please and no commit-convention section, is a gap — file it.
6. **File findings** via the store protocol in `_conventions.md`, using `--auditor contributing` and `--category docs`. Fold the domain fields into the body: Problem names the claim or the missing section and quotes it; Evidence names the source of truth and what it actually says; Impact states how it blocks or misleads a contributor; Fix is the exact correction or the section to add. The finding's area is `CONTRIBUTING.md` (or the section anchor).
7. **When the file is absent, offer to scaffold it.** *Enforced convention* means the repo has a build system, a test runner, a commit convention, or a CI gate. A missing `CONTRIBUTING.md` in a repo with any of those is a High finding, and offering the scaffold is mandatory. Its fix is a generated file, offered — not written — through the apply-fixes prompt and commit gate in `_conventions.md`. Build it per the skeleton below. With no interactive user, default to not creating it and record the un-created file in the run summary. A repo with none of those conventions gets the absence recorded as Advisory with no scaffold forced.
8. Present the summary and apply fixes per `_conventions.md`.

## Scaffold skeleton

The reference structure — GitHub's, cli/cli's, and ivuorinen/actions' CONTRIBUTING guides share this spine. It supplies the section order only. Every instruction inside a section is copied from this repo's source of truth in the table above; a section whose source does not exist is omitted, not filled with a plausible guess.

1. **Intro** — what the project is and a welcome, from the README or manifest description.
2. **Reporting issues** — from the issue templates and `SECURITY.md`; a security-report channel is stated separately from bugs when `SECURITY.md` exists.
3. **Development setup** — the exact clone-and-install steps from the manifests and setup target.
4. **Code style** — the linters/formatters actually configured, with the command that runs them.
5. **Testing** — the real test command and how to scope it.
6. **Commit convention** — the enforced format and its version/release consequence when release automation reads it.
7. **Pull-request process** — the PR-template checklist, required CI checks, and review/ownership rules.
8. **Adding a new `<unit>`** — the repo's documented extension pattern, if one exists.
9. **License** — the license the repo carries and that contributions fall under it.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | A documented command is destructive or wrong in a way that corrupts a contributor's checkout, or the stated process directly contradicts an enforced gate so a compliant PR is guaranteed rejected |
| High | A stated setup/build/test command names a target/script/binary that does not exist — the contributor is blocked at that step; or `CONTRIBUTING.md` is absent in a repo with any enforced convention (build system, test runner, commit convention, or CI gate) |
| Medium | A stale reference (renamed target/script), a drifted code-style or commit-convention claim, or a missing section whose source of truth exists |
| Low | A broken internal link, a wrong ordering, or a minor inaccuracy with no blocking effect |
| Advisory | Tone or wording with no correctness consequence; or `CONTRIBUTING.md` absent in a repo with no enforced convention |

## Rules

- Existence is not accuracy. A present `CONTRIBUTING.md` is audited claim by claim; "the file exists" is never a pass.
- Every generated instruction is copied from a real target, script, or config in this repo. A fabricated setup step is a defect, worse than an omitted section.
- The example guides supply structure only. Never copy an instruction from an example repo or from memory — only from this repo's source of truth.
- The scaffolded file is created only through the `_conventions.md` apply-fixes consent and commit gate. Never write or commit it silently.
- Do not execute a documented command to verify it. Locate the target it names; verify by inspection.
- Flag only claims that contradict the repo and sections the repo's own tooling demands. Do not flag tone, or demand sections for tooling the repo does not have.

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

**"`CONTRIBUTING.md` exists, so it passes."** Existence is the start of the audit, not the end. Every command and convention in it is a claim tried against its source.

**"It's missing — I'll just note that and move on."** The command's defined job is to offer to scaffold it from real conventions. A missing file in a repo with enforced convention is a High finding, and the scaffold offer through the apply-fixes gate is mandatory, not optional.

**"I'll adapt the example CONTRIBUTING structure — it's a good template."** The examples give section order and nothing else. Every setup step, test command, and convention is read out of this repo's config. An instruction lifted from an example describes the example's repo, not this one.

**"I'll write plausible setup steps to fill the section."** A guessed command that fails on a contributor's machine is worse than a missing section. No source of truth for a section → the section is omitted.

**"The README already covers setup, so the guide is redundant."** The contributor process — commit convention, PR gates, how to add a unit — is not README material. Verify each contributor-facing claim on its own; README overlap is not coverage of it.

**"It's just a doc, I'll create it directly."** Creation is a fix. It goes behind the apply-fixes consent and the commit gate like every other write. A silently created `CONTRIBUTING.md` is a violation even when its content is correct.

**"The command reads fine, so it works."** Prose is the claim, not the proof. A documented `make setup` is verified by finding the `setup` target in the `Makefile`, not by the sentence reading plausibly.

**"One lint config is close enough to the claim."** A code-style section naming a tool the repo does not configure is a false instruction. Verify each named tool against an actual config; drop the ones that do not exist.
