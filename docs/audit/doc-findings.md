# Documentation Audit Findings
Generated: 2026-04-26
Last validated: 2026-04-26

## Summary
- Total: 8 | Open: 0 | Fixed: 4 | Invalid: 4

## Open Findings

(none)

## Fixed

### Pass 1 — 2026-04-26

#### [D-001] N-002 fix notes claimed wrong action ref versions
Fixed: 2026-04-26
Notes: Updated N-002 notes in `docs/audit/nitpicker-findings.md` from "Reverted to `@v4`/`@v5`" to "SHA-pinned to `checkout@de0fac2e (v6.0.2)` and `setup-uv@08807647 (v8.1.0)`".

#### [D-002] doc-auditor mislabelled as Leaf in Skill Catalogue
Fixed: 2026-04-26
Notes: Changed doc-auditor role in `.claude/skills/README.md` Skill Catalogue from "Leaf" to "Consumer — verifies documentation accuracy against codebase; optionally reads `arch-profile.md`", consistent with its optional read of `arch-profile.md`.

#### [D-004] copilot-instructions.md made README.md update conditional
Fixed: 2026-04-26
Notes: Updated `.github/copilot-instructions.md` Adding a New Skill step 2 to state "Also update `README.md` (it always contains a mirrored skills table)" and added mention of `.claude/skills/README.md` update.

#### [D-008] CLAUDE.md step 4 omitted .claude/skills/README.md
Fixed: 2026-04-26
Notes: Added "also update the Skill Catalogue, Mermaid graphs, and Quick Reference in `.claude/skills/README.md`" to step 4 in `CLAUDE.md`.

## Invalid

### Pass 1 — 2026-04-26

#### [D-003] CLAUDE.md manual release flow missing Edit CHANGELOG.md step
Notes: CLAUDE.md line 92 already contains `# Edit CHANGELOG.md to add release notes` as a comment in the code block. The step is present; finding was wrong.

#### [D-005] WIRING.md release-prep diagram nitpicker release-gate claim
Notes: `.claude/skills/README.md` node I claims "nitpicker release-gate / threshold: High". `skills/nitpicker/SKILL.md` Modes table confirms this exactly. Claim is accurate.

#### [D-006] README.md arch-detector pattern and combination counts
Notes: `README.md` claims "19 patterns, 8 canonical combinations". `skills/arch-detector/SKILL.md` Individual Patterns table has exactly 19 rows; Combination Detection table has exactly 8 rows. Counts are accurate.

#### [D-007] .claude/skills/README.md New Skill Registration Checklist omits wiring doc update
Notes: Item 4 of the checklist already explicitly says "Add it to the Skill Catalogue table and all relevant Mermaid diagrams in this file (`.claude/skills/README.md`)". The wiring doc is not omitted. The gap was only in CLAUDE.md and copilot-instructions.md, addressed by D-008 and D-004.
