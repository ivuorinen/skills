---
name: ci-auditor
description: 'Hostile single-shot audit of CI/CD pipeline definitions (GitHub Actions first-class; GitLab CI and other YAML pipelines by the same principles) for unpinned actions, over-broad token permissions, script injection, privileged-trigger misuse, secrets leakage, non-gating checks, masked failures, missing concurrency, cache poisoning, and self-hosted runner exposure. Use when auditing or hardening CI/CD pipelines. Triggers: "audit the CI", "audit workflows", "check GitHub Actions security", "run ci-auditor".'
---

# CI Auditor

## Overview

Hostile audit of a project's CI/CD pipeline definitions. It assumes every workflow is exploitable or silently non-gating until each file is checked against every defect class. It enumerates every pipeline file, runs installed analyzers (actionlint, zizmor) when present — never installing anything — then performs the manual sweep the analyzers cannot do: permissions semantics, gating verification against branch protection, trigger/privilege interaction, and failure masking. Every finding cites file:line, the concrete attack or failure scenario, and the exact remediation — the SHA to pin, the permissions block to add, the interpolation to move into an env var. Writes `docs/audit/ci-auditor-findings.md`. Single-shot: re-validate existing findings, enumerate, scan, file new findings, optionally fix, re-validate.

## When to Use

- Auditing `.github/workflows/`, composite actions, `.gitlab-ci.yml`, or other pipeline YAML for security and reliability defects
- A new workflow was added or a trigger changed and you need to confirm it does not expose secrets or write tokens to untrusted code
- Before a release, to prove every merge-gating check actually gates and no failure passes green
- When asked to "audit the CI", "check GitHub Actions security", "harden the pipelines", or "run ci-auditor"

**When NOT to use:** For application-source vulnerabilities, dependency CVEs, or committed secrets in the codebase, use `security-auditor`. For agent-harness hooks and `.claude/settings.json` enforcement, use `hooks-enforcer` or `loophole-hunter`. For general code quality, use `nitpicker`.

## Process

```
0. Re-validate existing findings
   If docs/audit/ci-auditor-findings.md exists, re-validate each finding with Status: Open:
   - Defect no longer present at the cited location (re-check the file:line) → move to Fixed
   - Finding was wrong, or the user marks it false positive → move to Invalid (record reason)
   - Still present → leave Open (Unverifiable findings stay Open until verified)
1. Enumerate pipeline files
   .github/workflows/*.{yml,yaml}, .github/actions/**/action.{yml,yaml} (composite
   actions), .gitlab-ci.yml plus every `include:` target, azure-pipelines.yml,
   .circleci/config.yml, bitbucket-pipelines.yml, .drone.yml, .woodpecker.yml,
   .woodpecker/*.yml, .woodpecker/*.yaml. When unsure
   whether a YAML file defines a pipeline, examine it — "unrecognized" is not "absent".
   Record the count. Every enumerated file is examined against every defect class —
   never sample. A run with unexamined files has verdict INCOMPLETE.
2. Run installed analyzers
   Probe with `command -v actionlint` and `command -v zizmor`. Run each tool found
   (`actionlint -format '{{json .}}'`; `zizmor --pedantic --format json .` — the repository
   root discovers both workflows and composite actions); record a missing tool
   as "Not available" and a crashed tool as "Errored: <message>" in the Summary — a
   tool failure never aborts the run. Never install a tool. Parse tool output into
   findings, deduplicating on file + line + class; list every source under Tool:.
   Tool output supplements the manual sweep in step 3 — it never replaces it: neither
   tool verifies gating, permissions semantics, or concurrency intent.
3. Manual defect-class sweep
   Check every enumerated file against every class in the Defect Classes table. Read
   each `run:` block, `permissions:` block, trigger, `env:` indirection, and composite
   action input end-to-end — grep alone misses env-var indirection and composite inputs.
4. Verify gating
   A gate candidate is any workflow triggered on pull_request/merge_request whose jobs
   run tests, linters, builds, or validators. Zero candidates in a repo that has such
   workflows is a misclassification, not a pass. Run
   `gh auth status`; if authenticated, verify each candidate is required via
   `gh api repos/{owner}/{repo}/branches/{branch}/protection --jq '.required_status_checks.checks[].context'`
   and `gh api repos/{owner}/{repo}/rulesets`. A gate-shaped workflow not listed as
   required is a non-gating-check finding. If unauthenticated or the API returns
   401/403/404, file the finding with `Verification: Unverifiable` and the exact
   command above for the user to run — never skip gating, and never mark it verified.
   On a non-GitHub host, verify via that host's protected-branch API (e.g. `glab api
   projects/:id/protected_branches`) or file Unverifiable with that host's command.
5. File findings
   Assign the next CI-NNN id. Every finding records class, Evidence (file:line plus the
   concrete attack or failure scenario), Impact, and Fix (the exact remediation: the
   resolved commit SHA to pin, the permissions block to add, the env-var rewrite).
   No finding without a scenario; no fix without the exact change.
6. Write docs/audit/ci-auditor-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.
7. Present summary — run verdict (COMPLETE only if every enumerated file was examined
   and every gate candidate verified or filed Unverifiable), tool coverage, counts by
   severity — then ask: "Apply fixes? (a)ll  (c)ritical-and-high only  (s)afe  (n)o"
   - (a)ll / (c)ritical-and-high only: apply the matching Auto-applicable fixes.
   - (s)afe: apply only SHA pinning and env-var interpolation rewrites.
   Apply in severity order (Critical first). After each fix, re-check the cited
   location and re-run the analyzers on the changed file; move confirmed fixes to Fixed.
8. Commit gate
   Fix edits to workflow files are left in the working tree unstaged — never stage or
   commit them silently. Then ask: "Commit findings to git? (y/n)" and, on yes, stage
   only docs/audit/ci-auditor-findings.md.
```

### Defect Classes

| Class | What to flag | Fix shape |
|-------|--------------|-----------|
| **unpinned-action** | Third-party action referenced by mutable tag or branch (`uses: owner/repo@v4`, `@main`) instead of a full commit SHA | Resolve the tag (`gh api repos/{owner}/{repo}/git/ref/tags/{tag}` or `git ls-remote`) and pin `@<sha> # vX.Y.Z`. First-party `actions/*` unpinned is Advisory |
| **excess-permissions** | No `permissions:` block (repo default applies, write-all on older repos); `write-all`; write scopes a job does not use; `GITHUB_TOKEN` or PAT passed to an untrusted or third-party step | Top-level `permissions: contents: read`; per-job additions only for scopes that job provably uses |
| **untrusted-interpolation** | `${{ github.event.* }}`, `github.head_ref`, or other attacker-controlled context expanded inside `run:`, `script:`, or a composite action's shell — directly or via a composite input | Move the expression into `env:` and reference the quoted variable (`"$VAR"`) in the script |
| **privileged-trigger-misuse** | `pull_request_target` or `workflow_run` that checks out or executes fork-PR code (`ref: github.event.pull_request.head.sha`, `merge.ref`) with secrets or a write token in scope | Split: unprivileged `pull_request` builds; privileged job never executes fork code, or gates on a trusted label after review |
| **secrets-leakage** | Secret echoed or printed to logs (including base64/transformed — masking misses encodings); passed as a CLI argument (visible in `ps` and shell traces); written into an uploaded artifact; exported into `GITHUB_ENV` | Pass via `env:` into stdin or a config file with restricted mode; strip from artifacts; rotate any secret already exposed |
| **non-gating-check** | A workflow that reads as a merge gate but is not a required status check in branch protection/rulesets (verified per Process step 4) | Add the job's check name to required status checks; record the exact `gh api` verification command in the finding |
| **masked-failure** | `continue-on-error: true`, `\|\| true`, `set +e`, or an ignored exit code on a step whose failure is the signal — the check passes green while broken | Remove the mask; where one matrix leg is genuinely experimental, scope `continue-on-error` to that leg via a matrix flag and record the justification in the finding |
| **missing-concurrency** | Deploy, release, publish, or state-mutating workflow with no `concurrency:` group — parallel runs race | `concurrency: { group: <workflow>-${{ github.ref }}, cancel-in-progress: false }` for deploys; `true` for superseded CI runs |
| **cache-poisoning** | Cache key derived from attacker-controlled input; cache written by an untrusted (fork/PR) context and restored in a privileged one (branch protection does not isolate caches) | Key on lockfile hashes; separate cache namespaces per privilege boundary; never restore a PR-written cache in a release job |
| **runner-exposure** | `runs-on: self-hosted` (or a self-hosted label) in a public repo on a workflow reachable from fork PRs — fork code executes on your infrastructure | GitHub-hosted runners for fork-reachable workflows; self-hosted only behind `pull_request_target`-free, contributor-gated triggers or in private repos with ephemeral runners |

## Findings Format

Output path: `docs/audit/ci-auditor-findings.md`

```
# CI Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N files unexamined)
- Files enumerated: N | examined: N
- Tool coverage: actionlint <available|not available> | zizmor <available|not available>
- Gating: N gate candidates | verified N | unverifiable N (gh unauthenticated)
- Unexamined: <file path> — <why not examined>

## Open Findings

### Critical

#### [CI-NNN] Short title
Status: Open
Class: <unpinned-action|excess-permissions|untrusted-interpolation|privileged-trigger-misuse|secrets-leakage|non-gating-check|masked-failure|missing-concurrency|cache-poisoning|runner-exposure>
Area: <.github/workflows/file.yml:line>
Tool: <comma-separated sources — actionlint, zizmor, manual>
Verification: <Verified|Unverifiable — run: gh api ...>   (non-gating-check findings only)
Problem: <what is wrong>
Evidence: <file:line and the concrete attack or failure scenario>
Impact: <what an attacker gains or what failure ships>
Fix: <the exact change — the SHA to pin, the permissions block, the env-var rewrite>

### High
[same structure — repeat for Medium, Low, Advisory]

## Fixed

### Pass N — YYYY-MM-DD

#### [CI-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <what changed and the re-check that confirms the defect is gone>

## Invalid

### Pass N — YYYY-MM-DD

#### [CI-NNN] Short title
Notes: <why the scenario does not apply>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the other `## Summary` bullets after it. Keep the Total line in exactly that shape and insert no field between `Total:` and `Invalid:`. All fixed findings live under one `## Fixed` h2 and all invalid findings under one `## Invalid` h2, sub-divided by `### Pass N — YYYY-MM-DD` h3 headers — never `## Fixed — pass N` variants. Unexamined files live as `Unexamined:` Summary bullets, never in a separate section.

Finding ID format: `CI-NNN` (zero-padded to 3 digits). Assign sequentially from the highest existing ID; never reuse an ID, even after a finding moves to Fixed or Invalid. On moving a finding to Fixed or Invalid, drop the `Status:` line. Never print an actual secret value in a finding — redact to first 4 + last 4 characters with `***` between (values of 8 characters or fewer become `[REDACTED]`).

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | Secret exfiltration or arbitrary code execution with a write-capable token reachable from a fork PR: privileged-trigger-misuse executing fork code with secrets; untrusted-interpolation in a workflow with write permissions or secrets in scope; secret printed to a public log or artifact |
| High | Unpinned third-party action in a workflow with secrets or write permissions; write-all or missing permissions on a workflow running third-party code; untrusted-interpolation without secrets in scope; self-hosted runner reachable from fork PRs; cache written across a privilege boundary |
| Medium | Masked failure on a gating check; gate-shaped workflow verified as not required; missing concurrency on a deploy or release workflow; unpinned third-party action with read-only token and no secrets |
| Low | Missing concurrency on non-mutating CI; non-gating-check filed as Unverifiable |
| Advisory | Unpinned first-party `actions/*`; hardening with no current attack path (e.g. adding `persist-credentials: false` where the token is already read-only) |

## Fix Strategy

**Auto-applicable (ask first, apply only on approval):**
- Pin an action: resolve the tag's current commit SHA and rewrite to `@<sha> # vX.Y.Z`
- Add a least-privilege `permissions:` block (top-level `contents: read`, per-job additions)
- Rewrite untrusted interpolation into an `env:` variable, quoted in the script
- Add a `concurrency:` group to a deploy/release workflow

**Requires explicit approval per change:**
- Changing a trigger (`pull_request_target` → `pull_request`, splitting privileged jobs)
- Removing `continue-on-error` / `|| true` (the failure it unmasks surfaces immediately)
- Restructuring cache keys or namespaces
- Moving a workflow off self-hosted runners

**Never auto-apply:**
- Branch protection or ruleset changes via API — provide the exact `gh api` command, the user runs it
- Secret rotation — name the exposed secret and instruct rotation; rotation is the user's action
- Weakening any existing control (removing a permissions block, unpinning) to resolve a finding
- Committing anything silently

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"The action is popular, so the tag is safe."** Popularity is not immutability. A mutable tag is retargeted the moment the maintainer's account or repo is compromised, and every consumer runs the new code with their secrets on the next trigger. Pin by commit SHA; the tag stays readable in the `# vX.Y.Z` comment.

**"This is a private repo, so injection doesn't matter."** Private repos have multiple contributors, compromised dependencies, and tokens that reach other repos and clouds. Injection in a private repo is lateral movement, not a non-issue. File it at the severity the token scope earns.

**"actionlint passed, so the workflows are fine."** actionlint checks syntax and expression types; zizmor checks known template weaknesses. Neither verifies that a check gates merges, that permissions match what a job uses, or that concurrency protects a deploy. Tool output feeds step 3; it never replaces it.

**"I can't check branch protection without auth, so I'll skip gating."** Unverifiable is a finding state, not a skip. File every gate candidate with `Verification: Unverifiable` and the exact `gh api` command the user runs to verify. Silence on gating is approval of a check that gates nothing.

**"Pinning by SHA is unreadable — tags are fine."** The `@<sha> # vX.Y.Z` form is exactly as readable as the tag and is immutable. Readability is an argument for the comment, not against the pin.

**"The workflow is only triggered manually, so it's out of scope."** `workflow_dispatch` inputs are attacker-influenced data interpolated into `run:` blocks, the run still holds tokens and secrets, and triggers get added later without the body being re-reviewed. Every enumerated file is in scope regardless of trigger.

**"GitHub masks secrets automatically, so echoing them is harmless."** Masking matches the literal registered value. Base64, hex, split, or otherwise transformed secrets print in the clear, CLI arguments are visible in `ps` and `set -x` traces, and artifacts are not masked at all. Every secret that reaches a log, argument list, or artifact is a finding.

**"continue-on-error is obviously intentional here."** Intent is proven, not assumed. A genuinely experimental matrix leg is scoped via a matrix flag and the justification is recorded in the finding; an unscoped mask on a gating step is a masked-failure finding every time.

**"Grep for `${{ github.event` and injection is covered."** Attacker-controlled context also flows through `env:` indirection, composite action inputs, `github.head_ref`, and `pull_request.title`. Step 3 reads each `run:` block and composite action end-to-end; a grep is not a sweep.

**"There are thirty workflows; I'll audit the ones that matter."** The workflow nobody reads is where the unpinned action and the write-all token live. Every enumerated file is examined against every class; a run that samples has verdict INCOMPLETE and says so — it never presents a subset as complete.

**"I described the fix, so the finding is handled."** A described fix is an Open finding. A finding moves to Fixed only after the change is applied and the cited location re-checked (and the analyzers re-run on the changed file) in step 7.
