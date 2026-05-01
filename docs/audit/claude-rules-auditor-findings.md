# Claude Rules Audit Findings
Generated: 2026-05-01
Last validated: 2026-05-01

## Summary
- Rules files audited: 4
- CLAUDE.md files audited: 1
- Validation errors: 0 | Misplaced rules: 0 | Redundant rules: 0 | Suggestions: 0 | Invalid: 2

## Open Findings

(none)

## Fixed

### Pass 1 — 2026-05-01

#### [CRA-005] Implicit `uv run` convention not captured as a rule
Fixed: 2026-05-01
Notes: Created `.claude/rules/use-uv-runner.md` mandating `uv run --quiet` for all script invocations and requiring the `#!/usr/bin/env -S uv run --quiet` shebang on new scripts.

#### [CRA-002] Frontmatter format rules should be path-scoped
Fixed: 2026-05-01
Notes: Created `.claude/rules/skill-format.md` with `paths: ["skills/**/SKILL.md", ".claude/skills/**/SKILL.md"]` so the frontmatter mandates only load when Claude reads a SKILL.md file.

#### [CRA-001] `.claude/rules/` absent; CLAUDE.md contained 9 atomic behavioral rules
Fixed: 2026-05-01
Notes: Created `.claude/rules/` with four files: `skill-format.md` (path-scoped, mandates 1–5), `skill-lifecycle.md` (mandate 6), `skill-style.md` (mandates 7–9), `use-uv-runner.md` (CRA-005). Removed all nine mandates from CLAUDE.md: deleted the `### Description authoring rules` subsection, softened the "Body-only; avoid it" sentence, removed "Do not skip phases" from the new-skill steps, and replaced the Conventions Observed bullet list with a pointer to the rules files.

## Invalid

### Pass 1 — 2026-05-01

#### [CRA-004] `security-findings.md` absent
Notes: Incorrectly moved to Fixed — the artifact is still absent, no violation to remediate. Advisory suggestion only. Re-run `/claude-rules-auditor` after `/security-auditor` to extract rule candidates.

#### [CRA-003] `arch-profile.md` absent
Notes: Incorrectly moved to Fixed — the artifact is still absent, no violation to remediate. Advisory suggestion only. Re-run `/claude-rules-auditor` after `/arch-detector` to extract rule candidates.
