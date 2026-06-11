# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [1.6.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.5.0...ivuorinen-skills-v1.6.0) (2026-06-06)


### Features

* add hooks-enforcer skill ([#28](https://github.com/ivuorinen/skills/issues/28)) ([6173a60](https://github.com/ivuorinen/skills/commit/6173a6033e0f48cbc2143ec44d7241653ad956cb))
* add loophole-hunter skill ([#25](https://github.com/ivuorinen/skills/issues/25)) ([99e8472](https://github.com/ivuorinen/skills/commit/99e8472f3a3c91478dd6469f57bc66b053f4b09f))
* add Python skill tools with tests and nitpicker pass 21 ([#23](https://github.com/ivuorinen/skills/issues/23)) ([4709777](https://github.com/ivuorinen/skills/commit/47097772a06bd3b064e65f553dc0d3d69671a13f))

## [1.5.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.4.0...ivuorinen-skills-v1.5.0) (2026-05-28)


### Features

* skill docs, description format, validator, and /goal examples ([#21](https://github.com/ivuorinen/skills/issues/21)) ([8ea6e5a](https://github.com/ivuorinen/skills/commit/8ea6e5ab4dbe48aef8bfdafdf9e0f5e6b1bce521))

## [1.4.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.3.1...ivuorinen-skills-v1.4.0) (2026-05-01)


### Features

* add claude-rules-auditor skill ([#17](https://github.com/ivuorinen/skills/issues/17)) ([1907359](https://github.com/ivuorinen/skills/commit/19073596f5ff15cceab7c365081917e66a72a62f))
* add cr-implementer skill ([#14](https://github.com/ivuorinen/skills/issues/14)) ([aa2353c](https://github.com/ivuorinen/skills/commit/aa2353cc2ea4f73b30c091816330f7170485c5ec))


### Bug Fixes

* validator hardening — quote handling, duplicate pass header, pytest suite ([#16](https://github.com/ivuorinen/skills/issues/16)) ([3fc9fa9](https://github.com/ivuorinen/skills/commit/3fc9fa9ba58ec9e8060b3f27005ba026a7f0828d))

## [1.3.1](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.3.0...ivuorinen-skills-v1.3.1) (2026-04-29)


### Bug Fixes

* quote descriptions containing ': ' to fix yaml.v3 parsing ([#12](https://github.com/ivuorinen/skills/issues/12)) ([0178132](https://github.com/ivuorinen/skills/commit/01781324f062836d7d21ff29ff23bd54b22edf4b))

## [1.3.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.2.0...ivuorinen-skills-v1.3.0) (2026-04-26)


### Features

* wire internal skills together and add skill wiring README ([#9](https://github.com/ivuorinen/skills/issues/9)) ([554d719](https://github.com/ivuorinen/skills/commit/554d7196440d8faa3016e9daef6fe5ad26fdb226))

## [1.2.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.1.0...ivuorinen-skills-v1.2.0) (2026-04-25)


### Features

* add security-auditor skill ([#6](https://github.com/ivuorinen/skills/issues/6)) ([0a70ddd](https://github.com/ivuorinen/skills/commit/0a70ddd1285eb032768f6fcc675f6b15a6258c7e))


### Bug Fixes

* **docs:** fix marketplace command, add license ([#4](https://github.com/ivuorinen/skills/issues/4)) ([e15c2e6](https://github.com/ivuorinen/skills/commit/e15c2e68b4d31b12b4491bb2e47c13f03aa4fdfd))

## [1.1.0](https://github.com/ivuorinen/skills/compare/ivuorinen-skills-v1.0.0...ivuorinen-skills-v1.1.0) (2026-04-24)


### Features

* initial release ([7f941dd](https://github.com/ivuorinen/skills/commit/7f941dd59db4ef5cf2b6193025a08d40a610315d))


### Bug Fixes

* correct config-file and manifest-file paths (leading dot) ([#2](https://github.com/ivuorinen/skills/issues/2)) ([93d6136](https://github.com/ivuorinen/skills/commit/93d61364a3a4746d7d6455eb2882deafd9014195))
* move release-type inside package entry for release-please v5 ([044401d](https://github.com/ivuorinen/skills/commit/044401d4ff88685658a2b0142560bf26a3ecfeaa))
* release-please workflow — issues permission and explicit manifest inputs ([#1](https://github.com/ivuorinen/skills/issues/1)) ([3dd0277](https://github.com/ivuorinen/skills/commit/3dd0277e4c9762c975604baf433c7509d4f326df))

## [1.0.0] - 2026-04-24

### Added

- `adversarial-reviewer` — hostile code review; assumes bugs exist and hunts for them
- `nitpicker` — exhaustive repository audit with integrated fixing; single-shot with re-validation on subsequent runs
- `arch-detector` — detects architectural patterns (19 patterns, 8 canonical combinations including Explicit Architecture)
- `arch-auditor` — audits codebase for architectural violations against detected or declared patterns
- `doc-auditor` — verifies all documentation accuracy against the codebase; finds stale, incorrect, and missing docs
