# ivuorinen-skills

Hostile audit skills for Claude Code.

## Skills

Skills are listed in preferred execution order. [`nitpicker`][nitpicker] is the orchestrator — start there for a full audit.

| Skill | Description |
|-------|-------------|
| [`nitpicker`][nitpicker] | Exhaustive repository audit; finds defects across code, tests, docs, and config; optionally applies fixes |
| [`arch-detector`][arch-detector] | Detects which architectural patterns a codebase uses (19 patterns, 8 canonical combinations) |
| [`arch-auditor`][arch-auditor] | Audits codebase for architectural violations against detected or declared patterns |
| [`doc-auditor`][doc-auditor] | Verifies all documentation accuracy against the codebase; finds stale, incorrect, and missing docs |
| [`security-auditor`][security-auditor] | Audits a codebase with available security scanners, parses results, and writes a consolidated findings report |
| [`adversarial-reviewer`][adversarial-reviewer] | Hostile code review; assumes bugs exist and hunts for them |
| [`pr-reviewer`][pr-reviewer] | Hostile but constructive PR review; outputs copy-paste-ready markdown for GitHub PR comments |
| [`cr-implementer`][cr-implementer] | Fetches GitHub PR review comments (unresolved where available via GraphQL), evaluates and implements valid ones one at a time, verifies with tests and linting, and asks user whether to leave/commit/push |
| [`claude-rules-auditor`][claude-rules-auditor] | Audits `.claude/rules/` files for quality, checks CLAUDE.md for misplaced rules, and suggests new rules from project conventions and audit artifacts |
| [`loophole-hunter`][loophole-hunter] | Audits the Claude Code enforcement surface (`.claude/rules/`, hooks, `.claude/settings.json`, permissions, skills) for bypassable or unenforced constraints and closes them; invoked by `nitpicker` in `loophole` mode and by `release-prep` as a gate |
| [`hooks-enforcer`][hooks-enforcer] | Audits an agent project's hook *coverage* against its evidence base (current hooks, audit-findings history, git history, project memory); finds recurring failures no hook guards and context-discipline gaps where large-output work bypasses a context-saving tool; specifies and wires the missing hooks in the host harness's correct shape; invoked by `nitpicker` in `loophole` mode and by `release-prep` as a gate |
| [`complexity-hunter`][complexity-hunter] | Forces the laziest solution that actually works on every coding task — climbs a reuse-first ladder (YAGNI, codebase, stdlib, platform, installed dependency, one line) before writing new code; stays active on every coding response once invoked; also audits a diff or a whole repo for over-engineering with tagged, ranked findings; never simplifies away trust-boundary validation, data-loss error handling, security, or accessibility |
| [`perf-auditor`][perf-auditor] | Hostile single-shot performance audit; hunts N+1 queries, O(n²)+ hotspots on real data paths, sync-blocking calls in async contexts, unbounded caches/queues/retries, missing pagination, loop-invariant work redone per iteration, and chatty per-item I/O; every finding names the code path, the growth driver, and a concrete fix; uses installed measurement tools, never adds a dependency |
| [`test-auditor`][test-auditor] | Hostile audit of the test suite itself; assumes the tests are weaker than they look and proves it — assertion-free and tautological tests, mocks of the unit under test, over-mocking that severs the code path, flaky patterns, untracked skips, coverage holes on money/security/data-loss paths, and mutation-blind spots; fixes add or strengthen tests only, never production source |
| [`dep-auditor`][dep-auditor] | Audits dependency health beyond CVEs — unused, phantom, duplicate, heavyweight, unmaintained, license-conflicting, drifted, and misclassified dependencies; cross-references manifest, lockfile, and a full import/usage scan; never installs anything |

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

Invoke any skill by name in Claude Code (listed in execution order):

- `/nitpicker` — exhaustive audit + optional auto-fix
- `/arch-detector` — detect architecture patterns
- `/arch-auditor` — audit architecture violations
- `/doc-auditor` — verify documentation accuracy
- `/security-auditor` — security audit with available local scanners
- `/adversarial-reviewer` — hostile code review
- `/pr-reviewer` — PR review (stdout only)
- `/cr-implementer` — implement PR review comments
- `/claude-rules-auditor` — audit `.claude/rules/` and CLAUDE.md rule placement
- `/loophole-hunter` — audit the Claude Code enforcement surface and close loopholes
- `/hooks-enforcer` — audit hook coverage against the project's evidence base and wire the missing hooks
- `/complexity-hunter` — force the laziest working solution on every coding task (sticky mode); also audits a diff or repo for over-engineering
- `/perf-auditor` — performance audit with growth-driver evidence; writes findings to `docs/audit/perf-auditor-findings.md`
- `/test-auditor` — audit the test suite itself for tests that cannot fail, severed code paths, flaky patterns, and critical-path coverage holes
- `/dep-auditor` — audit dependency health beyond CVEs: unused, phantom, duplicate, heavyweight, unmaintained, license-conflicting, drifted, and misclassified dependencies

## Examples

### Full repository audit (recommended starting point)

```
/nitpicker
```

Exhaustive audit of code, tests, docs, and config. Findings written to `docs/audit/nitpicker-findings.md`. At the end, nitpicker offers to apply fixes and asks before committing.

### Focused nitpicker modes

```
/nitpicker security          # invokes security-auditor, then extends with trust-boundary analysis
/nitpicker docs              # invokes doc-auditor, then extends with inline comment accuracy
/nitpicker architecture      # invokes arch-detector + arch-auditor, then extends with coupling analysis
/nitpicker changed-files     # limit review to modified files and their dependencies only
/nitpicker release-gate      # fail if any High or Critical findings exist (CI gate)
/nitpicker inline            # return findings in the response, no file written
```

### Architecture pipeline

```
/arch-detector    # detect patterns → writes docs/audit/arch-profile.md
/arch-auditor     # find violations → writes docs/audit/arch-findings.md
```

Run `arch-detector` first — `arch-auditor` reads the profile and produces stronger, more precise findings.

### Security scan

```
/security-auditor
```

Probes for available scanners (`semgrep`, `grype`, `trivy`, `gitleaks`, `checkov`, `gosec`, `snyk`, `npm`/`yarn`/`pnpm` audit) and runs all that are present.

### PR review

```
/pr-reviewer          # review the current branch diff
/pr-reviewer 42       # review PR #42 on GitHub
```

Output is copy-paste-ready markdown for GitHub PR comments.

### Implement review comments

```
/cr-implementer       # detect and implement unresolved comments on the current PR
/cr-implementer 42    # implement comments on PR #42
```

Evaluates each comment, implements valid ones one at a time, verifies with tests and linting, and asks before committing or posting replies.

### Running nitpicker autonomously with /goal

[`/goal`][goal-doc] sets a completion condition and keeps Claude working toward it across turns — no re-prompting after each step. After each turn, a separate fast model checks whether the condition holds. If not, Claude starts another turn automatically. The goal clears once the condition is met.

```
/goal /nitpicker finds no Critical or High findings and docs/audit/nitpicker-findings.md is committed
```

For fully unattended runs, enable **[auto mode][auto-mode-doc]** before setting the goal. Auto mode uses a background classifier to approve tool calls (file edits, shell commands) without prompting you:

| Layer | What it removes |
|-------|----------------|
| `/goal` | Per-turn prompts — Claude re-enters after each turn until the condition holds |
| Auto mode | Per-tool prompts — file edits and shell commands proceed without confirmation |

Enable auto mode: press `Shift+Tab` in the CLI until `auto` is shown, or use the mode selector in VS Code or Desktop.

```
# 1. Enable auto mode first (Shift+Tab in the CLI)
# 2. Then set the goal:
/goal /nitpicker security applies all Critical and High fixes, docs/audit/nitpicker-findings.md shows 0 open Critical/High
```

Write effective goal conditions with a verifiable end state — something Claude's own output can demonstrate: a file written, a count reached, a command exit code. Include a turn limit to bound how long the goal can run: `or stop after 15 turns`.

> `/goal` requires Claude Code v2.1.139 or later. See the [`/goal` documentation][goal-doc] and [auto mode reference][auto-mode-doc] for full details.

## Versioning

This plugin follows [Semantic Versioning](https://semver.org/):

- **PATCH** — skill improvements, bug fixes, clarifications
- **MINOR** — new skills added
- **MAJOR** — breaking changes to skill behavior or output format

Releases are automated via [release-please](https://github.com/googleapis/release-please). Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/).

See [CHANGELOG.md](CHANGELOG.md) for version history.

## Credits

[`complexity-hunter`][complexity-hunter] is adapted from [ponytail](https://github.com/DietrichGebert/ponytail) by Dietrich Gebert — the lazy-senior mindset, the ladder, the output pattern, and the audit tags originate there, reshaped to this repo's skill conventions.

## License

This project is licensed under the [MIT License](LICENSE). Copyright © 2026 Ismo Vuorinen.

[nitpicker]: skills/nitpicker/README.md
[arch-detector]: skills/arch-detector/README.md
[arch-auditor]: skills/arch-auditor/README.md
[doc-auditor]: skills/doc-auditor/README.md
[security-auditor]: skills/security-auditor/README.md
[adversarial-reviewer]: skills/adversarial-reviewer/README.md
[pr-reviewer]: skills/pr-reviewer/README.md
[cr-implementer]: skills/cr-implementer/README.md
[claude-rules-auditor]: skills/claude-rules-auditor/README.md
[loophole-hunter]: skills/loophole-hunter/README.md
[hooks-enforcer]: skills/hooks-enforcer/README.md
[test-auditor]: skills/test-auditor/README.md
[complexity-hunter]: skills/complexity-hunter/README.md
[perf-auditor]: skills/perf-auditor/README.md
[dep-auditor]: skills/dep-auditor/README.md
[goal-doc]: https://code.claude.com/docs/en/goal
[auto-mode-doc]: https://code.claude.com/docs/en/glossary#auto-mode
