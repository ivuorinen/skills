# doc-auditor

Verifies all documentation accuracy against the codebase and writes a structured findings report.

## When to Use

- "Audit the docs" / "find stale documentation" / "verify docs against code"
- "Is the documentation accurate?" / "find missing docs" / "run doc-auditor"
- Before a release, to confirm no docs describe removed or changed behavior
- After a significant refactor, to catch documentation that was not updated

**When NOT to use:**
- Full repository audit (code, tests, docs, config together) → use [nitpicker] in docs mode, which invokes doc-auditor and then extends the review
- Architecture pattern detection → use [arch-detector]

## What It Reads / Writes

| | |
|---|---|
| **Reads** | All documentation files (`**/*.md`, inline code comments, docstrings, examples); codebase for cross-reference; `docs/audit/arch-profile.md` (optional — improves architecture description accuracy) |
| **Writes** | `docs/audit/doc-findings.md` |

## How to Invoke

```
/doc-auditor
```

Run [arch-detector] first if the codebase has architecture documentation that needs accuracy checking against detected patterns.

## Documentation Scanned

- `README.md` files at all levels
- `docs/` directory contents
- `CONTRIBUTING.md`, `CHANGELOG.md`, and similar project-level docs
- Inline code comments and docstrings
- Example code blocks inside documentation
- Cross-references between documents (links, `See also:` sections)

## Finding Types

| Type | Description |
|------|-------------|
| **Stale** | Documentation describes behavior that has changed or been removed |
| **Missing** | No documentation exists for a public API, feature, or important behavior |
| **Incorrect** | Documentation contradicts the actual implementation |
| **Structural** | Broken links, missing sections, orphaned files |
| **Coverage** | Public API or CLI flag with no documented usage |
| **Cross-reference** | `See also:` or `Related:` link points to a nonexistent or wrong target |

## Severity Model

| Severity | Meaning |
|----------|---------|
| Critical | Documentation actively misleads users — describes behavior that does the opposite of what is implemented |
| High | Stale description of a removed or significantly changed behavior; missing docs for a critical path |
| Medium | Incomplete description that omits important constraints or parameters |
| Low | Minor inaccuracy, outdated example, or cosmetic structural issue |

## Fix Types

| Type | When applied |
|------|-------------|
| **Update** | Revise existing text to match current behavior |
| **Add** | Create missing documentation |
| **Remove** | Delete documentation for removed features |
| **Repair link** | Fix a broken cross-reference |
| **Correct example** | Fix code in documentation that does not compile or run |

## Single-Shot Behavior

```
1. If docs/audit/doc-findings.md exists: re-validate each OPEN finding
     - Resolved → move to Fixed (record date)
     - Was wrong → move to Invalid (record reason)
     - Still present → leave Open
2. Read docs/audit/arch-profile.md if present (improves architecture doc accuracy checks)
3. Scan all documentation against codebase
4. Add new findings (assign next available ID — never reuse IDs)
5. Write docs/audit/doc-findings.md
6. Ask: "Apply fixes? (a)ll  (c)ritical-and-high only  (n)o"
7. Ask: "Commit findings to git? (y/n)" — never commit silently
```

## Findings Format

```
# Documentation Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N

## Open Findings

### Critical

#### [DOC-NNN] Short title
Type: <stale|missing|incorrect|structural|coverage|cross-reference>
Area: path/to/doc.md:line (or inline at path/to/file.go:42)
Problem: <direct description>
Evidence: <quoted text from doc vs. actual behavior>
Impact: <why this matters>
Fix: <concrete remediation>
```

Finding ID format: `DOC-NNN` (zero-padded to 3 digits).

## Related Skills

- [arch-detector] — produces `docs/audit/arch-profile.md`; run before doc-auditor when architecture docs need checking
- [nitpicker] — docs mode invokes doc-auditor, then extends the review with inline comment and cross-reference analysis
- [claude-rules-auditor] — reads `docs/audit/doc-findings.md` as supplemental input

---

[skill-source]: SKILL.md
[arch-detector]: ../arch-detector/README.md
[nitpicker]: ../nitpicker/README.md
[claude-rules-auditor]: ../claude-rules-auditor/README.md
