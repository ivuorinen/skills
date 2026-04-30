.PHONY: all check validate version-sync lint format list test help bump-patch bump-minor bump-major

UV := uv run --quiet

all: check

help:
	@echo "Available targets:"
	@echo "  check        — validate + version-sync + lint + test (default)"
	@echo "  validate     — validate all SKILL.md files"
	@echo "  version-sync — check version consistency across manifests"
	@echo "  lint         — ruff check on scripts/"
	@echo "  format       — ruff format on scripts/"
	@echo "  list         — list all skills with descriptions"
	@echo "  test         — run pytest unit tests"
	@echo "  bump-patch   — bump patch version"
	@echo "  bump-minor   — bump minor version"
	@echo "  bump-major   — bump major version"

check: validate version-sync lint test

validate:
	$(UV) scripts/validate-skill.py
	$(UV) scripts/validate-skill.py .claude/skills/*/SKILL.md

version-sync:
	$(UV) scripts/check-version-sync.py

list:
	$(UV) scripts/list-skills.py

test:
	uv run --with pytest pytest tests/

lint:
	uv run ruff check scripts/

format:
	uv run ruff format scripts/

bump-patch:
	$(UV) scripts/bump-version.py patch

bump-minor:
	$(UV) scripts/bump-version.py minor

bump-major:
	$(UV) scripts/bump-version.py major
