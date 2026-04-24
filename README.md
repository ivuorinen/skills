# ivuorinen-skills

Hostile audit skills for Claude Code.

## Skills

| Skill | Description |
|-------|-------------|
| `adversarial-reviewer` | Hostile code review; assumes bugs exist and hunts for them |
| `nitpicker` | Exhaustive repository audit; finds defects across code, tests, docs, and config; optionally applies fixes |
| `arch-detector` | Detects which architectural patterns a codebase uses (19 patterns, 8 canonical combinations) |
| `arch-auditor` | Audits codebase for architectural violations against detected or declared patterns |
| `doc-auditor` | Verifies all documentation accuracy against the codebase; finds stale, incorrect, and missing docs |

## Installation

### Add the marketplace

```
/plugins marketplace add github:ivuorinen/skills
```

### Install the plugin

```
/plugins install ivuorinen-skills
```

## Usage

Invoke any skill by name in Claude Code:

- `/adversarial-reviewer` — hostile code review
- `/nitpicker` — exhaustive audit + optional auto-fix
- `/arch-detector` — detect architecture patterns
- `/arch-auditor` — audit architecture violations
- `/doc-auditor` — verify documentation accuracy

## Versioning

This plugin follows [Semantic Versioning](https://semver.org/):

- **PATCH** — skill improvements, bug fixes, clarifications
- **MINOR** — new skills added
- **MAJOR** — breaking changes to skill behavior or output format

Releases are automated via [release-please](https://github.com/googleapis/release-please). Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/).

See [CHANGELOG.md](CHANGELOG.md) for version history.
