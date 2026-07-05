# ci-auditor

Hostile single-shot audit of a project's CI/CD pipeline definitions — GitHub Actions first-class, GitLab CI and other YAML pipelines by the same principles. Assumes every workflow is exploitable or silently non-gating until each file is checked against every defect class: unpinned actions, over-broad token permissions, script injection via untrusted interpolation, `pull_request_target`/`workflow_run` misuse, secrets leakage, non-gating checks, masked failures, missing concurrency, cache poisoning, and self-hosted runner exposure. Every finding cites file:line, the concrete attack or failure scenario, and the exact remediation — the SHA to pin, the permissions block to add, the interpolation to move into an env var.

## When to Use

- "Audit the CI" / "audit workflows" / "check GitHub Actions security" / "harden the pipelines"
- A new workflow was added or a trigger changed and you need to confirm it does not expose secrets or write tokens to untrusted code
- Before a release, to prove every merge-gating check actually gates and no failure passes green
- After a supply-chain incident in an action you use, to find every mutable reference

**When NOT to use:**
- Application-source vulnerabilities, dependency CVEs, committed secrets in the codebase → use [security-auditor]
- Agent-harness hooks and `.claude/settings.json` enforcement → use [hooks-enforcer] or [loophole-hunter]
- General code quality → use [nitpicker]

## ci-auditor vs. security-auditor vs. hooks-enforcer

| | ci-auditor | security-auditor | hooks-enforcer |
|---|---|---|---|
| Surface | Pipeline definitions (`.github/workflows/`, `.gitlab-ci.yml`, composite actions) | Application source, dependencies, git history | Agent-harness hooks (`.claude/settings.json`, hook scripts) |
| Question | "Can this pipeline leak secrets, run attacker code, or pass green while broken?" | "Does the codebase contain vulnerabilities, CVEs, or secrets?" | "What should be an agent hook and is not?" |
| Tools | actionlint, zizmor (when installed); `gh api` for gating | semgrep, grype, trivy, gitleaks, checkov, gosec, snyk, npm/yarn/pnpm audit | None — mines the project's own evidence base |
| Output | `docs/audit/ci-auditor-findings.md` | `docs/audit/security-findings.md` | `docs/audit/hooks-enforcer-findings.md` |

## What It Reads / Writes

| | |
|---|---|
| **Reads** | `.github/workflows/*.yml`, `.github/actions/**/action.yml`, `.gitlab-ci.yml` + includes, other pipeline YAML (azure-pipelines, CircleCI, Bitbucket, Drone, Woodpecker); actionlint/zizmor output when installed; branch protection and rulesets via `gh api` when authenticated |
| **Writes** | `docs/audit/ci-auditor-findings.md` |

## How to Invoke

```
/ci-auditor
```

Enumerates every pipeline file, runs installed analyzers (never installs anything), performs the manual defect-class sweep the analyzers cannot do, and verifies gating against branch protection — filing `Verification: Unverifiable` findings with the exact `gh api` command when unauthenticated.

## Defect Classes

| Class | Definition |
|-------|------------|
| **unpinned-action** | Third-party action on a mutable tag/branch instead of a full commit SHA |
| **excess-permissions** | Missing `permissions:` block, `write-all`, unused write scopes, tokens passed to untrusted steps |
| **untrusted-interpolation** | `${{ github.event.* }}` / `github.head_ref` expanded inside `run:` — script injection |
| **privileged-trigger-misuse** | `pull_request_target`/`workflow_run` executing fork code with secrets or a write token |
| **secrets-leakage** | Secrets echoed to logs, passed as CLI args (visible in `ps`), or uploaded in artifacts |
| **non-gating-check** | Gate-shaped workflow not required by branch protection/rulesets |
| **masked-failure** | `continue-on-error`/`\|\| true`/`set +e` letting a gating step pass green while broken |
| **missing-concurrency** | Deploy/release/publish workflow with no `concurrency:` group — parallel runs race |
| **cache-poisoning** | Cache keyed on untrusted input or shared across a privilege boundary |
| **runner-exposure** | Self-hosted runner reachable from fork PRs on a public repo |

## Findings Format

```
# CI Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N files unexamined)
- Files enumerated: N | examined: N
- Tool coverage: actionlint <available|not available> | zizmor <available|not available>
- Gating: N gate candidates | verified N | unverifiable N

## Open Findings

### Critical

#### [CI-NNN] Short title
Status: Open
Class: <unpinned-action|excess-permissions|untrusted-interpolation|privileged-trigger-misuse|secrets-leakage|non-gating-check|masked-failure|missing-concurrency|cache-poisoning|runner-exposure>
Area: <.github/workflows/file.yml:line>
Tool: <actionlint|zizmor|manual>
Problem: <what is wrong>
Evidence: <file:line and the concrete attack or failure scenario>
Impact: <what an attacker gains or what failure ships>
Fix: <the exact change — the SHA to pin, the permissions block, the env-var rewrite>
```

Finding ID format: `CI-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | Secret exfiltration or arbitrary code execution with a write-capable token reachable from a fork PR |
| High | Unpinned third-party action with secrets/write permissions in scope; write-all or missing permissions with third-party code; self-hosted runner reachable from forks; cross-privilege cache write |
| Medium | Masked failure on a gating check; verified non-gating gate; missing concurrency on a deploy; unpinned action with read-only token and no secrets |
| Low | Missing concurrency on non-mutating CI; non-gating-check filed as Unverifiable |
| Advisory | Unpinned first-party `actions/*`; hardening with no current attack path |

## Related Skills

- [security-auditor] — scans the application source and dependencies; this skill scans the pipelines that build them
- [hooks-enforcer] — audits agent-harness hook coverage; this skill audits CI/CD workflow definitions
- [loophole-hunter] — audits the Claude Code enforcement surface for evasion
- [nitpicker] — exhaustive repository audit across code, tests, docs, and config

---

[security-auditor]: ../security-auditor/README.md
[hooks-enforcer]: ../hooks-enforcer/README.md
[loophole-hunter]: ../loophole-hunter/README.md
[nitpicker]: ../nitpicker/README.md
