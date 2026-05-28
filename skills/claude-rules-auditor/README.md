# claude-rules-auditor

Audits `.claude/rules/` files for quality, checks `CLAUDE.md` files for misplaced rules, and suggests new rules based on project conventions and existing audit artifacts.

## When to Use

- "Audit rules" / "check .claude/rules" / "CLAUDE.md rules quality"
- After adding or modifying rule files, to verify they meet quality standards
- When CLAUDE.md files have accumulated inline guidance that should live in rules files
- Before a release, to ensure the rules library is consistent and actionable

**When NOT to use:**
- General codebase audit → use [nitpicker]
- Architecture violation check → use [arch-auditor]
- Documentation accuracy check → use [doc-auditor]

## What It Reads / Writes

| | |
|---|---|
| **Reads** | `.claude/rules/**` files; all `CLAUDE.md` files in the repo; `docs/audit/arch-findings.md`, `docs/audit/doc-findings.md`, `docs/audit/security-findings.md`, `docs/audit/nitpicker-findings.md` (all optional) |
| **Writes** | `docs/audit/claude-rules-auditor-findings.md` |

## How to Invoke

```
/claude-rules-auditor
```

Reads all rule files and CLAUDE.md files automatically. Audit artifacts are consumed if present — run the relevant audit skills first for richer suggestions.

## Prerequisite Artifacts (Optional)

Running these before claude-rules-auditor improves the suggestions output:

| Artifact | Produced by |
|----------|-------------|
| `docs/audit/arch-findings.md` | [arch-auditor] |
| `docs/audit/doc-findings.md` | [doc-auditor] |
| `docs/audit/security-findings.md` | [security-auditor] |
| `docs/audit/nitpicker-findings.md` | [nitpicker] |

## Rule Classification Reference

| Category | What it covers |
|----------|----------------|
| **validation** | Rule file fails structural checks (missing frontmatter, wrong format, broken paths) |
| **misplaced** | Guidance that belongs in a rule file but is inline in CLAUDE.md |
| **redundant** | Rule duplicates another rule or a default Claude behavior |
| **conflict** | Two rules contradict each other |
| **suggestion** | New rule recommended based on observed project conventions or audit findings |

## Good Rule File Anatomy

A well-formed rule file in `.claude/rules/`:

```markdown
---
paths:             # optional — scope to specific file globs
  - "src/**/*.ts"
---

# Rule Title

Imperative statement of what must always/never be done.
One sentence per rule. No hedging. No "consider" or "try to".
```

Rules flagged as violations typically:
- Are stated as preferences rather than requirements ("prefer X" instead of "always X")
- Contain vague language ("be careful about", "think about")
- Duplicate behavior Claude already exhibits by default
- Contradict another rule without a stated priority

## Process

```
0. If docs/audit/claude-rules-auditor-findings.md exists:
     Re-validate each OPEN finding:
     - Resolved → move to Fixed (record date)
     - Was wrong → move to Invalid (record reason)
     - Still present → leave Open
1. Discovery — enumerate all .claude/rules/*.md files
2. Validate each rule file structurally (frontmatter, path scoping, format)
3. Audit all CLAUDE.md files for inline guidance that belongs in rules files
4. Check for redundant or conflicting rules across all files
5. Read available audit artifacts; extract patterns suggesting new rules
6. Add new findings
7. Write docs/audit/claude-rules-auditor-findings.md
8. Ask: "Apply fixes? (y/n)"
9. Ask: "Commit findings to git? (y/n)" — never commit silently
```

## Findings Format

```
# Claude Rules Audit Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Rules files audited: N
- CLAUDE.md files audited: N
- Validation errors: N | Misplaced rules: N | Redundant rules: N | Suggestions: N

## Open Findings

### Critical

#### [CRA-NNN] Short title
Category: <validation|misplaced|redundant|conflict|suggestion>
Area: .claude/rules/filename.md
Problem: <direct description>
Evidence: <the specific text or pattern>
Impact: <why this matters>
Fix: <file to create, content to add, or line to remove>
```

Finding ID format: `CRA-NNN` (zero-padded to 3 digits, e.g. `CRA-001`). IDs are assigned sequentially and never reused.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | Rule file is structurally invalid; rule actively contradicts a requirement |
| High | Misplaced CLAUDE.md guidance that Claude cannot reliably follow without a rule file |
| Medium | Redundant rule that creates ambiguity; vague rule that cannot be enforced |
| Low | Minor formatting issue; rule that could be more precisely scoped |
| Advisory | Suggested new rule — not a defect, just an improvement opportunity |

## Related Skills

- [nitpicker] — full repository audit; `docs/audit/nitpicker-findings.md` feeds suggestions here
- [arch-auditor] — `docs/audit/arch-findings.md` feeds suggestions here
- [doc-auditor] — `docs/audit/doc-findings.md` feeds suggestions here
- [security-auditor] — `docs/audit/security-findings.md` feeds suggestions here

---

[skill-source]: SKILL.md
[nitpicker]: ../nitpicker/README.md
[arch-auditor]: ../arch-auditor/README.md
[doc-auditor]: ../doc-auditor/README.md
[security-auditor]: ../security-auditor/README.md
