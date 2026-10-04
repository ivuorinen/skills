---
paths:
  - "skills/**/SKILL.md"
  - ".claude/skills/**/SKILL.md"
  - "scripts/validate-skill.py"
  - "tests/test_validate_skill.py"
---

# Agent Skills Spec Compliance

The normative format is the open spec at <https://agentskills.io/specification>.
`scripts/validate-skill.py` enforces it. Required: `name` (≤64 chars,
lowercase/digits/hyphens, no leading, trailing or consecutive hyphen, matching
its directory) and `description` (≤1024 chars). Optional: `license`,
`compatibility` (≤500 chars), `metadata` (a string→string map) and
`allowed-tools` (one space-separated string).

A top-level key outside that set is an **error**. Client-specific properties go
under `metadata`, which is what the spec designates it for. There is no
allowlist and no exemption; internal dev skills are held to the same rule. Body
size warns past 500 lines or ~5000 tokens, the progressive-disclosure
instructions tier.

`disable-model-invocation` therefore lives under `metadata` as `"true"`, quoted
because metadata values are strings. Claude Code reads that key from the top
level only, so under `metadata` it is inert and those skills become
model-invocable. That trade was accepted deliberately, buying portability.

Each skill's eval sets live in `<skill-dir>/evals/`, gated by `make
validate-evals`; `.claude/rules/skill-official-best-practices.md` describes
them.

## The reference validator

`make spec-check` cross-checks every skill against the Agent Skills reference
validator. It needs network access, so it sits outside `make check`;
`validate-skill.py` enforces the same constraints offline. Every skill passed at
the time of writing, internal dev skills included — re-run it rather than
trusting that, since a spec release can change the verdict.

Install traps, each hit once already:

- The PyPI package is `skills-ref`, but its console script is `agentskills`.
  The spec page still documents a `skills-ref` command, which no longer exists
  and exits 1 with no output.
- The identically-named npm package is unrelated to Anthropic.
- Failures print to stderr and successes to stdout, so merge stderr before
  judging a run clean.

## Enforcement

Gated. `scripts/validate-skill.py` runs under `make validate`, in pre-commit
and in CI, and fails on a frontmatter key or value outside the spec.
`make spec-check` is the network cross-check and gates nothing, since it sits
outside `make check`.
