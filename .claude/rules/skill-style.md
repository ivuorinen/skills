---
paths:
  - "skills/**/SKILL.md"
  - ".claude/skills/**/SKILL.md"
---

# Skill Writing Style

Write skills as hostile, deterministic agents. No hedging language, no compliments. These words are banned outright:

```text
might   could   potential   consider
```

Every finding must include evidence and a concrete fix. Output destinations are explicit: stdout, or the findings store via `findings.py` (`docs/audit/findings/<auditor>/`).
Enumerate severity levels and checklists — or, for a skill that emits ranked one-line findings instead of severities, define the exact deterministic sort key and tie-break order down to a total order (for example: most code deleted first, then lower replacement rung, then file location). Never leave either to interpretation.
Silence = approval: if a finding is not filed, that is implicit acceptance.
