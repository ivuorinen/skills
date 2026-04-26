# Nitpicker Findings
Generated: 2026-04-24
Last validated: 2026-04-26

## Summary
- Total: 41 | Open: 0 | Fixed: 41 | Invalid: 0

## Open Findings

(none)

## Fixed

### Pass 8 — 2026-04-26

#### [N-041] release-readiness-reviewer.md step 6 uses broken shell quoting in git tag check
Fixed: 2026-04-26
Notes: Replaced nested double-quoted `python3 -c "..."` inside `grep "v$(…)"` with single-quoted `-c '...'` so the shell command is syntactically valid. Broken form: `grep "v$(python3 -c "import json; ...")"`. Fixed form: `grep "v$(python3 -c 'import json; ...')"`.

#### [N-040] release-prep/SKILL.md uses invalid git rebase range syntax
Fixed: 2026-04-26
Notes: `git rebase -i main..HEAD` is not a valid interactive rebase invocation (expects an upstream branch, not a range). Changed to `git rebase -i main`.

#### [N-039] nitpicker/SKILL.md step 3 missing inline-mode exclusion condition
Fixed: 2026-04-26
Notes: Single-shot step 3 said "If in security/docs/architecture mode: invoke specialist skill..." without the `AND NOT inline mode` guard. This contradicts the Mode delegation detail section which explicitly prohibits specialist invocation when `inline` is active. Added "AND NOT inline mode" to step 3.

#### [N-038] validate-skill.py legacy-path check strips inline code spans, creating false negatives
Fixed: 2026-04-26
Notes: The legacy-output-path check stripped all inline backtick spans before scanning, so a skill that referenced `codereview.md` inside an instruction code span would not be flagged. Changed to strip only fenced code blocks and table rows (documentation/example context) while leaving inline code in prose untouched.

#### [N-037] validate-audit-findings-hook.py does not resolve relative file_path against REPO_ROOT
Fixed: 2026-04-26
Notes: `path = Path(file_path)` with a relative path fails `path.exists()` when the hook is invoked from a directory other than the repo root. Fixed to `path = raw if raw.is_absolute() else REPO_ROOT / raw`. `REPO_ROOT` was already defined at module level.

### Pass 7 — 2026-04-26

#### [N-036] release-readiness-reviewer.md frontmatter description mentions "changelog" after N-035 fix
Fixed: 2026-04-26
Notes: Updated `description` in `.claude/agents/release-readiness-reviewer.md` from "checks skill validity, version sync, changelog, and CI status" to "checks skill validity, version sync, conventional commits, and CI status".

### Pass 6 — 2026-04-26

#### [N-035] release-readiness-reviewer.md step 3 checks CHANGELOG; contradicts release-prep/SKILL.md
Fixed: 2026-04-26
Notes: Replaced CHANGELOG check in `.claude/agents/release-readiness-reviewer.md` step 3 with a conventional commits check, matching `release-prep/SKILL.md` step 6 which explicitly forbids checking for a manually-written CHANGELOG entry.

#### [N-034] security-auditor/SKILL.md missing section-structure rule
Fixed: 2026-04-26
Notes: Added the section-structure rule to `## Common Mistakes` in `skills/security-auditor/SKILL.md`. The rule was added to nitpicker, doc-auditor, and arch-auditor but not to security-auditor, the canonical template.

#### [N-033] new-skill/SKILL.md prescribes `## Output Format` instead of `## Findings Format`
Fixed: 2026-04-26
Notes: Updated Phase 2 step 4 in `.claude/skills/new-skill/SKILL.md` to prescribe `## Findings Format` with `### Pass N — YYYY-MM-DD` h3 sub-sections for audit-writing skills; noted that non-audit (stdout-only) skills may use `## Output Format`.

#### [N-032] Fallback date extraction prefers `Generated:` over `Last validated:`
Fixed: 2026-04-26
Notes: Changed the `_DATE_HDR` scan loop in `parse_and_fix()` to not break on `Generated:` — it sets the fallback date but continues scanning. Breaking only on `Last validated:` ensures the more recent date is used.

#### [N-031] `_DATE_HDR` regex compiled inside `parse_and_fix()` on every call
Fixed: 2026-04-26
Notes: Moved `_DATE_HDR = re.compile(...)` to module level alongside the other compiled patterns in `scripts/hooks/validate-audit-findings-hook.py`.

#### [N-030] Dead tracking variables `h3_under_fixed` / `h3_under_invalid`
Fixed: 2026-04-26
Notes: Removed `h3_under_fixed` and `h3_under_invalid` lists and their `.append()` calls from `parse_and_fix()` in `scripts/hooks/validate-audit-findings-hook.py`.

#### [N-029] N-027 notes truncated in nitpicker-findings.md
Fixed: 2026-04-26
Notes: Restored the missing sentence fragment "## Fixed) into a single ## Fixed h2 with Pass N sub-sections. Renamed non-conforming h3 headers" to N-027 notes. Text was stripped during a hook false-positive run before the `prev_blank` guard was added.

#### [N-028] Hook silently deletes severity breakdown line from security-findings.md
Fixed: 2026-04-26
Notes: Added `summary_extra: list[str] = []` to `parse_and_fix()`. Non-SUMMARY_RE non-blank lines in `current == "summary"` are now collected into `summary_extra` and emitted after the reconstructed `Total:` line, preserving the `Critical: N | High: N | ...` line used by `security-auditor`.

### Pass 5 — 2026-04-26

#### [N-027] nitpicker-findings.md Fixed section has wrong structure
Fixed: 2026-04-26
Notes: Merged three separate ## Fixed h2 sections (## Fixed — fifth pass, ## Fixed — fourth pass,
## Fixed) into a single ## Fixed h2 with Pass N sub-sections. Renamed non-conforming h3 headers
(e.g. "### 2026-04-26, third pass" → "### Pass 3 — 2026-04-26"). Updated nitpicker/SKILL.md,
doc-auditor/SKILL.md, and arch-auditor/SKILL.md Findings Format to match the security-auditor
canonical template (h2 status → h3 pass → h4 finding). Added
scripts/hooks/validate-audit-findings-hook.py to enforce structure on future writes.

#### [N-026] validate-skills/SKILL.md missing "Header level progression" check row
Fixed: 2026-04-26
Notes: Added `| Header level progression (no skipping levels) | Error |` row to the "What is checked" table in `.claude/skills/validate-skills/SKILL.md`. This check is implemented in the validator but was absent from the documentation table after the N-020 fix removed unimplemented rows.

#### [N-025] skill-tester/SKILL.md GREEN and REFACTOR phases conflated
Fixed: 2026-04-26
Notes: Split the single dispatch instruction into two separate instructions: GREEN phase now reads "Write skill. Then dispatch same subagent with skill loaded. Confirm each RED rationalization is blocked." REFACTOR phase now reads "Refactor skill body. Then dispatch same scenario again (skill still loaded). Confirm no regressions." Each phase has its own clear dispatch step matching the checklist item added in N-023.

#### [N-024] copilot-instructions.md validate-skills.yml description incomplete
Fixed: 2026-04-26
Notes: Updated the validate-skills.yml description in `.github/copilot-instructions.md` from "triggers on SKILL.md files or scripts/validate-skill.py" to "triggers on SKILL.md files, version files, and validation scripts" to match the paths added in N-015.

### Pass 4 — 2026-04-26

#### [N-023] skill-tester/SKILL.md checklist missing REFACTOR-phase verify item
Fixed: 2026-04-26
Notes: Added `- [ ] REFACTOR scenario re-run confirms no regression and no new loopholes` as fourth checklist item.

#### [N-022] new-skill/SKILL.md step 8 uses conditional "If README.md contains a mirrored skills table"
Fixed: 2026-04-26
Notes: Changed step 8 from "If README.md contains a mirrored skills table, update it too" to "Also update README.md — it always contains a mirrored skills table."

#### [N-021] release-readiness-reviewer.md step 6 uses node require() on ESM package
Fixed: 2026-04-26
Notes: Replaced `node -p "require('./package.json').version"` with `python3 -c "import json; print(json.load(open('package.json'))['version'])"` in step 6.

#### [N-020] validate-skills/SKILL.md documents checks the validator does not implement
Fixed: 2026-04-26
Notes: Removed the two unimplemented Warning rows (`## Overview`/`## Mindset` and `## When to Use`/`## Operating Rules`) from the "What is checked" table in `.claude/skills/validate-skills/SKILL.md`.

#### [N-019] make validate only validates public skills
Fixed: 2026-04-26
Notes: Added `$(UV) scripts/validate-skill.py .claude/skills/*/SKILL.md` as a second line in the `validate` Makefile target.

#### [N-018] check-version-sync-hook.py missing pyproject.toml from VERSION_FILES
Fixed: 2026-04-26
Notes: Added `"pyproject.toml"` to the `VERSION_FILES` set in `scripts/hooks/check-version-sync-hook.py`.

### Pass 3 — 2026-04-26

#### [N-017] skills router SKILL.md lacks explicit no-chain rule
Fixed: 2026-04-26
Notes: Added `## Rules` block to `.claude/skills/skills/SKILL.md` explicitly prohibiting multi-skill invocation and chaining.

#### [N-016] Skill Quality Gate missing REFACTOR-phase skill-tester checkbox
Fixed: 2026-04-26
Notes: Added `skill-tester REFACTOR verify` as a sixth gate item in `.claude/skills/new-skill/SKILL.md`.

#### [N-015] CI does not trigger version-sync check on version file changes
Fixed: 2026-04-26
Notes: Added all five version files and `scripts/check-version-sync.py` to the `paths:` filters in both `push` and `pull_request` triggers in `.github/workflows/validate-skills.yml`.

#### [N-014] skills router absent from Master Invocation Map
Fixed: 2026-04-26
Notes: Added `SK[skills / router]` to the Leaves and Consumers subgraph in the Master Invocation Map.

#### [N-013] arch-auditor role label inconsistent
Fixed: 2026-04-26
Notes: Renamed subgraph to `"Leaves and Consumers (called, never call)"`. Updated Consumer definition to state Consumers are a specialised Leaf that optionally read a predecessor's artifact.

### Pass 2 — 2026-04-24

#### [N-012] ERRORS/WARNINGS are module-level lists in validate-skill.py
Fixed: 2026-04-24
Notes: `errors` and `warnings` are now local lists in `main()`, passed into `validate()`. Inner `err()`/`warn()` closures append to them.

#### [N-011] TOML version regex inconsistent between bump and check scripts
Fixed: 2026-04-24
Notes: Aligned `bump-version.py` regex to `[^"]+` to match `check-version-sync.py`.

#### [N-010] update_toml() silently no-ops when version line not found
Fixed: 2026-04-24
Notes: Added `if new_content == content: sys.exit(1)` guard after `re.sub`.

#### [N-009] pyproject.toml excluded from release-please auto-bump
Fixed: 2026-04-24
Notes: Added `{ "type": "toml", "path": "pyproject.toml", "jsonpath": "$.project.version" }` to extra-files in `.release-please-config.json`.

### Pass 1 — 2026-04-24

#### [N-008] Makefile has no help target
Fixed: 2026-04-24
Notes: Added `help` target listing all available targets with descriptions.

#### [N-007] parse_frontmatter duplicated across two scripts
Fixed: 2026-04-24
Notes: Extracted to `scripts/common.py`; both scripts now import from there.

#### [N-006] update_file() captures new_version as implicit global
Fixed: 2026-04-24
Notes: `update_file` now accepts `version: str` as an explicit parameter.

#### [N-005] Private skills not validated by CI
Fixed: 2026-04-24
Notes: Added `.claude/skills/**/SKILL.md` to workflow path filters; validate step now runs against both `skills/` and `.claude/skills/`.

#### [N-004] stop-reminder.py silent on repo with no commits
Fixed: 2026-04-24
Notes: Falls back to `git status --porcelain` when `git diff --name-only HEAD` returns non-zero.

#### [N-003] .ruff_cache/ not in .gitignore
Fixed: 2026-04-24
Notes: Added `.ruff_cache/` to `.gitignore`.

#### [N-002] Action SHA pins reference non-existent versions
Fixed: 2026-04-24
Notes: SHA-pinned to `actions/checkout@de0fac2e (v6.0.2)` and `astral-sh/setup-uv@08807647 (v8.1.0)`.

#### [N-001] CI calls deleted shell script
Fixed: 2026-04-24
Notes: Replaced `bash scripts/check-version-sync.sh` with `uv run scripts/check-version-sync.py`; removed superfluous `node --version` line.

## Invalid

(none)
