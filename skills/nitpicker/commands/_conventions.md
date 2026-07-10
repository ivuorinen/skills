# Shared Conventions — binding for every /nitpicker command

Read this file before executing any command file. Every rule here applies to
every command unless the command file explicitly overrides it.

## Severity levels

| Level | Meaning |
| --- | --- |
| Critical | Correctness or security failure; must be fixed |
| High | Significant risk or defect |
| Medium | Quality or reliability concern |
| Low | Minor issue or smell |
| Advisory | Informational, no action required |

Severity reflects actual risk, never preference.

## Categories

`correctness` | `security` | `reliability` | `maintainability` | `performance` | `tests` | `docs` | `conventions`

## Execution

- **Run the command as a task list.** A command whose body defines a numbered
  Process or Procedure copies each step into the agent's task list before it
  begins — in Claude Code one `TaskCreate`/`TodoWrite` entry per step, the
  equivalent task tracker in other agents — and closes every step before
  reporting. No step may be silently dropped: an unexecuted step is a coverage
  gap, and silence means approval. The default `audit` command's
  `_audit-coverage.md` checklist is this rule's expanded, cross-command form.
- **Preflight every external tool.** Before invoking any external binary the
  skill does not itself ship — a scanner (`semgrep`, `opengrep`, `grype`,
  `trivy`, `gitleaks`, …), `gh`, a package manager, a linter or analyzer —
  probe its availability with `command -v` / `which`. Never install it. Run
  only the tools found. Record a missing tool as "not available" and a tool
  that ran but failed as "errored: <message>" in the run summary; capture
  stderr, never discard it. A missing or failed tool never aborts the run and
  never yields empty output presented as a clean result — the run continues
  with that tool recorded as uncovered. The skill's own bundled tools are
  stdlib-only and run with plain `python3`; if `python3` itself is absent,
  stop with a clear error rather than proceeding as though the tool ran clean.

## Findings store

Open findings live one file each under `docs/audit/findings/<auditor>/open/`
in the audited repository, where `<auditor>` is the command name; resolving a
finding appends a record to the append-only `docs/audit/findings/resolved.jsonl`
ledger and deletes the open file, so the tree never accumulates resolved files
and PR review stays readable. Drive the store only through this skill's bundled
`scripts/findings.py` — stdlib-only,
plain `python3`, no uv required. Resolve the tool path relative to this
skill's directory (Claude Code: `${CLAUDE_SKILL_DIR}/scripts/findings.py`;
below it is abbreviated `findings.py`):

```bash
python3 findings.py new --auditor <command> --severity high \
  --category security --area src/auth.py --body - "Short title" <<'EOF'
## Problem
...
## Evidence
...
## Impact
...
## Fix
...
EOF
python3 findings.py resolve <id> --status fixed --notes "what changed"
python3 findings.py list --status open
python3 findings.py validate
python3 findings.py index
```

Every finding file carries `## Problem`, `## Evidence`, `## Impact`, `## Fix`.
IDs are content-hashed by the tool — never invent or reuse IDs by hand.

Run protocol:

0. Pre-flight: if any file matching `docs/audit/*-findings.md` exists
   (the glob is authoritative; only `arch-profile.md` is exempt), that is
   a legacy v1 findings file and a **consent gate**: it blocks migration,
   never the audit itself. Ask the user whether to run
   `/nitpicker x-findings-migrator` now. Never migrate without an explicit
   per-run "yes" — **this question overrides autonomous/goal mode**;
   consent from an earlier session, an earlier run, or a memory file does
   not carry over. Silence, "no", or "later" all mean: record the pending
   migration in the run summary and continue in the v2 store without
   touching the v1 files **and without re-filing their contents into the
   v2 store** — copying v1 findings in by hand is migration and needs the
   same consent. The user decides _when_ migration happens; the agent
   never does.
1. At run start: `findings.py list --auditor <command> --status open` and
   re-validate each open finding against the current code — resolve as
   `fixed` (issue gone) or `invalid` (finding was wrong, say why), leave
   truly open ones open.
2. File new findings as they are confirmed, not at the end.
3. After filing: `findings.py index` to refresh `INDEX.md`.
4. Present a findings summary in the response.
5. If the command applies fixes: ask
   `Apply fixes? (a)ll  (c)ritical-and-high only  (s)afe — no refactors  (n)o`
   and fix in severity order (Critical first). This prompt overrides
   autonomous/goal mode — never apply fixes without presenting it. With no
   interactive user, default to `(n)o` and record the un-applied fixes in the
   run summary.
6. Ask "Commit findings to git? (y/n)" — never commit silently.

## Modifiers

These may appear anywhere in the instruction text after the command:

- **inline** — return findings in the response only; write nothing to
  `docs/audit/findings/`.
- **changed-files** (or "changed files only") — limit scope to modified files
  and their direct dependencies.

## Rules

- No compliments. No hedging without evidence — if it looks wrong, say it is
  wrong and prove it.
- Silence means approval: an unfiled finding is an accepted defect.
- Every finding includes evidence (a failing scenario, a quoted line, a
  measurement) and a concrete fix — never "consider refactoring".
- Prefer exact fixes over general advice; prefer failing scenarios over
  abstract warnings.
- Validate documentation against implementation and tests against actual
  behavior — never assume either is right.
- Do not weaken tests to make them pass. If a test fails after a fix, the
  fix is wrong.
- Do not introduce unnecessary abstractions, change public APIs without
  need, or introduce regressions.
- Out-of-scope defects are routed, not dropped: file one line naming the
  target command (e.g. "routes to `/nitpicker security`") in the response.

## Common mistakes

- Hedging without proof: if you cannot construct the failing scenario, do
  not file the finding.
- Filing a finding with no fix.
- Applying lower-severity fixes before Critical/High are done.
- Approving by omission during the pass, then adding findings later.
- Flagging style when content is correct.
