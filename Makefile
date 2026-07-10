.PHONY: all check validate validate-rules version-sync audit-consistency index-check pre-commit lint format format-check list test help bump-patch bump-minor bump-major

UV := uv run --quiet

all: check

help:
	@echo "Available targets:"
	@echo "  check        — validate + validate-rules + version-sync + audit-consistency + lint + format-check + test (default)"
	@echo "  validate     — validate all SKILL.md files"
	@echo "  validate-rules — validate .claude/rules/ files (structure + path freshness)"
	@echo "  version-sync — check version consistency across manifests"
	@echo "  audit-consistency — validate the docs/audit/findings/ store (findings.py validate)"
	@echo "  index-check  — regenerate INDEX.md and fail if it was stale"
	@echo "  pre-commit   — run the full pre-commit suite (markdownlint, yamllint, gitleaks, …)"
	@echo "  lint         — ruff check on scripts/, tests/, skills/"
	@echo "  format       — ruff format on scripts/, tests/, skills/"
	@echo "  format-check — ruff format --check (CI-safe, no writes)"
	@echo "  list         — list all skills with descriptions"
	@echo "  test         — run pytest unit tests"
	@echo "  bump-patch   — bump patch version"
	@echo "  bump-minor   — bump minor version"
	@echo "  bump-major   — bump major version"

check: validate validate-rules version-sync audit-consistency index-check lint format-check test pre-commit

validate:
	$(UV) scripts/validate-skill.py
	$(UV) scripts/validate-skill.py .claude/skills/*/SKILL.md

validate-rules:
	$(UV) scripts/validate-rules.py

version-sync:
	$(UV) scripts/check-version-sync.py

audit-consistency:
	python3 skills/nitpicker/scripts/findings.py validate

index-check:
	python3 skills/nitpicker/scripts/findings.py index
	git diff --exit-code docs/audit/findings/INDEX.md

pre-commit:
	uv run --with pre-commit pre-commit run --all-files

list:
	$(UV) scripts/list-skills.py

test:
	uv run --with pytest --with ruff pytest tests/

lint:
	uv run --with ruff ruff check scripts/ tests/ skills/

format:
	uv run --with ruff ruff format scripts/ tests/ skills/

format-check:
	uv run --with ruff ruff format --check scripts/ tests/ skills/

bump-patch:
	$(UV) scripts/bump-version.py patch

bump-minor:
	$(UV) scripts/bump-version.py minor

bump-major:
	$(UV) scripts/bump-version.py major
