---
name: claude-rules-auditor
description: Use when auditing .claude/rules/ files for quality and completeness, checking CLAUDE.md for rules that belong in .claude/rules/ instead, or discovering new rules from project conventions and audit artifacts.
---

# Claude Rules Auditor

## Overview

Audits the project's Claude Code rule configuration end-to-end. It validates every file in `.claude/rules/`, classifies every rule in CLAUDE.md as correctly placed or misplaced, and generates concrete suggestions for new rules by reading available audit artifacts and scanning project conventions. This skill assumes every rule file has defects until proven otherwise. It examines CLAUDE.md without assuming it is clean — absence of findings means the CLAUDE.md was reviewed and approved. It writes a findings report and asks before applying any migration or addition.

## When to Use

- `.claude/rules/` is absent and the project has a non-trivial CLAUDE.md
- CLAUDE.md has grown large and may contain rules that belong in `.claude/rules/`
- A `.claude/rules/` file is vague, covers too many topics, or duplicates another file
- You want to discover implicit rules from architectural, security, or code-quality audits
- Setting up or reviewing Claude Code configuration for a new or existing project

## Prerequisite Artifacts

These artifacts enrich rule suggestions. Run the corresponding skill before this one to maximize findings. If absent, this skill proceeds without them and records the gap as Advisory.

| Artifact | Prerequisite skill | Purpose |
|----------|--------------------|---------|
| `docs/audit/arch-profile.md` | `arch-detector` | Architectural boundary rules |
| `docs/audit/arch-findings.md` | `arch-auditor` | Violated conventions worth enforcing |
| `docs/audit/security-findings.md` | `security-auditor` | Security mandates from high-severity findings |
| `docs/audit/nitpicker-findings.md` | `nitpicker` | Code convention rules from repeated violations |

If no artifacts exist at all, run `arch-detector` first — it is the highest-yield single source for new rule suggestions.

## Process

```
1. Discovery
   a. Find all CLAUDE.md files in the project (root + any subdirectory)
   b. List all files under .claude/rules/ (record empty directory as a finding)
   c. Collect every available artifact from the Prerequisite Artifacts table
   d. Read .claude/settings.json, .claude/settings.local.json, and ~/.claude/settings.json
      for claudeMdExcludes patterns. Any .claude/rules/ file whose absolute path matches
      an exclusion glob is flagged Advisory: "Rule file exists but is excluded by
      claudeMdExcludes — Claude never loads it."

2. Validate existing .claude/rules/ files
   For each file found:
   - Filename must be kebab-case with .md extension
   - File may optionally begin with YAML frontmatter containing a `paths:` field (array
     of glob strings). This is valid and expected. Rules with `paths:` load only when
     Claude reads a file matching one of those globs — they do NOT apply to all files.
     Validate that every `paths:` value is a valid glob string (not an absolute path,
     not an empty string).
   - For each symlink in .claude/rules/, verify the target exists and is readable.
     A dangling symlink is a High finding: "Symlink target missing — rule file will not load."
   - File must contain exactly one focused rule topic; flag grab-bags.
     A grab-bag is a file whose rules require two or more distinct competency areas
     (e.g., version control behavior AND code style). A file covering only variations
     of a single behavioral domain (e.g., all git commands) is not a grab-bag.
   - Rules must be unconditional imperatives — no "try", "consider", "prefer", "might"
   - No duplicate mandates across files. "Duplicate" means same behavioral prohibition or
     mandate regardless of phrasing ("Never use grep" and "Use rg not grep" are duplicates).
   - No mandates that already appear in CLAUDE.md (redundant enforcement)
   - If a rule applies only to a specific file type or directory (e.g., "In TypeScript files,
     always use strict null checks"), suggest adding a `paths:` frontmatter to scope it
     rather than loading it unconditionally into every session.

3. Audit every CLAUDE.md
   For each CLAUDE.md file:
   - Count lines. Over 200 lines → Medium finding: "CLAUDE.md exceeds 200-line guideline;
     longer files reduce adherence. Move file-type-specific rules to path-scoped
     .claude/rules/ files or split to subdirectory CLAUDE.md files."
     Over 400 lines → High finding.
   - Scan for @-prefixed file imports (e.g., @docs/standards.md). Verify each imported
     file exists relative to the CLAUDE.md location. A missing import target is a
     Medium finding: "CLAUDE.md imports a file that does not exist — content silently absent."
   - Scan for block-level HTML comments (<!-- ... -->). Any behavioral rule found inside
     a comment is invisible to Claude at runtime. File a High finding: "Rule inside HTML
     comment is never loaded into context."
   For each line or block:
   - Classify as RULE (atomic behavioral mandate) or CONTEXT (workflow doc, setup, meta).
     Use the tiebreaker in Rule Classification Reference when borderline.
   - Flag each RULE not already in a .claude/rules/ file as MISPLACED
   - Flag each RULE already covered by a .claude/rules/ file as REDUNDANT
   - Never flag CONTEXT blocks — they belong in CLAUDE.md
   - When two CLAUDE.md files (e.g., root and subdirectory) contain the same rule with
     conflicting wording or opposite mandates, file a "Cross-file conflict" finding
     (High severity). A CLAUDE.md in a git submodule (has its own .git directory or is
     listed in .gitmodules) is out-of-scope; never flag or modify it. CLAUDE.md files in
     non-git subdirectories of the same repo are in-scope.

4. Extract rules from audit artifacts
   Extract only Critical and High severity findings from each artifact. Medium and below
   produce Advisory suggestions only. Apply these severity mappings per artifact:
   - arch-profile.md: extract boundary rules stated as absolutes (e.g., "controllers never
     import repositories directly"); skip descriptive observations about detected patterns
   - arch-findings.md: Critical/High → rule candidate; Medium and below → Advisory only
   - security-findings.md: Critical/High/Medium → rule candidate; Low/Advisory → Advisory only
   - nitpicker-findings.md: Critical/High → rule candidate; Medium and below → Advisory only

5. Scan the project for implicit conventions not yet captured anywhere
   - Directory naming and structural patterns → structural rules
   - Test file placement and naming conventions → testing rules
   - Import / dependency direction patterns → boundary rules
   - Repeated code constructs → code generation rules
   Limit: report only the top 3 most-repeated patterns per category. Cap total
   Advisory suggestions from this step at 10.

6. Write docs/audit/claude-rules-auditor-findings.md
   Update the "Last validated" date to today. "Generated" is the first-run date and
   must not change on subsequent runs.

7. Present summary: validation errors, misplaced rules, redundant rules, suggestions

8. For each MISPLACED rule: ask "Move to .claude/rules/<filename>.md? (y/n)"
   For each REDUNDANT rule: ask "Remove from CLAUDE.md? (mandate already in .claude/rules/) (y/n)"
   For each new suggestion: ask "Create .claude/rules/<filename>.md? (y/n)"
   Propose <filename> as the kebab-case topic of the rule (3 words max, no articles);
   e.g., "Never run git commit" → no-direct-commits.md.
   If there are 5 or more pending actions, offer a batch option first:
   "Apply all? (y)  Review individually? (r)  Skip all? (n)"
   Apply only approved changes — never modify files silently.
   If running non-interactively or no response is received, write all proposed changes
   under a "## Pending Approval" section in the findings report and halt. Do not apply
   any change without explicit per-change confirmation.
   After completing this step, re-write the findings file if any Pending Approval entries
   were added.
```

## Rule Classification Reference

**Move to `.claude/rules/`** — atomic behavioral mandates for Claude's conduct:
- "Never run `git commit` without explicit user instruction"
- "Use `rg` for code search, not `grep`"
- "Never use `--no-verify` with git hooks"
- "Always check `which <tool>` before using a tool"

**Keep in CLAUDE.md** — project context, workflow documentation, meta-instructions:
- Development commands and Makefile targets
- Architecture overview and skill routing tables
- Release workflow and versioning documentation
- Prerequisites, installation steps, and project background

Rule of thumb: if a statement answers "what should Claude always do in this project?" → `.claude/rules/`. If it answers "what is this project and how does it work?" → `CLAUDE.md`.

**User-level vs project-level:** If a rule is personal preference with no project-specific justification (e.g., "always use vim keybindings", "prefer dark theme output"), suggest `~/.claude/rules/` instead of `.claude/rules/`. User-level rules at `~/.claude/rules/` apply to every project on the machine. Project-level rules in `.claude/rules/` are committed and shared with the team.

**Compliance reliability:** CLAUDE.md is delivered as a user message after the system prompt — there is no strict compliance guarantee for vague or conflicting instructions. Security-critical and compliance mandates belong in `.claude/rules/` (dedicated context injection) rather than CLAUDE.md for more reliable enforcement.

**Tiebreaker for borderline cases:** If removing the statement would not change Claude's observable behavior during a conversation (only its understanding of the project), classify as CONTEXT. If removing it would allow a prohibited action to occur, classify as RULE. "Use semantic versioning" describes the project → CONTEXT. "Always run `make check` before committing" prescribes Claude's behavior → RULE.

## Good Rule File Anatomy

Two valid forms of a `.claude/rules/` file:

**Unconditional rule** (loaded in every session):
```markdown
# <Topic — imperative noun phrase>

Never <X>.
Always <Y>.
Use <tool-A>, not <tool-B>.
```

**Path-scoped rule** (loaded only when Claude reads a matching file):
```markdown
---
paths:
  - "src/**/*.ts"
  - "src/**/*.tsx"
---

Always add explicit return types to exported functions.
Never use `any` — use `unknown` and narrow it.
```

Each rule must be:
- **Specific**: "Use `rg` not `grep`" not "prefer better search tools"
- **Unconditional**: no "try to", "generally", "prefer", "consider", "when possible"
- **Testable**: a reviewer can check compliance from a conversation transcript
- **Scoped**: one topic per file; split grab-bags into separate files

The h1 title is a convention for readability; its absence is not a validation error.
Path-scoped rules trigger when Claude reads a matching file, not on every tool use — use them for language- or directory-specific mandates to avoid loading rules that don't apply.

## Findings Format

Output path: `docs/audit/claude-rules-auditor-findings.md`

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

#### [ID] Short title
Category: <validation|misplaced|redundant|conflict|suggestion>
Area: <file path>
Problem: <direct description>
Evidence: <the specific text or pattern>
Impact: <why this matters>
Fix: <concrete action — file to create, content to add, line to remove>

### High
[same structure]

### Medium
[same structure]

### Low
[same structure]

### Advisory
[same structure]

## Fixed

### Pass N — YYYY-MM-DD

#### [ID] Short title
Fixed: YYYY-MM-DD
Notes: <what changed>

## Invalid

### Pass N — YYYY-MM-DD

#### [ID] Short title
Notes: <why this finding was wrong>
```

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | `.claude/rules/` absent and CLAUDE.md contains 5 or more atomic behavioral rules; rule file with broken/unparseable content |
| High | `.claude/rules/` absent and CLAUDE.md contains 1–4 atomic behavioral rules; 3 or more misplaced rules in CLAUDE.md; contradictory duplicate rules across files; cross-file CLAUDE.md conflict; rule inside HTML comment (invisible to Claude); CLAUDE.md over 400 lines; dangling symlink in `.claude/rules/` |
| Medium | 1–2 misplaced rules; grab-bag rule file covering multiple unrelated topics; CLAUDE.md between 200–400 lines; missing @-import target in CLAUDE.md; invalid `paths:` glob in rule frontmatter |
| Low | Hedged rule language ("try to", "prefer"); non-kebab-case filename; rule that could be more specific; rules-to-rules duplicate without contradiction; unconditional rule that would be better path-scoped |
| Advisory | Suggested new rule from detected convention; no current violation; `.claude/rules/` absent and CLAUDE.md has no atomic behavioral rules; `.claude/rules/` exists but is empty; rule file excluded by `claudeMdExcludes`; project rule that would be better as a user-level rule in `~/.claude/rules/` |

## Fix Strategy

**Auto-applicable (ask first, apply only on approval):**
- Create `.claude/rules/<filename>.md` from a misplaced CLAUDE.md rule
- Remove the migrated rule from CLAUDE.md after the rules file is created
- Rename a non-kebab-case rule file to its correct kebab-case name

**Requires explicit approval per change:**
- Splitting a grab-bag file into multiple focused files
- Deleting a redundant rules file
- Any modification of existing CLAUDE.md content beyond removing a migrated rule

**Never auto-apply:**
- Deleting any file without explicit per-file confirmation
- Rewriting the semantic content of an existing rule
- Modifying a CLAUDE.md that belongs to a different project (nested repos)

## Common Mistakes

**Flagging CLAUDE.md workflow documentation as misplaced rules:** Development commands, skill routing tables, release workflows, and architecture overviews belong in CLAUDE.md. Only atomic behavioral mandates ("always", "never", "use X not Y") are candidates for migration.

**Creating a new rules file without checking existing .claude/rules/ first:** Before suggesting a new rule, verify no existing file covers the same mandate. Duplicates create contradictions when Claude loads both files.

**Misclassifying severity for absent .claude/rules/:** Use the Severity Guide exactly. Absence + 5+ atomic rules → Critical. Absence + 1–4 atomic rules → High. Absence + zero atomic rules → Advisory. Do not invent intermediate thresholds.

**Migrating a rule without removing it from CLAUDE.md:** A rule that lives in both places is a redundancy finding. Every migration must include removing the original.

**Flagging correctly-placed CLAUDE.md context as misplaced rules:** "The project uses semantic versioning" is project context, not a behavioral rule. Only statements that directly instruct Claude's conduct are candidates for migration.

**Skipping artifact collection because the skill "can detect enough on its own":** Audit artifacts (arch-profile.md, security-findings.md) surface violation-derived rules that static CLAUDE.md analysis will miss. If artifacts are absent, record this in the report under Advisory and instruct the user to run the prerequisite skills before the next pass.

**Applying changes without user confirmation:** This skill never creates, modifies, or deletes a file silently. Ask for each change individually.
