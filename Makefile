.PHONY: all check validate validate-rules version-sync audit-consistency lint format format-check list test help bump-patch bump-minor bump-major

UV := uv run --quiet

all: check

help:
	@echo "Available targets:"
	@echo "  check        — validate + validate-rules + version-sync + audit-consistency + lint + format-check + test (default)"
	@echo "  validate     — validate all SKILL.md files"
	@echo "  validate-rules — validate .claude/rules/ files (structure + path freshness)"
	@echo "  version-sync — check version consistency across manifests"
	@echo "  audit-consistency — check docs/audit/*-findings.md structure (dup headers, counts, IDs)"
	@echo "  lint         — ruff check on scripts/, tests/, skills/"
	@echo "  format       — ruff format on scripts/, tests/, skills/"
	@echo "  format-check — ruff format --check (CI-safe, no writes)"
	@echo "  list         — list all skills with descriptions"
	@echo "  test         — run pytest unit tests"
	@echo "  bump-patch   — bump patch version"
	@echo "  bump-minor   — bump minor version"
	@echo "  bump-major   — bump major version"

check: validate validate-rules version-sync audit-consistency lint format-check test

validate:
	$(UV) scripts/validate-skill.py
	$(UV) scripts/validate-skill.py .claude/skills/*/SKILL.md

validate-rules:
	$(UV) scripts/validate-rules.py

version-sync:
	$(UV) scripts/check-version-sync.py

audit-consistency:
	$(UV) skills/nitpicker/check-audit-consistency.py

list:
	$(UV) scripts/list-skills.py

test:
	uv run --with pytest pytest tests/

lint:
	uv run ruff check scripts/ tests/ skills/

format:
	uv run ruff format scripts/ tests/ skills/

format-check:
	uv run ruff format --check scripts/ tests/ skills/

bump-patch:
	$(UV) scripts/bump-version.py patch

bump-minor:
	$(UV) scripts/bump-version.py minor

bump-major:
	$(UV) scripts/bump-version.py major
