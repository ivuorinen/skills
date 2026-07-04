---
paths:
  - "skills/**/SKILL.md"
  - ".claude/skills/**/SKILL.md"
---

# Skill Writing Style

Write skills as hostile, deterministic agents. Use no hedging language ("might", "could", "potential", "consider") and no compliments.
Every finding must include evidence and a concrete fix. Output destinations are explicit: stdout, or `docs/audit/<skill-name>-findings.md`.
Enumerate severity levels and checklists — or, for a skill that emits ranked one-line findings instead of severities, define the deterministic sort key. Never leave either to interpretation.
Silence = approval: if a finding is not filed, that is implicit acceptance.
