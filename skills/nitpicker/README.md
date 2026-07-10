# nitpicker

Hostile audit toolkit: one skill dispatching a categorized deck of commands.

```text
/nitpicker <command> [extra instructions]
```

No command → exhaustive whole-repository audit. First word picks the command
(1.x skill names work as aliases); the rest is free-text instructions for
that run. In pi, invoke as `/skill:nitpicker <command> …`; in Copilot,
`/nitpicker <command> …` in the prompt.

## Layout

| Path                             | Purpose                                                                            |
| -------------------------------- | ---------------------------------------------------------------------------------- |
| `SKILL.md`                       | The router: dispatch rules + the authoritative command table                       |
| `commands/_conventions.md`       | Shared severity levels, findings protocol, rules — binds every command             |
| `commands/<command>.md`          | Full instructions for one command                                                  |
| `scripts/findings.py`            | Findings store CLI (new/resolve/list/show/validate/index/migrate/migrate-resolved) |
| `scripts/fetch-pr-comments.py`   | Used by `cr` — unresolved PR review threads via GraphQL                            |
| `scripts/process-sarif.py`       | Used by `security` — SARIF parsing and dedup                                       |
| `scripts/check-rules-anatomy.py` | Used by `agent-rules` — rule-file anatomy checks                                   |

All scripts are stdlib-only and run with plain `python3` — no uv or package
installs required on the host.

## Reads / Writes

|        |                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reads  | The audited repository; the findings store                                                                                                                                                                                                                                                                                                                                                                     |
| Writes | `docs/audit/findings/<auditor>/open/<id>.md` (open findings), the append-only `docs/audit/findings/resolved.jsonl` ledger (resolved findings), the generated `docs/audit/findings/INDEX.md`, and a self-written `docs/audit/findings/.gitattributes`; `arch-profile` writes `docs/audit/arch-profile.md`; `pr` and `complexity` write to stdout only; `cr` presents results inline and writes no findings file |

Modifiers accepted by every command: `inline` (respond only, write nothing),
`changed-files` (scope to modified files + direct dependencies).

## Severity

Critical | High | Medium | Low | Advisory — defined in
`commands/_conventions.md`. `release-gate` fails on any open finding at or
above its threshold (default High).
