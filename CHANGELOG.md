# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

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
