# /nitpicker agent-rules — Rules Auditor

Audits the project's agent rule configuration end-to-end: validates every rule file, classifies every rule in the root instruction file as correctly placed or misplaced, and generates concrete new-rule suggestions from audit artifacts and project conventions. Assume every rule file has defects until proven otherwise.

## When to use

- The project has a non-trivial root instruction file and no rules directory
- The root instruction file has grown large and may hold rules belonging in a rules directory
- A rule file is vague, covers too many topics, or duplicates another file
- You want to discover implicit rules from architectural, security, or code-quality audits
- Setting up or reviewing coding-agent configuration for a new or existing project

Not for enforcement bypasses — whether rules and hooks actually bind is `/nitpicker agent-loopholes`. Not for missing hook coverage — that is `/nitpicker agent-hooks`.

## Harness scope

The audited project's agent is not knowable in advance, so this command names
surfaces by role and resolves each against whatever the project actually keeps.
Detect by presence; a project serving several agents at once has all of them,
and every one is in scope.

| Role | Where it lives |
| --- | --- |
| **Root instruction file** — loaded every turn, read start to finish | `CLAUDE.md`, `AGENTS.md`, `.claude/CLAUDE.md`, `.cursorrules`, `.windsurfrules`, `.clinerules` (file form), `GEMINI.md`, `.rules`, `CONVENTIONS.md`, `.continuerules` |
| **Rules directory** — one file per rule, loaded on demand or by path scope | `.claude/rules/`, `.cursor/rules/` (`.mdc`), `.windsurf/rules/`, `.github/instructions/`, `.clinerules/` (directory form) |

`AGENTS.md` is the cross-agent convention: near enough every harness reads it,
so it co-loads with all of the above rather than belonging to any one of them.

Where a step below names a Claude Code path, read it as the example of its role,
not the only file that fills it. The two genuinely Claude-only surfaces are
marked as such where they appear: `claudeMdExcludes` and `.claude/settings.json`.

## Prerequisite artifacts

These enrich rule suggestions. Run the corresponding command before this one to maximize findings. If absent, proceed without them and record the gap as Advisory.

| Artifact | Prerequisite command | Purpose |
| --- | --- | --- |
| `docs/audit/arch-profile.md` | `/nitpicker arch-profile` | Architectural boundary rules |
| Findings store, `arch` auditor key | `/nitpicker arch` | Violated conventions worth enforcing |
| Findings store, `security` auditor key | `/nitpicker security` | Security mandates from high-severity findings |
| Findings store, `audit` auditor key | `/nitpicker audit` | Code convention rules from repeated violations |

If no artifacts exist at all, run `/nitpicker arch-profile` first — it is the highest-yield single source for new rule suggestions.

## Process

1. Discovery
   - Find every root instruction file in the project (root + any subdirectory), per the Harness scope table.
   - If no rules directory exists, or every one found is empty, record this as a finding and continue.
   - Collect every available artifact from the Prerequisite Artifacts table
     (`np_list_findings` with `auditor: <name>`, else
     `findings.py list --auditor <name>`, for store-backed artifacts).
   - Claude Code only: read `.claude/settings.json`, `.claude/settings.local.json`
     and `~/.claude/settings.json` for `claudeMdExcludes` patterns. Any rule file
     whose absolute path matches an exclusion glob is flagged Advisory: "Rule
     file exists but is excluded by claudeMdExcludes — never loaded." Skip this
     where the project has no Claude Code configuration; a rules directory for
     another harness has no equivalent exclusion mechanism.
2. Validate every existing rule file. For each file:
   - Filename must be kebab-case, with the extension its directory uses
     (`.md` everywhere except `.cursor/rules/`, which uses `.mdc`).
   - Optional YAML frontmatter with a `paths:` field (array of glob strings) is
     valid and expected — such rules load only when a matching file is read, not
     in every session. Validate every `paths:` value is a valid glob string (not
     an absolute path, not empty).
   - For each symlink, verify the target exists and is readable. A dangling
     symlink is a High finding: the rule file will not load.
   - File must contain exactly one focused rule topic; flag grab-bags. A grab-bag
     requires two or more distinct competency areas (e.g. version control AND
     code style). Variations of a single behavioral domain (all git commands) are
     not a grab-bag.
   - Rules must be unconditional imperatives — no "try", "consider", "prefer", "might".
   - No duplicate mandates across files. "Duplicate" means the same behavioral
     prohibition or mandate regardless of phrasing ("Never use grep" and "Use rg
     not grep" are duplicates).
   - No mandates that already appear in CLAUDE.md (redundant enforcement).
   - If a rule applies only to a specific file type or directory, suggest a
     `paths:` frontmatter to scope it instead of loading it unconditionally.
3. Audit every CLAUDE.md. For each file:
   - Count lines. Over 200 → Medium finding (longer files reduce adherence; move
     file-type-specific rules to path-scoped `.claude/rules/` files or split to
     subdirectory CLAUDE.md files). Over 400 → High.
   - Scan for @-prefixed file imports (e.g. `@docs/standards.md`) and verify each
     target exists relative to the CLAUDE.md. Missing target → Medium finding:
     content silently absent.
   - Scan for block-level HTML comments. A behavioral rule inside a comment is
     invisible at runtime → High finding.
   - Classify each line or block as RULE (atomic behavioral mandate) or CONTEXT
     (workflow doc, setup, meta) using the tiebreaker below. Flag each RULE not
     in a `.claude/rules/` file as MISPLACED; each RULE already covered there as
     REDUNDANT. Never flag CONTEXT blocks — they belong in CLAUDE.md.
   - When two CLAUDE.md files contain the same rule with conflicting wording or
     opposite mandates, file a cross-file conflict (High). A CLAUDE.md in a git
     submodule (own `.git` or listed in `.gitmodules`) is out of scope — never
     flag or modify it; non-git subdirectories of the same repo are in scope.
4. Extract rules from audit artifacts. Extract only Critical and High severity
   findings as rule candidates; Medium and below produce Advisory suggestions
   only — except security findings, where Medium also qualifies as a candidate.
   From `arch-profile.md`, extract boundary rules stated as absolutes
   ("controllers never import repositories directly"); skip descriptive
   observations about detected patterns.
5. Scan the project for implicit conventions not yet captured anywhere:
   directory naming and structure → structural rules; test file placement and
   naming → testing rules; import/dependency direction → boundary rules;
   repeated code constructs → code generation rules. Report only the top 3
   most-repeated patterns per category; cap total Advisory suggestions from this
   step at 10.
6. File findings via the store protocol in `_conventions.md`, under the
   `agent-rules` auditor key.
7. Present the summary: validation errors, misplaced rules, redundant rules,
   suggestions. Then, instead of the generic apply-fixes prompt, ask per action:
   - Each MISPLACED rule: "Move to `.claude/rules/<filename>.md`? (y/n)"
   - Each REDUNDANT rule: "Remove from CLAUDE.md? (mandate already in .claude/rules/) (y/n)"
   - Each new suggestion: "Create `.claude/rules/<filename>.md`? (y/n)"
     Propose `<filename>` as the kebab-case topic of the rule (3 words max, no
     articles); e.g. "Never run git commit" → `no-direct-commits.md`. With 5 or
     more pending actions, offer a batch option first:
     "Apply all? (y) Review individually? (r) Skip all? (n)".
     If running non-interactively or no response is received, record the proposed
     changes in the findings and halt — never apply without explicit per-change
     confirmation.

## Bundled tool

`np_check_rules_anatomy` — no arguments; it reads whichever rules directories the audited project keeps, per the Harness scope table, and names them in `rules_dirs`. Without the nitpicker MCP tools, the same code runs through the bundled CLI (non-Claude agents resolve the path relative to the nitpicker skill directory):

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/check-rules-anatomy.py" [<project_root>]
```

Either way the output is JSON. Checks: kebab-case filenames, non-empty bodies, valid `paths:` frontmatter, no hedged language ("try to", "prefer", "consider"), dangling symlinks, symlinks escaping the project root, stale paths, unfilled placeholders, stale dates, duplicate lines, dead same-file anchors, and a directive buried mid-file. The tool adds `blocking` — true when any finding is High or Critical, the CLI's exit-1 condition. Use in step 2 for a programmatic report before filing findings.

A second tool covers what no per-file check can see — the always-loaded **set**:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/check-agent-instructions.py" [<project_root>]
```

It reads every instruction file the detected harnesses load — both roles in the Harness scope table — and reports five defects that only exist across files or against a whole-set total: `instruction_budget` (the set's directives against the ~150 a session can carry once the harness takes its share), `position_risk` (a critical rule titled in the middle 20–80% of a root file, where it is skimmed past), `cross_file_duplicate` (one directive stated in two files), `dangling_import` (an `@path.md` import whose target does not exist — the harness skips it in silence, so every rule the target holds is absent from the session and the author has no signal), and `circular_import` (an import chain returning to a file already on it, cut at a depth limit rather than followed). The budget limit and a dangling import block. It names the harnesses it detected in `harnesses`.

A duplicate is graded by whether one session ever holds both copies: Medium within a harness, where the two are genuinely competing sources; Low across two, where the repetition is a deliberate mirror — `.github/copilot-instructions.md` exists precisely because Copilot does not read `CLAUDE.md` — and the hazard is that editing one leaves the other stale rather than contradicted. Position risk inside a rules directory belongs to `check-rules-anatomy.py`, which scores that file shape with a stricter rule — do not report it from both.

## Rule classification reference

**Move to `.claude/rules/`** — atomic behavioral mandates for the agent's conduct:

- "Never run `git commit` without explicit user instruction"
- "Use `rg` for code search, not `grep`"
- "Never use `--no-verify` with git hooks"

**Keep in CLAUDE.md** — project context, workflow documentation, meta-instructions:

- Development commands and Makefile targets
- Architecture overview and skill routing tables
- Release workflow, versioning docs, prerequisites, project background

Rule of thumb: "what should the agent always do in this project?" → `.claude/rules/`. "What is this project and how does it work?" → CLAUDE.md.

**User-level vs project-level:** a rule that is personal preference with no project-specific justification ("always use vim keybindings") belongs in `~/.claude/rules/` (applies machine-wide), not `.claude/rules/` (committed, shared with the team).

**Compliance reliability:** CLAUDE.md is delivered as a user message after the system prompt — no strict compliance guarantee for vague or conflicting instructions. Security-critical and compliance mandates belong in `.claude/rules/` (dedicated context injection) for more reliable enforcement.

**Tiebreaker for borderline cases:** if removing the statement would not change observable behavior (only understanding of the project), it is CONTEXT. If removing it would allow a prohibited action, it is RULE. "Use semantic versioning" describes the project → CONTEXT. "Always run `make check` before committing" prescribes behavior → RULE.

## Good rule file anatomy

Two valid forms:

**Unconditional rule** (loaded in every session):

```markdown
# <Topic — imperative noun phrase>

Never <X>.
Always <Y>.
Use <tool-A>, not <tool-B>.
```

**Path-scoped rule** (loaded only when a matching file is read):

```markdown
---
paths:
  - "src/**/*.ts"
---

Always add explicit return types to exported functions.
Never use `any` — use `unknown` and narrow it.
```

Each rule must be **specific** ("Use `rg` not `grep`", not "prefer better search tools"), **unconditional** (no "try to", "generally", "when possible"), **testable** (compliance checkable from a transcript), and **scoped** (one topic per file). The h1 title is a readability convention; its absence is not a validation error. Path-scoped rules trigger on file reads, not every tool use — use them for language- or directory-specific mandates.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | `.claude/rules/` absent and CLAUDE.md contains 5+ atomic behavioral rules; rule file with broken/unparseable content |
| High | `.claude/rules/` absent and CLAUDE.md contains 1–4 atomic rules; 3+ misplaced rules; contradictory duplicate rules across files; cross-file CLAUDE.md conflict; rule inside HTML comment; CLAUDE.md over 400 lines; dangling symlink |
| Medium | 1–2 misplaced rules; grab-bag rule file; CLAUDE.md 200–400 lines; missing @-import target; invalid `paths:` glob |
| Low | Hedged rule language; non-kebab-case filename; rule that could be more specific; rules-to-rules duplicate without contradiction; unconditional rule that would be better path-scoped |
| Advisory | Suggested new rule from a detected convention; `.claude/rules/` absent with zero atomic rules; `.claude/rules/` exists but empty; rule file excluded by `claudeMdExcludes`; project rule better as a user-level rule |

Do not invent intermediate thresholds — use this table exactly.

## Fix strategy

**Auto-applicable:**

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

## Common mistakes

- **Flagging CLAUDE.md workflow documentation as misplaced rules.** Development commands, routing tables, release workflows, and architecture overviews belong in CLAUDE.md. Only atomic behavioral mandates are migration candidates.
- **Creating a new rules file without checking existing `.claude/rules/` first.** Duplicates create contradictions when both files load.
- **Migrating a rule without removing it from CLAUDE.md.** A rule in both places is a redundancy finding. Every migration includes removing the original.
- **Flagging correctly-placed context as a misplaced rule.** "The project uses semantic versioning" is context, not a behavioral rule.
- **Skipping artifact collection because the command "can detect enough on its own".** Audit artifacts surface violation-derived rules static analysis misses. If absent, record the gap as Advisory and name the prerequisite commands to run before the next pass.
