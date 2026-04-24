.PHONY: all check validate version-sync lint format list help bump-patch bump-minor bump-major

UV := uv run --quiet

all: check

help:
	@echo "Available targets:"
	@echo "  check        — validate + version-sync + lint (default)"
	@echo "  validate     — validate all SKILL.md files"
	@echo "  version-sync — check version consistency across manifests"
	@echo "  lint         — ruff check on scripts/"
	@echo "  format       — ruff format on scripts/"
	@echo "  list         — list all skills with descriptions"
	@echo "  bump-patch   — bump patch version"
	@echo "  bump-minor   — bump minor version"
	@echo "  bump-major   — bump major version"

check: validate version-sync lint

validate:
	$(UV) scripts/validate-skill.py

version-sync:
	$(UV) scripts/check-version-sync.py

list:
	$(UV) scripts/list-skills.py

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
