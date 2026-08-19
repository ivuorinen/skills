.PHONY: all check validate validate-evals spec-check validate-rules version-sync lock-check audit-consistency index-check pre-commit lint format format-check security list test typecheck help bump-patch bump-minor bump-major

UV := uv run --quiet

all: check

help:
	@echo "Available targets:"
	@echo "  check        — validate + validate-evals + validate-rules + version-sync + lock-check + audit-consistency + index-check + lint + format-check + security + typecheck + test + pre-commit (default)"
	@echo "  validate     — validate all SKILL.md files"
	@echo "  validate-evals — validate the evals/ sets bundled with each skill"
	@echo "  spec-check   — cross-check skills against the Agent Skills reference validator (network)"
	@echo "  validate-rules — validate .claude/rules/ files (structure + path freshness)"
	@echo "  version-sync — check version consistency across manifests"
	@echo "  lock-check   — fail if uv.lock is stale against pyproject.toml"
	@echo "  audit-consistency — validate the docs/audit/findings/ store (findings.py validate)"
	@echo "  index-check  — regenerate INDEX.md and fail if it was stale"
	@echo "  pre-commit   — run the full pre-commit suite (markdownlint, yamllint, gitleaks, …)"
	@echo "  lint         — ruff check on scripts/, tests/, skills/"
	@echo "  format       — ruff format on scripts/, tests/, skills/"
	@echo "  format-check — ruff format --check (CI-safe, no writes)"
	@echo "  security     — bandit static security scan of shipped tools and internal scripts"
	@echo "  list         — list all skills with descriptions"
	@echo "  test         — run pytest unit tests"
	@echo "  bump-patch   — bump patch version"
	@echo "  bump-minor   — bump minor version"
	@echo "  bump-major   — bump major version"

check: validate validate-evals validate-rules version-sync lock-check audit-consistency index-check lint format-check security typecheck test pre-commit

validate:
	$(UV) scripts/validate-skill.py
	$(UV) scripts/validate-skill.py .claude/skills/*/SKILL.md

# Eval sets are dev artifacts, never loaded at runtime — but a malformed one is
# silently skipped by the eval loop, so it is gated like any other surface.
validate-evals:
	$(UV) scripts/validate-evals.py

# Cross-check our validator against the Agent Skills reference implementation
# (https://agentskills.io/specification#validation). Every skill in the repo
# passes it, internal dev skills included. Out of `make check` only because it
# needs network access; scripts/validate-skill.py enforces the same constraints
# offline.
#
# The package is PyPI `skills-ref` but the console script it installs is
# `agentskills`; the spec page still documents the old `skills-ref` command,
# which no longer exists and exits 1 with no output — indistinguishable from a
# validation failure. The npm package of the same name is published by an
# unrelated author; do not substitute it.
#
# Failures print to stderr, successes to stdout, so stderr is merged before the
# result is judged. A silent pass is not evidence: this target fails the build
# on any non-zero skill rather than swallowing it.
spec-check:
	@fail=0; \
	for d in skills/*/ .claude/skills/*/; do \
		uvx --quiet --from skills-ref==0.1.1 agentskills validate "$$d" 2>&1 || fail=1; \
	done; \
	if [ "$$fail" -ne 0 ]; then echo "spec-check: at least one skill failed"; exit 1; fi; \
	echo "spec-check: all skills valid against the reference validator"

validate-rules:
	$(UV) scripts/validate-rules.py

version-sync:
	$(UV) scripts/check-version-sync.py

# check-version-sync.py covers the five manifests release-please rewrites; it
# does not cover uv.lock, which carries its own copy of the project version in
# the root package entry. 3.0.0 shipped with uv.lock still declaring 2.0.0 and
# nothing caught it, because release-please has no updater for the lockfile.
# `uv lock --check` is uv's own staleness test — it fails on that version drift
# and on dependency drift too, so no second parser is needed here.
lock-check:
	uv lock --check

audit-consistency:
	python3 skills/nitpicker/scripts/findings.py validate

index-check:
	python3 skills/nitpicker/scripts/findings.py index
	git diff --exit-code docs/audit/findings/INDEX.md

pre-commit:
	uv run --with pre-commit==4.6.2 pre-commit run --all-files --show-diff-on-failure

list:
	$(UV) scripts/list-skills.py

test:
	uv run --extra dev pytest tests/

# Zero floor: any pyright error fails the gate. A count threshold could mask a
# new error by fixing an old one, so the tolerated set must stay empty. Mirrors
# the Type-check step in .github/workflows/validate-skills.yml — change both together.
typecheck:
	uv run --with pyright==1.1.411 pyright --outputjson | python3 -c "import json,sys; n=json.load(sys.stdin)['summary']['errorCount']; print(f'pyright: {n} error(s)'); sys.exit(n != 0)"

lint:
	uv run --extra dev ruff check scripts/ tests/ skills/

# Scope matches [tool.bandit] in pyproject.toml: shipped tools plus internal
# tooling, tests excluded there. Mirrors the Security step in
# .github/workflows/validate-skills.yml — change both together.
security:
	uv run --extra dev bandit -c pyproject.toml -q -r skills/ scripts/

# ruff pinned to the same version pyproject.toml and .pre-commit-config.yaml
# name. These two targets WRITE, so a stale pin here reformats the tree one way
# while the gate judges it another.
format:
	uv run --with ruff==0.16.3 ruff format scripts/ tests/ skills/

format-check:
	uv run --with ruff==0.16.3 ruff format --check scripts/ tests/ skills/

bump-patch:
	$(UV) scripts/bump-version.py patch

bump-minor:
	$(UV) scripts/bump-version.py minor

bump-major:
	$(UV) scripts/bump-version.py major
