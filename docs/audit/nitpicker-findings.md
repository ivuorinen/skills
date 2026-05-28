# Nitpicker Findings
Generated: 2026-04-24
Last validated: 2026-05-28

## Summary
- Total: 85 | Open: 5 | Fixed: 79 | Invalid: 1

## Open Findings

### High

#### [N-079] `security-auditor/SKILL.md` step 7 silently marks all open findings Fixed when no tools run
Category: correctness
Area: skills/security-auditor/SKILL.md (Process, step 7)
Problem: Step 7 re-validates open findings by checking whether the "current scan still reports a match." If no tools are installed, no scan runs and the current results are empty. Every existing open finding appears "no longer reported" and gets moved to Fixed — not because the vulnerability was fixed, but because no scanner ran.
Evidence: Process step 7: "If current scan no longer reports a match → move to Fixed." If grype, semgrep, gitleaks, etc. are all absent, `which <tool>` fails for all, zero tools execute, and the match check trivially passes for every existing finding.
Impact: Running the skill on a machine without scanners silently invalidates the entire historical security audit. A previously found Critical CVE would be closed with "Fixed" even though the vulnerable dependency was never updated.
Fix: Add a guard before step 7: "If fewer tools ran successfully than reported findings reference, skip re-validation of those findings — do not move findings whose detecting tool did not run. Emit a warning: 'Re-validation skipped for findings from tools not available in this run: <list>.'"

### Medium

#### [N-078] `claude-rules-auditor/SKILL.md` Process section has no step to re-validate existing open findings
Category: correctness
Area: skills/claude-rules-auditor/SKILL.md (Process, steps 1–9)
Problem: All other audit skills (nitpicker, arch-auditor, doc-auditor, security-auditor) include a step: "If findings file exists, re-validate each OPEN finding — resolved → Fixed, wrong → Invalid, still present → leave Open." `claude-rules-auditor` has no such step. On repeated runs, fixed rule violations would remain Open indefinitely and previously filed findings would not get closed.
Evidence: Process steps 1–9 checked line-by-line: step 2 validates existing rule files (structural), step 3 audits CLAUDE.md, steps 4–5 extract suggestions — none re-validate previously filed findings against current state.
Impact: Accumulated stale open findings; no convergence to a clean state even after issues are resolved.
Fix: Insert a step after step 1 (Discovery): "If `docs/audit/claude-rules-auditor-findings.md` exists, re-validate each OPEN finding: if the flagged issue is now resolved → move to Fixed (record date); if the finding was wrong → move to Invalid (record reason); otherwise leave Open."

### Low

#### [N-080] `claude-rules-auditor/SKILL.md` Findings Format uses `[ID]` placeholder without defining the `CRA-NNN` prefix
Category: docs
Area: skills/claude-rules-auditor/SKILL.md (Findings Format)
Problem: The Findings Format shows `#### [ID] Short title` without specifying the ID format or prefix. In practice the skill uses `CRA-NNN` (as seen in `docs/audit/claude-rules-auditor-findings.md`), but this is not defined in the skill. Compare with `security-auditor` which explicitly states "Finding ID format: `SEC-NNN` (zero-padded to 3 digits)."
Evidence: `docs/audit/claude-rules-auditor-findings.md` uses IDs `CRA-001` through `CRA-007`. `claude-rules-auditor/SKILL.md` Findings Format section has no ID format statement.
Impact: Without a defined prefix, a new run of the skill might choose a different prefix, breaking ID uniqueness across runs.
Fix: Add after the Findings Format code block: "Finding ID format: `CRA-NNN` (zero-padded to 3 digits, e.g. `CRA-001`). Assign sequentially; never reuse IDs."

#### [N-084] `arch-detector/SKILL.md` does not define output behavior when no architectural patterns are detected
Category: docs
Area: skills/arch-detector/SKILL.md (Output)
Problem: The `## Output` section shows a profile template with pattern sections, but says nothing about what to write if no patterns match any of the 19 catalogued architectures. The `## Behavior` section adds only re-detection and commit-ask rules. An unrecognized architecture produces no guidance on what to include in the profile.
Evidence: `## Behavior` (L101–L105) covers re-detection and commit gate only. No "if no patterns matched" clause anywhere in the skill body.
Impact: An ambiguous codebase would produce an empty or misleading `arch-profile.md` with no inferred rules, which arch-auditor then uses as its source of truth — resulting in an audit against zero rules.
Fix: Add to `## Behavior`: "If no catalogued pattern matches with ≥ Medium confidence, write the profile with `Detected: none` and `Inferred Structural Rules: none` and flag the profile as `Confidence: none — manual review required`. Do not invent rules."

#### [N-085] `claude-rules-auditor/SKILL.md` step 1b does not distinguish absent `.claude/rules/` from empty
Category: docs
Area: skills/claude-rules-auditor/SKILL.md (Process, step 1b)
Problem: Step 1b says "List all files under `.claude/rules/` (record empty directory as a finding)." If the directory does not exist, this instruction is ambiguous — the skill should treat absent and empty directories identically (both produce zero rule files), but the wording only covers the empty case.
Evidence: L38: "b. List all files under `.claude/rules/` (record empty directory as a finding)." No mention of the absent directory case, despite the "When to Use" section explicitly listing `.claude/rules/ is absent` as a trigger.
Impact: Ambiguity about whether an absent directory is treated as empty (and filed as a finding) or as an error condition.
Fix: Change step 1b to: "b. If `.claude/rules/` does not exist or is empty, record this as a finding; proceed to step 1c."
Category: docs
Area: skills/nitpicker/SKILL.md:19
Problem: The "When NOT to use" line says "For a focused security-only scan, use `adversarial-reviewer` instead." `adversarial-reviewer` is a code-review skill — it does not run CVE scanners, secrets detection, or dependency audits. Users following this instruction get code-level analysis only and miss tool-detected findings entirely.
Evidence: L19: `**When NOT to use:** For a focused security-only scan, use \`adversarial-reviewer\` instead.` The adversarial-reviewer description confirms: "Use when asked to review code, find bugs, audit for correctness" — no scanner tooling.
Impact: Users needing a security scan (CVEs, leaked secrets, vulnerable dependencies) are silently directed to a skill that cannot produce those findings.
Fix: Change `adversarial-reviewer` to `security-auditor` on line 19.

### Medium

#### [N-070] `nitpicker/SKILL.md` description summarizes workflow in violation of `skill-format.md`
Category: conventions
Area: skills/nitpicker/SKILL.md:3
Problem: The description ends with "Finds defects and optionally applies fixes in a single run." This describes what the skill does, not when to use it — a direct violation of the rule "Never summarize the skill's workflow in the description — describe triggering conditions only."
Evidence: L3 (raw): `description: Use when performing … run a release gate check. Finds defects and optionally applies fixes in a single run.`
Impact: The auto-discovery signal is polluted with capability description. The validator does not catch this, so the violation persists silently.
Fix: Remove the trailing sentence "Finds defects and optionally applies fixes in a single run." from the description.

#### [N-071] `pr-reviewer/SKILL.md` description summarizes workflow in violation of `skill-format.md`
Category: conventions
Area: skills/pr-reviewer/SKILL.md:3
Problem: The second sentence of the description — "Produces copy-paste-ready markdown code review with constructive criticism — problems, severity, and suggested fixes — formatted for GitHub PR comments." — describes the skill's output format and workflow, not a triggering condition.
Evidence: L3 (raw): `description: Use when reviewing a pull request, staged changes, or a specific diff. Produces copy-paste-ready markdown code review with constructive criticism — problems, severity, and suggested fixes — formatted for GitHub PR comments.`
Impact: Same as N-070 — capability description in the trigger field; not caught by validator.
Fix: Remove everything after "a specific diff." from the description.

#### [N-072] `.claude/skills/new-skill/SKILL.md` description summarizes workflow
Category: conventions
Area: .claude/skills/new-skill/SKILL.md:3
Problem: The description ends with "Scaffolds the correct directory structure, frontmatter, and required sections." — describing the skill's actions rather than triggering conditions. `skill-format.md` applies to `.claude/skills/**/SKILL.md` paths (per its frontmatter `paths:` field).
Evidence: L3: `description: Use when creating a new hostile audit skill for this repository. Scaffolds the correct directory structure, frontmatter, and required sections.`
Impact: Same pattern as N-070/N-071 — undiscovered by validator.
Fix: Remove "Scaffolds the correct directory structure, frontmatter, and required sections." from the description.

#### [N-073] `.claude/skills/skills/SKILL.md` description summarizes workflow
Category: conventions
Area: .claude/skills/skills/SKILL.md:3
Problem: The description ends with "Routes to the correct public skill based on the request." — describing the action performed, not a trigger condition.
Evidence: L3: `description: Use when the user wants to run one of the hostile audit skills in this repo, or asks what skills are available. Routes to the correct public skill based on the request.`
Impact: Same pattern as N-070/N-071.
Fix: Remove "Routes to the correct public skill based on the request." from the description.

#### [N-074] No tests for `bump-version.py` `update_toml` rewrite
Category: tests
Area: scripts/bump-version.py, tests/
Problem: The branch rewrites `update_toml()` from a single `re.sub` into a line-by-line state machine that tracks `[project]` section boundaries. The new logic handles `[project.sub]` sections, comments, and multiple `[...]` headers. No test file for `bump-version.py` exists; the rewrite has zero test coverage.
Evidence: `ls tests/` shows no `test_bump_version.py`. Diff shows `update_toml` changed from a 6-line regex to a 16-line state machine. Failure scenario: if `in_project` tracking is wrong, `version` in `[tool.poetry]` or `[project.scripts]` could be updated, or `[project]` version missed, and `sys.exit(1)` only fires when `replaced` remains `False` — silent wrong-section updates are not caught.
Impact: Version bumps could silently update the wrong TOML section on unusual `pyproject.toml` layouts.
Fix: Add `tests/test_bump_version.py` covering: (a) standard single `[project]` version update, (b) `[project.scripts]` version not touched, (c) `[project]` after other sections is still found, (d) missing `[project]` exits with code 1.

### Low

#### [N-075] `test_missing_blank_lines_before_sections_corrected` does not assert finding content preserved
Category: tests
Area: tests/test_validate_audit_findings_hook.py:258
Problem: The test verifies that `## Open Findings`, `## Fixed`, `## Invalid` appear in the output and the summary line is preserved, but it never asserts that `[X-001] Finding` (the h4 finding in `## Open Findings`) survives. If the pre-pass or section classifier silently drops findings, the test still passes.
Evidence: L263: `"## Open Findings\n#### [X-001] Finding\n"` is in the input. Assertions on L268-L271 check for section headers and summary count but not for `[X-001]`.
Impact: A regression in finding-content preservation through the pre-pass would not be caught by this test.
Fix: Add `assert "[X-001] Finding" in fixed` to the test body.

#### [N-076] `validate-skill.py` does not enforce "never summarize workflow" rule from `skill-format.md`
Category: conventions
Area: scripts/validate-skill.py
Problem: `skill-format.md` states "Never summarize the skill's workflow in the description — describe triggering conditions only." The validator checks that descriptions start with "Use when", are ≤500 chars, and that `': '`-containing values are single-quoted — but performs no check for workflow-summary sentences appended after the trigger conditions. N-070/N-071/N-072/N-073 all pass `make validate` undetected.
Evidence: Running `make validate` on the current tree reports zero errors despite four descriptions with workflow summaries. The description check in `validate-skill.py` has no pattern for "Produces", "Scaffolds", "Routes", "Finds", "Writes", "Generates".
Impact: The rule is written but unenforced — authors can violate it without any CI feedback.
Fix: Add a warn-level check: if the description contains a sentence not beginning with "Use when" that starts with a verb pattern (`Produces`, `Finds`, `Writes`, `Generates`, `Scaffolds`, `Routes`, `Outputs`, `Applies`), emit a warning "description may contain workflow summary — describe triggering conditions only."

#### [N-077] `.claude/skills/validate-skills/SKILL.md` "What is checked" table missing the `': '` → single-quote check
Category: docs
Area: .claude/skills/validate-skills/SKILL.md
Problem: The "What is checked" table lists 8 checks, but omits the check that is implemented in `validate-skill.py` L51-L54: "If description contains `': '`, it must be wrapped in single quotes." This check is an Error-level validation that has been enforced since at least N-048/N-062 iterations.
Evidence: Table ends at `| Legacy output paths (\`./codereview.md\` etc.) | Warning |` — no row for the quote-style check. The validator at L51: `raw_val = line[len("description: "):].strip()` and L52-L54 confirm the check exists.
Impact: Users reading the validate-skills documentation believe descriptions with `': '` are valid unquoted, leading to preventable CI failures.
Fix: Add `| Description with \`': '\` must be single-quoted | Error |` row to the "What is checked" table.

## Fixed

### Pass 19 — 2026-05-28

#### [N-069] `nitpicker/SKILL.md` "When NOT to use" redirects security scans to the wrong skill
Fixed: 2026-05-28
Notes: Changed `adversarial-reviewer` to `security-auditor` in the "When NOT to use" line of `skills/nitpicker/SKILL.md`. The security-auditor runs CVE scanners, secrets detection, and dependency audits; adversarial-reviewer is a code-logic review skill only.

#### [N-070] `nitpicker/SKILL.md` description summarizes workflow
Fixed: 2026-05-28
Notes: Removed "Finds defects and optionally applies fixes in a single run." from the description. The description now ends at the last trigger condition (release gate check) with no workflow summary.

#### [N-071] `pr-reviewer/SKILL.md` description summarizes workflow
Fixed: 2026-05-28
Notes: Removed "Produces copy-paste-ready markdown code review with constructive criticism — problems, severity, and suggested fixes — formatted for GitHub PR comments." from the description. The description is now trigger-only.

#### [N-072] `.claude/skills/new-skill/SKILL.md` description summarizes workflow
Fixed: 2026-05-28
Notes: Removed "Scaffolds the correct directory structure, frontmatter, and required sections." from the description.

#### [N-073] `.claude/skills/skills/SKILL.md` description summarizes workflow
Fixed: 2026-05-28
Notes: Removed "Routes to the correct public skill based on the request." from the description.

#### [N-074] No tests for `bump-version.py` `update_toml` rewrite
Fixed: 2026-05-28
Notes: Created `tests/test_bump_version.py` with 9 tests: 4 covering `bump_version()` (patch/minor/major/invalid-part) and 5 covering `update_toml()` (project section updated, tool section untouched, project after other section found, missing project exits with code 1 + file unchanged, project subscope not matched).

#### [N-075] `test_missing_blank_lines_before_sections_corrected` does not assert finding content preserved
Fixed: 2026-05-28
Notes: Added `assert "[X-001] Finding" in fixed` to the test. The finding in `## Open Findings` is now verified to survive the pre-pass normalization.

#### [N-076] `validate-skill.py` does not enforce "never summarize workflow" rule
Fixed: 2026-05-28
Notes: Added `_WORKFLOW_VERBS` regex (module-level) and a warn-level check: if the description contains `. <WorkflowVerb>` (period + space + one of Produces/Finds/Writes/Generates/Scaffolds/Routes/Outputs/Applies), emit a warning. Added `test_workflow_summary_in_description_warns` and `test_clean_description_no_workflow_warning` to `tests/test_validate_skill.py`. 64 tests pass.

#### [N-077] `.claude/skills/validate-skills/SKILL.md` "What is checked" table missing `': '` → single-quote check
Fixed: 2026-05-28
Notes: Added `| Description with \`': '\` must be single-quoted | Error |` and `| Description contains workflow summary sentence | Warning |` rows to the "What is checked" table in `.claude/skills/validate-skills/SKILL.md`.

#### [N-081] No test for workflow-summary warning in `validate-skill.py`
Fixed: 2026-05-28
Notes: Filed and fixed in the same pass. Added two tests: `test_workflow_summary_in_description_warns` and `test_clean_description_no_workflow_warning`.

#### [N-082] `_WORKFLOW_VERBS` regex compiled inside `validate()` instead of at module level
Fixed: 2026-05-28
Notes: Moved `_WORKFLOW_VERBS = re.compile(...)` to module level in `scripts/validate-skill.py`. Eliminates redundant compilation on every `validate()` call.

#### [N-083] `test_missing_project_version_exits` does not assert file is unchanged after failed update
Fixed: 2026-05-28
Notes: Added `assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == toml` after the `mock_exit.assert_called_once_with(1)` assertion. After `sys.exit(1)` (which is a no-op in tests), execution continues to `path.write_text(...)` — this assertion confirms the write preserves the original content.

### Pass 17 — 2026-05-02

#### [N-068] CI paths use individual script entries; `bump-version.py` and `list-skills.py` uncovered
Fixed: 2026-05-02
Notes: Replaced four individual `scripts/*.py` entries and `scripts/hooks/**` with a single `scripts/**` glob in both `push` and `pull_request` trigger paths. `copilot-instructions.md` line 104 now accurately describes the trigger paths.

### Pass 16 — 2026-05-02

#### [N-065] CI paths filter missing `scripts/hooks/**`
Fixed: 2026-05-02
Notes: Added `- 'scripts/hooks/**'` to both `push` and `pull_request` paths lists in `.github/workflows/validate-skills.yml`. A source-only hook change now triggers CI.

#### [N-066] `test_validate_audit_findings_hook.py` missing test for N-063 custom-summary preservation
Fixed: 2026-05-02
Notes: Added `test_custom_summary_not_overwritten` to `TestParseAndFix`. Asserts that a file with custom summary lines and no `Total:` line emerges unchanged. 52 tests pass.

#### [N-067] `copilot-instructions.md` CI section describes 3 steps; CI now has 5
Fixed: 2026-05-02
Notes: Replaced stale description with accurate 5-step list (validate-skill ×2, validate-rules, check-version-sync, pytest, ruff) and updated the trigger-paths summary.

### Pass 15 — 2026-05-02

#### [N-061] CI workflow missing ruff lint step
Fixed: 2026-05-02
Notes: Added `- name: Lint scripts / run: uv run --with ruff ruff check scripts/` step to `.github/workflows/validate-skills.yml` after the "Run tests" step.

#### [N-062] `validate-skill.py` error message contradicts `skill-format.md` on quote style
Fixed: 2026-05-02
Notes: Updated `.claude/rules/skill-format.md` to say "single quotes" only (removing "or double quotes"), aligning the rule with the validator. `test_validate_skill.py::test_description_double_quoted_colon_space_errors` confirms double-quoted values intentionally produce errors — the validator behavior was correct, the rule was wrong.

#### [N-063] `validate-audit-findings-hook.py` corrupts `claude-rules-auditor-findings.md` summary
Fixed: 2026-05-02
Notes: Guarded the `Total:` line reconstruction with `if summary_found or not summary_extra:` in `parse_and_fix`. Files with no `Total:` line but custom summary content (like `claude-rules-auditor-findings.md`) no longer have a spurious `Total:` line prepended on every save.

### Pass 13 — 2026-05-01

#### [N-060] `copilot-instructions.md` validation table missing `make validate-rules`
Fixed: 2026-05-01
Notes: Added `make validate-rules # validate .claude/rules/ files (structure + path freshness)` after `make validate` in the Validation section of `.github/copilot-instructions.md`.

#### [N-059] `skill-format.md` rule stricter than validator on quote style
Fixed: 2026-05-01
Notes: Updated `.claude/rules/skill-format.md` to say "single or double quotes" — matching the behavior of `validate-skill.py` which accepts both after fix N-048.

#### [N-058] CRA-003 and CRA-004 marked Fixed when artifacts still absent
Fixed: 2026-05-01
Notes: Moved CRA-003 and CRA-004 from `## Fixed` to `## Invalid` in `docs/audit/claude-rules-auditor-findings.md` with a note that the artifact gaps persist and the findings were informational, not violations requiring remediation.

#### [N-057] CI paths filter missing `.claude/rules/**`
Fixed: 2026-05-01
Notes: Added `'.claude/rules/**'` to both `push` and `pull_request` paths lists in `.github/workflows/validate-skills.yml`. A commit adding or modifying a rule file now triggers the `validate-rules` CI step.

### Pass 12 — 2026-05-01

#### [N-056] Auto-discovery silently skipped dangling symlinks
Fixed: 2026-05-01
Notes: Replaced `rglob("*.md")` in discovery with `_iter_rules_dir()` using `os.scandir` recursively, which explicitly detects dangling symlinks. Added `test_dangling_symlink_found_in_discovery` to confirm the fix.

#### [N-055] `parse_rules_frontmatter` type annotation contradicted `None` sentinel return
Fixed: 2026-05-01
Notes: Changed return type from `tuple[dict, str]` to `tuple[dict | None, str]` and removed the `# type: ignore[return-value]` comment. Callers can now discover the error sentinel from the type signature.

#### [N-054] CI workflow had no `validate-rules` step
Fixed: 2026-05-01
Notes: Added `- name: Validate rules files\n  run: uv run scripts/validate-rules.py` step to `.github/workflows/validate-skills.yml`, symmetric with the existing `validate-skill.py` step.

#### [N-053] `make check` description stale in three files
Fixed: 2026-05-01
Notes: Updated help text in `Makefile`, `CLAUDE.md`, and `.github/copilot-instructions.md` to include `validate-rules` in the `make check` description.

#### [N-052] `test_no_rules_dir_exits_clean` never called script code
Fixed: 2026-05-01
Notes: Replaced the no-op test (which only asserted empty Python lists) with two meaningful tests: `test_empty_rules_dir_returns_no_targets` calls `_discover_targets()` on an empty `.claude/rules/` directory, and `test_dangling_symlink_found_in_discovery` verifies dangling symlinks appear in discovery output.

#### [N-051] CI paths filter missing `scripts/validate-rules.py`
Fixed: 2026-05-01
Notes: Added `'scripts/validate-rules.py'` to both `push` and `pull_request` paths lists in `.github/workflows/validate-skills.yml`. A PR modifying the validator now triggers CI.

### Pass 11 — 2026-04-30

#### [N-050] `make test` missing from CLAUDE.md and copilot-instructions.md command tables
Fixed: 2026-04-30
Notes: Added `make test — run pytest unit tests for scripts/` to the Development Commands block in `CLAUDE.md` and to the Validation section in `.github/copilot-instructions.md`. Also updated the `make check` description in both files to reflect that tests now run as part of the default gate.

#### [N-049] `make check` excludes `test` target — pre-commit gate incomplete
Fixed: 2026-04-30
Notes: Changed `check: validate version-sync lint` to `check: validate version-sync lint test`. `make check` now runs all 35 unit tests as part of the pre-commit gate. Updated the help string from "validate + version-sync + lint" to "validate + version-sync + lint + test". All 35 tests pass with the updated gate.

### Pass 10 — 2026-04-30

#### [N-048] `validate-skill.py` description `': '` check rejects double-quoted values with inaccurate error message
Fixed: 2026-04-30
Notes: Changed regex from `re.fullmatch(r"'.*'", raw_val)` to `re.fullmatch(r"['\"].*['\"]", raw_val)` to accept both single- and double-quoted descriptions (consistent with `parse_frontmatter` which already strips both quote styles). Updated error message from "wrap in single quotes for yaml.v3 compatibility" to "wrap in single quotes (project convention)" to accurately reflect the reason. The compatibility concern applies only to unquoted plain scalars; double-quoted YAML strings are equally valid in yaml.v3.

#### [N-047] No unit tests for validator and hook scripts
Fixed: 2026-04-30
Notes: Created `tests/` directory with 35 tests covering `parse_frontmatter` (10 cases), `validate()` (14 cases), `_ensure_pass_header` (6 cases, including the N-046 regression case), and `parse_and_fix` (5 cases). Added `[project.optional-dependencies] dev = ["pytest"]` and `[tool.pytest.ini_options]` to `pyproject.toml`. Added `test` target to Makefile (`uv run --with pytest pytest tests/`). Added `tests/**` to CI paths filter and a `Run tests` step to `validate-skills.yml`.

#### [N-046] `_ensure_pass_header` produces duplicate `### Pass 1` when existing minimum pass is 1
Fixed: 2026-04-30
Notes: When `min(existing) - 1 < 1`, the function now falls back to `max(existing) + 1` instead of clamping to 1. If orphaned h4s appear before an existing `### Pass 1`, they are wrapped in `### Pass 2` (or `max+1`), avoiding a duplicate `### Pass 1` sub-section. Covered by `test_n046_orphaned_h4_before_pass_1_no_duplicate` and `test_n046_orphaned_before_pass_1_and_2_uses_pass_3`.

#### [N-045] CI path filter missing `scripts/common.py`
Fixed: 2026-04-30
Notes: Added `'scripts/common.py'` to both `push` and `pull_request` paths filters in `.github/workflows/validate-skills.yml`. A PR that only modifies `common.py` (e.g., a breaking change to `parse_frontmatter`) now triggers CI.

### Pass 9 — 2026-04-26

#### [N-044] validate-audit-findings-hook.py contains dead else-branch summary recount
Fixed: 2026-04-26
Notes: After `parse_and_fix` runs, the `else` branch (lines 288-326) recounted h4 findings and rewrote the summary if the input numbers disagreed. But `parse_and_fix` already derives the summary from the same h4 counts when reconstructing the file, so if `fixed == original` the summary was already correct and the inner mismatch check could never fire. Verified by running the hook on a structurally-correct findings file: md5 unchanged before and after. Removed the dead else branch (-39 lines).

#### [N-043] stop-reminder.py misses untracked new SKILL.md files
Fixed: 2026-04-26
Notes: The hook used `git diff --name-only HEAD`, which sees tracked-modified and staged paths but not brand-new untracked files. A freshly-created `skills/foo/SKILL.md` not yet `git add`-ed was invisible — exactly the case where the validate-skills reminder matters most. Switched to `git status --porcelain -uall` (the `-uall` flag is required because the default `-u normal` shows untracked directories as `?? skills/` rather than recursing to the file). Also folded the no-commits fallback path away — `git status --porcelain` works without prior commits — and added explicit handling for rename entries (`R  old -> new`).

#### [N-042] release-readiness-reviewer.md step 6 uses unanchored grep for tag presence check
Fixed: 2026-04-26
Notes: `git tag | grep "v$(...)"` does substring matching. With version `1.2.0`, the grep also matches `v1.2.0-rc1`, `v1.2.10`, etc., causing false "tag exists" verdicts that would block a legitimate release. Verified: `printf 'v1.2.0\nv1.2.0-rc1\n' | grep "v1.2.0"` returns both lines. Replaced with `git rev-parse --verify "refs/tags/v$(...)" 2>/dev/null` which is the canonical exact-match tag-existence check.

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

### Pass 15 — 2026-05-02

#### [N-064] `test_validate_rules.py` missing test for valid no-frontmatter rule file
Notes: Invalid — `test_valid_plain_file_no_errors` already exercises this exact path using `VALID_PLAIN` (a file with no frontmatter). The no-frontmatter code path is covered; finding was filed in error.
