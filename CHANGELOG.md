# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [1.0.0] - 2026-04-24

### Added

- `adversarial-reviewer` — hostile code review; assumes bugs exist and hunts for them
- `nitpicker` — exhaustive repository audit with integrated fixing; single-shot with re-validation on subsequent runs
- `arch-detector` — detects architectural patterns (19 patterns, 8 canonical combinations including Explicit Architecture)
- `arch-auditor` — audits codebase for architectural violations against detected or declared patterns
- `doc-auditor` — verifies all documentation accuracy against the codebase; finds stale, incorrect, and missing docs
