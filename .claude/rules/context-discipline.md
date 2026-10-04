---
paths:
  - "skills/nitpicker/SKILL.md"
  - "skills/nitpicker/commands/**"
  - "skills/nitpicker/scripts/context_pack.py"
  - "skills/nitpicker/scripts/check-context-tokens.py"
  - "skills/nitpicker/scripts/check-agent-instructions.py"
  - "tests/test_context_pack.py"
  - "tests/test_check_context_tokens.py"
---

# Context Discipline

`_conventions.md` carries only what binds every command. The shared protocols load on a
trigger instead — `_findings-store` before the first store operation,
`_committing` before a commit, `_documentation` before a fix or a `docs` finding,
`_audit-coverage` for `audit`. Each trigger is stated in `_conventions.md` and in
SKILL.md's execution order, and both are binding: a protocol not loaded is a
protocol not followed. Rules that hold in *every* run — the finding contract,
redaction, the migration consent gate, the run protocol's shape — stay in the
core file rather than moving with their protocol.

## The context firewall

`skills/nitpicker/scripts/context_pack.py` (MCP: `np_context_pack`) is the
portable context firewall. It answers with coordinates — path, line range,
enclosing symbol, why it matched — not with file bodies. Its modes are the
acquisition ladder: `inventory` (A), `symbols` and `diff` (B), `evidence` (C).
Level D is a direct read the caller performs after the pack narrows it. The
invariant the callers are held to: **compression may decide what to inspect
next; only original source may prove a finding.** `--self-test` runs the
known-positive controls, because a retriever returning nothing is otherwise
indistinguishable from a repository containing nothing.

## Measuring the budget

`skills/nitpicker/scripts/check-context-tokens.py` reports the size of the set
loaded on every turn and of one invocation. It is CLI-only and **cannot fail a
build**: its numbers are four-characters-per-token estimates, and gating on an
estimate turns an approximation into a rule nobody can reproduce. Read the
`--baseline` delta, not the absolute. `check-agent-instructions.py` remains the
directive-count gate; the two measure different halves of the same budget
(`.claude/rules/instruction-budget.md`).

## Enforcement

Partly gated. `tests/test_context_pack.py` holds the firewall's contract and
its self-test controls. Loading a protocol on its trigger, and proving a finding
from original source rather than a pack's summary, are agent discipline: no
check sees which files a run read.
