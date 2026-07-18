# skills

**Nitpicker** — a hostile audit toolkit for coding agents. One skill, one
entry point, a full deck of audit commands:

```text
/nitpicker <command> [extra instructions]
```

Assumes the code is incorrect until proven otherwise. Every command files
findings with evidence and a concrete fix — no compliments, no hedging.

Works in **Claude Code**, **GitHub Copilot**, **pi**, and any agent that
reads the open [Agent Skills](https://agentskills.io) format.

## Install

| Agent                                             | How                                                                                                                                                                |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Claude Code (plugin)                              | `/plugins` → add marketplace `ivuorinen/skills` → install `ivuorinen-skills`                                                                                       |
| Any agent via [skills.sh](https://www.skills.sh/) | `npx skills add ivuorinen/skills` (installs into the agent you pick)                                                                                               |
| GitHub Copilot                                    | `npx skills add ivuorinen/skills -a copilot`, or copy `skills/nitpicker/` into `.github/skills/` — Copilot also reads `.claude/skills/` and `.agents/skills/`      |
| pi                                                | `npx skills add ivuorinen/skills -a pi`, copy into `.agents/skills/`, or add the checkout to the `"skills": [...]` setting; invoke as `/skill:nitpicker <command>` |

The bundled tools (`skills/nitpicker/scripts/*.py`) are stdlib-only and run
with plain `python3` — no uv, no package installs on the consumer machine.

## Usage

```text
/nitpicker                       # exhaustive whole-repo audit (default)
/nitpicker security              # run the security scanners, consolidate findings
/nitpicker tests inline          # audit the test suite; findings in the response only
/nitpicker cr fix only critical  # implement PR review comments, scoped by your words
/nitpicker release-gate          # fail if any open finding ≥ High
/nitpicker help                  # print the command table
```

The first word after `/nitpicker` picks the command (old 1.x skill names
still work as aliases); everything after it is free-text instructions for
that run. The modifiers `inline` (nothing written to disk) and
`changed-files` (scope to modified files) work with every command.

## Commands

### Review and fixing

| Command            | What it hunts                                                                                          |
| ------------------ | ------------------------------------------------------------------------------------------------------ |
| _(none)_ / `audit` | Everything: code, tests, docs, config — the exhaustive review                                          |
| `review`           | Bugs in a diff or file set — logic errors, edge cases, missing tests                                   |
| `pr`               | PR defects; outputs copy-paste-ready GitHub review markdown                                            |
| `cr`               | Unresolved PR review comments — evaluates and implements the valid ones                                |
| `complexity`       | Over-engineering; forces the laziest solution that works                                               |
| `unwired`          | Implementations never wired in, or left incomplete; wires, merges, or removes with per-finding consent |

### Planning

| Command | What it does                                                                                                                                 |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `plan`  | Turns a change request into a plan hardened by the audit lenses; writes a plan doc and stops for explicit approval before any implementation |

### Learning

| Command | What it does                                                                                                      |
| ------- | ----------------------------------------------------------------------------------------------------------------- |
| `teach` | Teaches a skill or concept across sessions; builds a persistent `docs/lessons/` workspace — lessons, not findings |

### Security and data

| Command         | What it hunts                                                                    |
| --------------- | -------------------------------------------------------------------------------- |
| `security`      | Vulnerabilities, exposed secrets, insecure dependencies (via installed scanners) |
| `privacy`       | Personal data without the control its class requires                             |
| `config`        | Undocumented env vars, unsafe prod defaults, committed secrets                   |
| `iac`           | Container/IaC misconfig: root, open ingress, public stores, overbroad IAM        |
| `prompt-safety` | LLM-integration safety: prompt injection, model-output-to-sink, tool agency      |

### Runtime behavior

| Command       | What it hunts                                                          |
| ------------- | ---------------------------------------------------------------------- |
| `perf`        | N+1 queries, O(n²)+ hotspots, sync-blocking-in-async, unbounded growth |
| `concurrency` | Data races, TOCTOU, deadlock ordering, unsafe publication              |
| `errors`      | Swallowed exceptions, fail-open defaults, masking fallbacks            |
| `leaks`       | Resources acquired without guaranteed release on failure paths         |

### Structure and contracts

| Command        | What it hunts                                                                  |
| -------------- | ------------------------------------------------------------------------------ |
| `arch`         | Architectural violations against detected or declared patterns                 |
| `arch-profile` | Detects the architecture; writes `docs/audit/arch-profile.md`                  |
| `contract`     | Spec-vs-code drift and surface changes vs the declared semver bump             |
| `deps`         | Unused, phantom, duplicate, unmaintained, license-conflicting dependencies     |
| `license`      | Project license, dependency compatibility, copyleft contamination, attribution |
| `migrations`   | Migrations that eat production: destructive ops, long locks, drift             |

### Quality surfaces

| Command         | What it hunts                                                            |
| --------------- | ------------------------------------------------------------------------ |
| `tests`         | Tests that cannot fail: tautologies, mocked-out subjects, coverage holes |
| `types`         | Suppressed type errors, any-escapes, unsound casts, untyped boundaries   |
| `docs`          | Documentation that lies: stale, incorrect, missing                       |
| `contributing`  | `CONTRIBUTING.md` drift vs real tooling; offers to scaffold when absent  |
| `ci`            | Pipeline defects: unpinned actions, script injection, over-broad tokens  |
| `commits`       | Commit messages that mis-version the release vs their actual diffs       |
| `observability` | Dark paths, PII in logs, unfireable alerts, cardinality bombs            |
| `a11y`          | WCAG 2.2 AA violations computed from the actual UI code                  |
| `i18n`          | Hardcoded locale assumptions against the declared locale scope           |

### Coding-agent enforcement

| Command           | What it hunts                                                     |
| ----------------- | ----------------------------------------------------------------- |
| `agent-loopholes` | Bypassable constraints in the agent enforcement surface           |
| `agent-hooks`     | Recurring failures no hook guards; missing hook coverage          |
| `agent-rules`     | `.claude/rules/` quality and rules mined from project conventions |

### Meta

| Command        | What it hunts                                               |
| -------------- | ----------------------------------------------------------- |
| `baseline`     | Snapshots open findings as accepted; gate fails only on new |
| `release-gate` | Fails if any open finding at/above threshold (default High) |
| `help`         | Prints the command listing                                  |

Full command instructions: [`skills/nitpicker/commands/`](skills/nitpicker/commands/),
shared conventions in [`commands/_conventions.md`](skills/nitpicker/commands/_conventions.md).

## Findings store

Open findings live one file each; resolving one appends to an append-only
ledger and deletes the file, so audits scale, parallel worktrees never conflict
on a counter, and PR review is never buried under resolved-finding files:

```text
docs/audit/findings/
  INDEX.md                      # generated summary — never hand-edited
  resolved.jsonl                # append-only ledger of fixed/invalid findings
  .gitattributes                # marks the store linguist-generated (self-written)
  <auditor>/open/<id>.md        # one open finding per file
```

IDs are content-hashed (`security-1a2b3c4d`). The store is managed by the
bundled CLI:

```bash
python3 skills/nitpicker/scripts/findings.py list --status open
python3 skills/nitpicker/scripts/findings.py resolve <id> --status fixed --notes "…"
python3 skills/nitpicker/scripts/findings.py validate
python3 skills/nitpicker/scripts/findings.py index
```

### Migrating from 1.x

1.x wrote one `docs/audit/<skill>-findings.md` per skill. Run
`/nitpicker x-findings-migrator` (nitpicker also detects the old files
itself and asks before migrating — never mid-PR without your consent), or
convert manually:

```bash
python3 skills/nitpicker/scripts/findings.py migrate docs/audit/*-findings.md
git rm docs/audit/*-findings.md
```

Legacy IDs (`N-042`) stay valid. All 1.x skill invocations
(`/security-auditor`, `/test-auditor`, …) map to `/nitpicker <command>`
aliases — the `## Commands` tables in `skills/nitpicker/SKILL.md` list
every alias next to its command.

## MCP server

Installing the plugin registers a stdlib-only stdio MCP server (`nitpicker`)
that exposes skill introspection (`list_skills`, `read_skill`, `read_command`,
`list_commands`) and findings management (`list_findings`, `show_finding`,
`findings_index`, `validate_store`, `new_finding`, `resolve_finding`). See the
"MCP server" section of `skills/nitpicker/SKILL.md` for scope and the
non-interactive mutate contract.

## Development

```bash
make check     # validate skill + commands, rules, version sync, findings store, findings index, lint, format, tests, pre-commit
make list      # list the skill and its commands
make test      # pytest suite for the tooling
```

Repo conventions for agents working on this codebase: [`AGENTS.md`](AGENTS.md)
(shared), [`CLAUDE.md`](CLAUDE.md) (Claude Code),
[`.github/copilot-instructions.md`](.github/copilot-instructions.md) (Copilot).

Versioning is [SemVer](https://semver.org/) automated with
[release-please](https://github.com/googleapis/release-please) from
Conventional Commits (`feat:` minor, `fix:` patch, `feat!:` major).

## Credits

- `/nitpicker plan` adapts the brainstorm → plan → gated-execution model from
  [obra/superpowers](https://github.com/obra/superpowers) — the separation of
  planning from implementation, with explicit human sign-off before code is
  written — and hardens the plan with nitpicker's own adversarial audit lenses.
- `/nitpicker teach` adapts the stateful teaching-workspace model from
  [mattpocock/skills](https://github.com/mattpocock/skills) — mission-grounded
  learning, spaced retrieval-practice lessons, and learning records as ADRs —
  rewritten to this repo's command conventions with lessons under `docs/lessons/`.

## License

[MIT](LICENSE) © Ismo Vuorinen
