# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## Commit-type corrections

Post-hoc corrections to commits that have already landed, newest first. Each
names its own commit and date, so this section's position relative to the
generated release sections below carries no meaning — release-please inserts
each new release directly beneath the header above, and these notes stay here.

> **Correction (2026-08-09):** commits `8f1c411` ("chore(deps)!: update
> astral-sh/setup-uv action", [#79]) and `b394d25` ("chore(deps)!: update
> pre-commit hook pre-commit/pre-commit-hooks", [#71]) each change a single line
> of CI config — `.github/workflows/validate-skills.yml` and
> `.pre-commit-config.yaml` respectively. `.claude/rules/commit-types.md`:
> "A workflow-only or CI-only dependency bump is never breaking." Both `!`
> markers are wrong, and they are the only breaking markers in the range since
> `ivuorinen-skills-v2.0.0` — so they alone drive release-please to a MAJOR
> bump. The release they are part of adds nine commands and an MCP server and
> removes or renames nothing: no command file was deleted or renamed, and
> `findings.py` lost no CLI flag. Read its "⚠ BREAKING CHANGES" section as
> naming two dependency upgrades, not a consumer-facing incompatibility.
> `.github/workflows/validate-skills.yml` now rejects this pattern, but only
> within an open PR's commit range, so it cannot reach these two on `main`.
>
> **Resolved (2026-08-10):** 3.0.0 is now a deliberate choice, not a derived
> one. The release carries a `Release-As: 3.0.0` footer, so release-please
> takes the version from that footer rather than from the two mislabeled `!`
> markers above. The correction stands as a record of how the number was
> originally arrived at — and the two markers remain wrong — but the version
> itself is the maintainer's decision, made in the open, and the CI guard
> prevents a repeat.

## [3.0.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v2.0.0...ivuorinen-skills-v3.0.0) (2026-08-12)


### ⚠ BREAKING CHANGES

* **deps:** update astral-sh/setup-uv action (v8.3.2 → v9.0.0) ([#79](https://github.com/ivuorinen/skills/issues/79))
* **deps:** update pre-commit hook pre-commit/pre-commit-hooks (3e8a8703264a2f4a69428a0aa4dcb512790b2c8c → v6.0.0) ([#71](https://github.com/ivuorinen/skills/issues/71))

### Features

* add /nitpicker cache command ([#77](https://github.com/ivuorinen/skills/issues/77)) ([8d0c237](https://github.com/ivuorinen/skills/commit/8d0c23702070533d3b7f02823058116455bec77a))
* add /nitpicker contributing command ([#57](https://github.com/ivuorinen/skills/issues/57)) ([4ec92d5](https://github.com/ivuorinen/skills/commit/4ec92d51b11f573ec26503817c0efe26b5581784))
* add /nitpicker dead-code command ([#76](https://github.com/ivuorinen/skills/issues/76)) ([a392ec6](https://github.com/ivuorinen/skills/commit/a392ec66ccfac4207f2a1cf94f6747d2d8fb96a7))
* add /nitpicker execute-plan command ([#65](https://github.com/ivuorinen/skills/issues/65)) ([1d718c9](https://github.com/ivuorinen/skills/commit/1d718c927e9e7fd54b188d6e64d30dc8fdeaf932))
* add /nitpicker reliability command ([#75](https://github.com/ivuorinen/skills/issues/75)) ([8553e0c](https://github.com/ivuorinen/skills/commit/8553e0c5dd01103135c4ff1bd32ea347f04febd7))
* add /nitpicker reverify command ([#81](https://github.com/ivuorinen/skills/issues/81)) ([6fafcfe](https://github.com/ivuorinen/skills/commit/6fafcfe51bfc5cf67cee70a18e0f312f521e7eb8))
* add /nitpicker teach command ([#62](https://github.com/ivuorinen/skills/issues/62)) ([0aa2eb3](https://github.com/ivuorinen/skills/commit/0aa2eb34ae6d5d08837cf588676f6a829e40d326))
* add /nitpicker triage command ([#80](https://github.com/ivuorinen/skills/issues/80)) ([594705d](https://github.com/ivuorinen/skills/commit/594705d97593e65c7868bc599753fce51caee2e8))
* add CodeRabbit review loop to /nitpicker cr ([#83](https://github.com/ivuorinen/skills/issues/83)) ([30632d9](https://github.com/ivuorinen/skills/commit/30632d9f68e5923891a93e9b454a4cf542780a56))
* add nitpicker MCP server (skill introspection + findings tools) ([#64](https://github.com/ivuorinen/skills/issues/64)) ([444a84c](https://github.com/ivuorinen/skills/commit/444a84cdac0ee50b0b666239e7fa773f6e5510ff))
* add write-surgical-code rule from Karpathy's LLM-coding guidelines ([#61](https://github.com/ivuorinen/skills/issues/61)) ([955fac3](https://github.com/ivuorinen/skills/commit/955fac3fc89cbbdc2a88aee245b954c26b584a3e))
* cr surfaces review bodies + bot summaries and adds an autopilot option ([#88](https://github.com/ivuorinen/skills/issues/88)) ([1022c28](https://github.com/ivuorinen/skills/commit/1022c28d27ba761ba36989440cb83a3df3e8eee4))
* fold datetime, money, and changelog lenses into existing commands ([#78](https://github.com/ivuorinen/skills/issues/78)) ([20851c6](https://github.com/ivuorinen/skills/commit/20851c6d3b41dcaa1ba6125854f08fe225523cde))
* fold supply-chain execution surface into deps ([#82](https://github.com/ivuorinen/skills/issues/82)) ([53611f6](https://github.com/ivuorinen/skills/commit/53611f61f2522d49412df18cded83fb8c818043a))
* graphify integration, vendored-skill validator support, and tool hardening ([#63](https://github.com/ivuorinen/skills/issues/63)) ([a7aa066](https://github.com/ivuorinen/skills/commit/a7aa066a0f4e715f82cfa517b8293da0ceb8df54))
* harden the audit toolkit and add a bandit security gate ([#90](https://github.com/ivuorinen/skills/issues/90)) ([07513cc](https://github.com/ivuorinen/skills/commit/07513cc090ea5dd15519cfb4826e5ffd9eb74e62))
* harden the enforcement surface and the findings store ([#66](https://github.com/ivuorinen/skills/issues/66)) ([2dce882](https://github.com/ivuorinen/skills/commit/2dce882c9904f2543fd681ae132407d6bdad4b41))
* publish MCP tool annotations and negotiate the protocol version ([#89](https://github.com/ivuorinen/skills/issues/89)) ([d80acde](https://github.com/ivuorinen/skills/commit/d80acde4594ab635cfbe879844d71ad688ffbc6d))


### Bug Fixes

* **ci:** let Renovate update the SHA-pinned pre-commit revs ([#98](https://github.com/ivuorinen/skills/issues/98)) ([d3b4912](https://github.com/ivuorinen/skills/commit/d3b4912f45ae9291512f8f8e9db72688664e9c97))
* **ci:** make the pre-commit custom manager actually match its file ([#100](https://github.com/ivuorinen/skills/issues/100)) ([1781baf](https://github.com/ivuorinen/skills/commit/1781baf5200319b96874d1220fa9bf2fe38c3f14))
* close deny-agents glob bypass, add hooks/settings edit guard, harden sarif/findings/validate-rules edge cases ([#87](https://github.com/ivuorinen/skills/issues/87)) ([157d8b2](https://github.com/ivuorinen/skills/commit/157d8b27df6817d59ce002213672cc3d93362209))
* close the globstar bypass in the agents-path guard ([#96](https://github.com/ivuorinen/skills/issues/96)) ([16e38ef](https://github.com/ivuorinen/skills/commit/16e38ef2e1db1c718a5f247d6774562417d80d12))
* **deps:** update dependency ruff (0.15.21 → 0.15.22) ([#73](https://github.com/ivuorinen/skills/issues/73)) ([1309b54](https://github.com/ivuorinen/skills/commit/1309b540f7b57d2395becf5772571723cc6239dd))
* **deps:** update dependency ruff (0.15.22 → 0.16.0) ([#85](https://github.com/ivuorinen/skills/issues/85)) ([8962495](https://github.com/ivuorinen/skills/commit/8962495319d563836a075cea5024fa90c1e17968))
* **deps:** update dependency ruff (0.16.0 → 0.16.1) ([#94](https://github.com/ivuorinen/skills/issues/94)) ([9b917a2](https://github.com/ivuorinen/skills/commit/9b917a22fc96ee64560523eb0f6a60d230fcb8dc))
* **deps:** update ruff ([#109](https://github.com/ivuorinen/skills/issues/109)) ([c4ef015](https://github.com/ivuorinen/skills/commit/c4ef015026d775953785c50d1882fb9ac0f9eb6c))
* harden audit toolkit — findings-store, shipped tools, and enforcement hooks ([#86](https://github.com/ivuorinen/skills/issues/86)) ([90a1cbf](https://github.com/ivuorinen/skills/commit/90a1cbfdf141f5371e79cec13c1c9dd53c98d4f9))
* harden shipped audit tools and enforcement surface (nitpicker audit) ([#72](https://github.com/ivuorinen/skills/issues/72)) ([6a6499d](https://github.com/ivuorinen/skills/commit/6a6499dc6f67d033af6aa2b92c6ee6b753659771))
* make MCP tools the default and shell the last resort in the conventions ([#68](https://github.com/ivuorinen/skills/issues/68)) ([513f52f](https://github.com/ivuorinen/skills/commit/513f52f369a4b52c6534d5c234bd9c6d561e41fa))
* prepare the 3.0.0 release and close the enforcement-surface bypass ([#111](https://github.com/ivuorinen/skills/issues/111)) ([8b2a651](https://github.com/ivuorinen/skills/commit/8b2a651f434e7104c36c97d6c7ee60e390574446))
* stop a line continuation hiding a push to a protected branch ([#105](https://github.com/ivuorinen/skills/issues/105)) ([789efa9](https://github.com/ivuorinen/skills/commit/789efa996b7eaa1fdfdc9e19e6f688bc1db82e87))
* stop reading permanent GraphQL failures as transient outages ([#95](https://github.com/ivuorinen/skills/issues/95)) ([dcd387b](https://github.com/ivuorinen/skills/commit/dcd387b0946f4dad16e23786d62da8764340bc1a))


### Miscellaneous Chores

* **deps:** update astral-sh/setup-uv action (v8.3.2 → v9.0.0) ([#79](https://github.com/ivuorinen/skills/issues/79)) ([8f1c411](https://github.com/ivuorinen/skills/commit/8f1c411e67e80bfc4e813facbb2474fcc3c332ee))
* **deps:** update pre-commit hook pre-commit/pre-commit-hooks (3e8a8703264a2f4a69428a0aa4dcb512790b2c8c → v6.0.0) ([#71](https://github.com/ivuorinen/skills/issues/71)) ([b394d25](https://github.com/ivuorinen/skills/commit/b394d2560d4b52b18abf87fa5743975b461c7792))

## 3.0.0 — why a major

3.0.0 is a maintainer decision rather than a semver derivation, recorded here
so the number is not mistaken for a compatibility signal.

**Nothing in this release breaks a 2.x consumer.** No command file was deleted
or renamed, `findings.py` lost no CLI flag, and the resolved-ledger store
layout shipped in 2.0.0 and is unchanged. A strict semver reading of the diff
gives 2.1.0.

The major marks the size of the addition rather than a break in compatibility:
nine new commands (`cache`, `contributing`, `dead-code`, `execute-plan`,
`reliability`, `reverify`, `teach`, `triage`, plus the shared `_teach-formats`),
a bundled stdio MCP server exposing ten `np_`-prefixed tools, and a reworked
enforcement surface. Upgrading from 2.x requires no changes.

**Contributors to this repository** — as distinct from consumers of the
published skill — do see a behaviour change. The PreToolUse guards in
`scripts/hooks/` now deny a Bash write to `scripts/hooks/` or
`.claude/settings.json`, an unscoped worktree rewrite (`git reset --hard`,
`git checkout .`, `git restore .`, `git apply`), and whole-tree staging
(`git add -A`, `--all`, `.`, `:/`). Explicit pathspecs, `git add -u`, `git add
-p`, `git stash` and `git clean` are unaffected. None of this reaches an
installed consumer: `.claude-plugin/plugin.json` declares no `hooks` key, the
repository ships no plugin `hooks/` directory, and the installed tree is
`skills/nitpicker/` only — `scripts/hooks/` and `.claude/settings.json` are
development configuration for this repo and are not part of the package.

> **Correction (2026-07-19):** commit `955fac3` ("feat: add write-surgical-code
> rule from Karpathy's LLM-coding guidelines", [#61]) touches only
> `.claude/rules/write-surgical-code.md`, `.gitignore` and `CLAUDE.md` — no path
> under `skills/`, so no installed consumer sees a difference. It should have
> been `docs:` or `chore:` and warrants no minor bump. See
> `.claude/rules/commit-types.md`.

> **Correction (2026-07-19):** commit `a7aa066` ("feat: graphify integration,
> vendored-skill validator support, and tool hardening", [#63]) bundles three
> separable concerns across 25 files — vendoring a third-party skill, adding a
> validator allowlist plus its rule, and hardening three shipped scripts. It
> should have been split into three commits. The vendoring half landed without
> the `LICENSE` and `NOTICE` entries `.claude/rules/vendored-skills.md` requires
> (both added later); a single-concern vendoring commit would have surfaced that
> gap in review. See `.claude/rules/commit-types.md`.

[#61]: https://github.com/ivuorinen/skills/issues/61
[#63]: https://github.com/ivuorinen/skills/issues/63
[#71]: https://github.com/ivuorinen/skills/issues/71
[#79]: https://github.com/ivuorinen/skills/issues/79

## [2.0.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.8.0...ivuorinen-skills-v2.0.0) (2026-07-10)


### ⚠ BREAKING CHANGES

* the standalone `*-auditor` skills are replaced by a single `nitpicker` skill invoked as `/nitpicker <command>`; consumers must update their invocations (the old names still resolve as aliases).

### Features

* reorganize standalone audit skills into one nitpicker skill with commands ([#54](https://github.com/ivuorinen/skills/issues/54)) ([dc3c074](https://github.com/ivuorinen/skills/commit/dc3c07437d8d5c1aac0fae6d7285f5c9d1c9d3fc))

## [1.8.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.7.2...ivuorinen-skills-v1.8.0) (2026-07-06)

### Features

- add concurrency-auditor skill ([#47](https://github.com/ivuorinen/skills/issues/47)) ([45833f8](https://github.com/ivuorinen/skills/commit/45833f8d227832e7afc4b8c12e784a31954bd5f7))
- add config-auditor skill ([#50](https://github.com/ivuorinen/skills/issues/50)) ([0ac2ba0](https://github.com/ivuorinen/skills/commit/0ac2ba09d124885c0ebd4da7b4503ada4b52c255))
- add data-privacy-auditor skill ([#51](https://github.com/ivuorinen/skills/issues/51)) ([679e74c](https://github.com/ivuorinen/skills/commit/679e74c92f3fff8576863def8d442516033bc432))
- add i18n-auditor skill ([#48](https://github.com/ivuorinen/skills/issues/48)) ([ba681ef](https://github.com/ivuorinen/skills/commit/ba681efe5cfaa7b0729c61990aa5a0a7a8a56ed3))
- add resource-leak-auditor skill ([#49](https://github.com/ivuorinen/skills/issues/49)) ([9c54f45](https://github.com/ivuorinen/skills/commit/9c54f45319320e91527c7602e49a7baa29f01329))

## [1.7.2](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.7.1...ivuorinen-skills-v1.7.2) (2026-07-06)

### Bug Fixes

- repo audit fixes, workflow hardening, and findings-consistency enforcement ([#45](https://github.com/ivuorinen/skills/issues/45)) ([979ef8c](https://github.com/ivuorinen/skills/commit/979ef8ca3feaffa25b3dcb3ad354492be3b5ef6b))

## [1.7.1](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.7.0...ivuorinen-skills-v1.7.1) (2026-07-05)

### Bug Fixes

- wire specialist auditors into nitpicker modes and release-prep gates ([#43](https://github.com/ivuorinen/skills/issues/43)) ([02b159b](https://github.com/ivuorinen/skills/commit/02b159bc24dc71e1c9b51007913acac90f4da3ed))

## [1.7.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.6.0...ivuorinen-skills-v1.7.0) (2026-07-05)

> **Correction (2026-07-19):** this entry originally carried a "BREAKING
> CHANGES" section naming the actions/checkout v6→v7 bump (#29). That commit
> used `chore(deps)!:` for a change confined to `.github/workflows/`, which
> touches no published surface — 1.7.0 shipped no breaking change and the
> section has been removed. See `.claude/rules/commit-types.md`.

### Features

- add a11y-auditor skill ([#42](https://github.com/ivuorinen/skills/issues/42)) ([aa21561](https://github.com/ivuorinen/skills/commit/aa2156109fa47bb6c55f836004f8aaf8ba6b7a35))
- add api-contract-auditor skill ([#41](https://github.com/ivuorinen/skills/issues/41)) ([7b1078a](https://github.com/ivuorinen/skills/commit/7b1078a16bd24724ebcf93c3b55dd1081e86ef6f))
- add ci-auditor skill ([#36](https://github.com/ivuorinen/skills/issues/36)) ([19f0ff9](https://github.com/ivuorinen/skills/commit/19f0ff9bcb2c3c0097422e1d8e15c80d69fbd187))
- add commit-auditor skill ([#38](https://github.com/ivuorinen/skills/issues/38)) ([59e9b2c](https://github.com/ivuorinen/skills/commit/59e9b2cec15c8c9141faa7cab1186402689a2763))
- add complexity-hunter skill ([#30](https://github.com/ivuorinen/skills/issues/30)) ([03de76c](https://github.com/ivuorinen/skills/commit/03de76ce437c1c5bf785ba86a28aa7b332414a53))
- add dep-auditor skill ([#34](https://github.com/ivuorinen/skills/issues/34)) ([70c991b](https://github.com/ivuorinen/skills/commit/70c991b65578279d98aba3aef648c806c45bd073))
- add migration-auditor skill ([#39](https://github.com/ivuorinen/skills/issues/39)) ([9492c57](https://github.com/ivuorinen/skills/commit/9492c57461df840328eff40735a3c6f6e5629aaa))
- add observability-auditor skill ([#40](https://github.com/ivuorinen/skills/issues/40)) ([8af9fe8](https://github.com/ivuorinen/skills/commit/8af9fe8b4bdacb8142c26066a53a5892e5ad5789))
- add perf-auditor skill ([#32](https://github.com/ivuorinen/skills/issues/32)) ([59f58dc](https://github.com/ivuorinen/skills/commit/59f58dcfb739078788ce74ead85ab9e566165787))
- add silent-failure-hunter skill ([#35](https://github.com/ivuorinen/skills/issues/35)) ([1c296b0](https://github.com/ivuorinen/skills/commit/1c296b053e824b4bb19eaac769e7e58e95271892))
- add test-auditor skill ([#33](https://github.com/ivuorinen/skills/issues/33)) ([0726fba](https://github.com/ivuorinen/skills/commit/0726fba35d7181753dc8e030bd94f347b1bed83b))

### Miscellaneous Chores

- **deps:** update actions/checkout action (v6.0.3 → v7.0.0) ([#29](https://github.com/ivuorinen/skills/issues/29)) ([29ab230](https://github.com/ivuorinen/skills/commit/29ab230c3f09fd6f813ee4a988d46e02f14ad2fc))
- release 1.7.0 ([4e3f1bd](https://github.com/ivuorinen/skills/commit/4e3f1bd28ef072403ec6c814b754af0e93d967eb))

## [1.6.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.5.0...ivuorinen-skills-v1.6.0) (2026-06-06)

### Features

- add hooks-enforcer skill ([#28](https://github.com/ivuorinen/skills/issues/28)) ([6173a60](https://github.com/ivuorinen/skills/commit/6173a6033e0f48cbc2143ec44d7241653ad956cb))
- add loophole-hunter skill ([#25](https://github.com/ivuorinen/skills/issues/25)) ([99e8472](https://github.com/ivuorinen/skills/commit/99e8472f3a3c91478dd6469f57bc66b053f4b09f))
- add Python skill tools with tests and nitpicker pass 21 ([#23](https://github.com/ivuorinen/skills/issues/23)) ([4709777](https://github.com/ivuorinen/skills/commit/47097772a06bd3b064e65f553dc0d3d69671a13f))

## [1.5.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.4.0...ivuorinen-skills-v1.5.0) (2026-05-28)

### Features

- skill docs, description format, validator, and /goal examples ([#21](https://github.com/ivuorinen/skills/issues/21)) ([8ea6e5a](https://github.com/ivuorinen/skills/commit/8ea6e5ab4dbe48aef8bfdafdf9e0f5e6b1bce521))

## [1.4.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.3.1...ivuorinen-skills-v1.4.0) (2026-05-01)

### Features

- add claude-rules-auditor skill ([#17](https://github.com/ivuorinen/skills/issues/17)) ([1907359](https://github.com/ivuorinen/skills/commit/19073596f5ff15cceab7c365081917e66a72a62f))
- add cr-implementer skill ([#14](https://github.com/ivuorinen/skills/issues/14)) ([aa2353c](https://github.com/ivuorinen/skills/commit/aa2353cc2ea4f73b30c091816330f7170485c5ec))

### Bug Fixes

- validator hardening — quote handling, duplicate pass header, pytest suite ([#16](https://github.com/ivuorinen/skills/issues/16)) ([3fc9fa9](https://github.com/ivuorinen/skills/commit/3fc9fa9ba58ec9e8060b3f27005ba026a7f0828d))

## [1.3.1](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.3.0...ivuorinen-skills-v1.3.1) (2026-04-29)

### Bug Fixes

- quote descriptions containing ': ' to fix yaml.v3 parsing ([#12](https://github.com/ivuorinen/skills/issues/12)) ([0178132](https://github.com/ivuorinen/skills/commit/01781324f062836d7d21ff29ff23bd54b22edf4b))

## [1.3.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.2.0...ivuorinen-skills-v1.3.0) (2026-04-26)

### Features

- wire internal skills together and add skill wiring README ([#9](https://github.com/ivuorinen/skills/issues/9)) ([554d719](https://github.com/ivuorinen/skills/commit/554d7196440d8faa3016e9daef6fe5ad26fdb226))

## [1.2.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.1.0...ivuorinen-skills-v1.2.0) (2026-04-25)

### Features

- add security-auditor skill ([#6](https://github.com/ivuorinen/skills/issues/6)) ([0a70ddd](https://github.com/ivuorinen/skills/commit/0a70ddd1285eb032768f6fcc675f6b15a6258c7e))

### Bug Fixes

- **docs:** fix marketplace command, add license ([#4](https://github.com/ivuorinen/skills/issues/4)) ([e15c2e6](https://github.com/ivuorinen/skills/commit/e15c2e68b4d31b12b4491bb2e47c13f03aa4fdfd))

## [1.1.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.0.0...ivuorinen-skills-v1.1.0) (2026-04-24)

### Features

- initial release ([7f941dd](https://github.com/ivuorinen/skills/commit/7f941dd59db4ef5cf2b6193025a08d40a610315d))

### Bug Fixes

- correct config-file and manifest-file paths (leading dot) ([#2](https://github.com/ivuorinen/skills/issues/2)) ([93d6136](https://github.com/ivuorinen/skills/commit/93d61364a3a4746d7d6455eb2882deafd9014195))
- move release-type inside package entry for release-please v5 ([044401d](https://github.com/ivuorinen/skills/commit/044401d4ff88685658a2b0142560bf26a3ecfeaa))
- release-please workflow — issues permission and explicit manifest inputs ([#1](https://github.com/ivuorinen/skills/issues/1)) ([3dd0277](https://github.com/ivuorinen/skills/commit/3dd0277e4c9762c975604baf433c7509d4f326df))

## [1.0.0] - 2026-04-24

### Added

- `adversarial-reviewer` — hostile code review; assumes bugs exist and hunts for them
- `nitpicker` — exhaustive repository audit with integrated fixing; single-shot with re-validation on subsequent runs
- `arch-detector` — detects architectural patterns (19 patterns, 8 canonical combinations including Explicit Architecture)
- `arch-auditor` — audits codebase for architectural violations against detected or declared patterns
- `doc-auditor` — verifies all documentation accuracy against the codebase; finds stale, incorrect, and missing docs
