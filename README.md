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
| `pr-reviewer` | Hostile but constructive PR review; outputs copy-paste-ready markdown for GitHub PR comments |
| `security-auditor` | Audits a codebase with available security scanners, parses results, and writes a consolidated findings report |
| `cr-implementer` | Fetches GitHub PR review comments (unresolved where available via GraphQL), evaluates and implements valid ones one at a time, verifies with tests and linting, and asks user whether to leave/commit/push |

## Installation

### Add the marketplace

```text
/plugins marketplace add ivuorinen/skills
```

### Install the plugin

```text
/plugins install ivuorinen-skills
```

## Usage

Invoke any skill by name in Claude Code:

- `/adversarial-reviewer` — hostile code review
- `/nitpicker` — exhaustive audit + optional auto-fix
- `/arch-detector` — detect architecture patterns
- `/arch-auditor` — audit architecture violations
- `/doc-auditor` — verify documentation accuracy
- `/pr-reviewer` — PR review (stdout only)
- `/security-auditor` — security audit with available local scanners

## Versioning

This plugin follows [Semantic Versioning](https://semver.org/):

- **PATCH** — skill improvements, bug fixes, clarifications
- **MINOR** — new skills added
- **MAJOR** — breaking changes to skill behavior or output format

Releases are automated via [release-please](https://github.com/googleapis/release-please). Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/).

See [CHANGELOG.md](CHANGELOG.md) for version history.

## License

This project is licensed under the [MIT License](LICENSE). Copyright © 2026 Ismo Vuorinen.
