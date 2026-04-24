# Nitpicker Findings
Generated: 2026-04-24
Last validated: 2026-04-24

## Summary
- Total: 12 | Open: 0 | Fixed: 12 | Invalid: 0

## Open Findings

(none)

## Fixed

### 2026-04-24, first pass

#### [N-001] CI calls deleted shell script
Fixed: 2026-04-24
Notes: Replaced `bash scripts/check-version-sync.sh` with `uv run scripts/check-version-sync.py`; removed superfluous `node --version` line.

#### [N-002] Action SHA pins reference non-existent versions
Fixed: 2026-04-24
Notes: Reverted to `actions/checkout@v4` and `astral-sh/setup-uv@v5`.

#### [N-003] .ruff_cache/ not in .gitignore
Fixed: 2026-04-24
Notes: Added `.ruff_cache/` to `.gitignore`.

#### [N-004] stop-reminder.py silent on repo with no commits
Fixed: 2026-04-24
Notes: Falls back to `git status --porcelain` when `git diff --name-only HEAD` returns non-zero.

#### [N-005] Private skills not validated by CI
Fixed: 2026-04-24
Notes: Added `.claude/skills/**/SKILL.md` to workflow path filters; validate step now runs against both `skills/` and `.claude/skills/`.

#### [N-006] update_file() captures new_version as implicit global
Fixed: 2026-04-24
Notes: `update_file` now accepts `version: str` as an explicit parameter.

#### [N-007] parse_frontmatter duplicated across two scripts
Fixed: 2026-04-24
Notes: Extracted to `scripts/common.py`; both scripts now import from there.

#### [N-008] Makefile has no help target
Fixed: 2026-04-24
Notes: Added `help` target listing all available targets with descriptions.

### 2026-04-24, second pass

#### [N-009] pyproject.toml excluded from release-please auto-bump
Fixed: 2026-04-24
Notes: Added `{ "type": "toml", "path": "pyproject.toml", "jsonpath": "$.project.version" }` to extra-files in `.release-please-config.json`.

#### [N-010] update_toml() silently no-ops when version line not found
Fixed: 2026-04-24
Notes: Added `if new_content == content: sys.exit(1)` guard after `re.sub`.

#### [N-011] TOML version regex inconsistent between bump and check scripts
Fixed: 2026-04-24
Notes: Aligned `bump-version.py` regex to `[^"]+` to match `check-version-sync.py`.

#### [N-012] ERRORS/WARNINGS are module-level lists in validate-skill.py
Fixed: 2026-04-24
Notes: `errors` and `warnings` are now local lists in `main()`, passed into `validate()`. Inner `err()`/`warn()` closures append to them.

## Invalid

(none)
